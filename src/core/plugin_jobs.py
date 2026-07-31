"""The core's book of in-flight plugin jobs — progress and cooperative cancellation (C9/C10).

Every function here opens its **own short-lived session** and commits it, exactly like the
scrape cache does, and for the same reason: what it writes has to be visible to another session
*while* the work is still running. A page polling a progress bar cannot see an uncommitted row.

That is the whole point of moving it here. A plugin used to publish its progress by writing its
own table and committing the session it had been handed — which, in a scheduled run, is the
**worker's** session, mid-``run_for_user``, with a half-filled ``scrape_user_log`` in it. The
commit made that half-row durable and a crash before the worker finished left it behind for
ever with a NULL status. A plugin now answers two questions instead of owning a transaction.

Reads and cancellation report the truth; publishing progress **never** raises: a progress bar
that cannot be updated is not a reason to lose a scrape.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select

from src.core.db import new_session
from src.core.models import PluginJob

log = logging.getLogger("wea.core.jobs")


@dataclass(frozen=True)
class JobProgress:
    """How far a job has got, as a reader sees it."""

    done: int
    total: int | None
    detail: str | None
    cancel_requested: bool


def begin_job(plugin_id: str, job_key: str, *, total: int | None = None) -> None:
    """Open (or reopen) a job: progress back to zero, **cancellation cleared**.

    The row is not deleted when a job ends, because its final progress is what the page shows
    afterwards — "read 2 of 21 pages" on a walk that stopped early is the honest record (C20),
    and clearing it would put a full bar or an empty one where a fact belongs. So a stale
    ``cancel_requested`` from the previous run has to be cleared *here*, or the next job would
    be killed by a request nobody made this time.
    """
    session = new_session()
    try:
        row = session.scalar(
            select(PluginJob).where(PluginJob.plugin_id == plugin_id, PluginJob.job_key == job_key)
        )
        if row is None:
            row = PluginJob(plugin_id=plugin_id, job_key=job_key)
            session.add(row)
        row.progress_done = 0
        row.progress_total = total
        row.detail = None
        row.cancel_requested = False
        row.updated_at = datetime.now(UTC)
        session.commit()
    finally:
        session.close()


def publish_progress(
    plugin_id: str,
    job_key: str,
    *,
    done: int,
    total: int | None = None,
    detail: str | None = None,
) -> None:
    """Record how far this job has got, and commit so a poller can see it.

    ``total`` and ``detail`` are only written when given: a walk knows its total from page one
    and would otherwise erase it on the next step.
    """
    try:
        session = new_session()
        try:
            row = session.scalar(
                select(PluginJob).where(
                    PluginJob.plugin_id == plugin_id, PluginJob.job_key == job_key
                )
            )
            if row is None:
                row = PluginJob(plugin_id=plugin_id, job_key=job_key)
                session.add(row)
            row.progress_done = done
            if total is not None:
                row.progress_total = total
            if detail is not None:
                row.detail = detail
            row.updated_at = datetime.now(UTC)
            session.commit()
        finally:
            session.close()
    except Exception:  # a bar that cannot move must not take a scrape down with it
        log.exception("jobs: could not publish progress for %s/%s", plugin_id, job_key)


def read_progress(plugin_id: str, job_key: str) -> JobProgress | None:
    """This job's state, or ``None`` when nothing of it is running."""
    session = new_session()
    try:
        row = session.scalar(
            select(PluginJob).where(PluginJob.plugin_id == plugin_id, PluginJob.job_key == job_key)
        )
        if row is None:
            return None
        return JobProgress(
            done=row.progress_done,
            total=row.progress_total,
            detail=row.detail,
            cancel_requested=row.cancel_requested,
        )
    finally:
        session.close()


def is_cancel_requested(plugin_id: str, job_key: str) -> bool:
    """Has anyone asked this job to stop?

    A **fresh session every time** on purpose, and that is not a substitution waiting to happen:
    the request is committed by another session (a web request), and a session that has already
    read this row would keep answering with the snapshot of its own transaction.
    """
    session = new_session()
    try:
        return bool(
            session.scalar(
                select(PluginJob.cancel_requested).where(
                    PluginJob.plugin_id == plugin_id, PluginJob.job_key == job_key
                )
            )
        )
    finally:
        session.close()


def request_cancel(plugin_id: str, job_key: str) -> None:
    """Ask this job to stop at its next checkpoint.

    Creates the row when there is none, and that matters: most of a scrape is the politeness
    wait, and the **first** wait happens before the first page has published any progress. A
    request that needed an existing row would be silently dropped in exactly the window a user
    is most likely to change their mind in.

    Whether the job was cancellable at all is the caller's question, not this one's: it is the
    plugin that knows what its job is and reads its own status to answer.
    """
    session = new_session()
    try:
        row = session.scalar(
            select(PluginJob).where(PluginJob.plugin_id == plugin_id, PluginJob.job_key == job_key)
        )
        if row is None:
            row = PluginJob(plugin_id=plugin_id, job_key=job_key)
            session.add(row)
        row.cancel_requested = True
        row.updated_at = datetime.now(UTC)
        session.commit()
    finally:
        session.close()


def forget_job(plugin_id: str, job_key: str) -> None:
    """Drop the book entry of something that no longer exists (the input was deleted). Not a
    job's normal ending: a finished job keeps its row, because its last progress is the record
    the page reads."""
    session = new_session()
    try:
        session.execute(
            delete(PluginJob).where(PluginJob.plugin_id == plugin_id, PluginJob.job_key == job_key)
        )
        session.commit()
    finally:
        session.close()
