"""Per-scraper job drainers (9.X6c).

One background thread per scraper that declares a queue. Each thread loops: take this
scraper's run lock, ask the plugin to drain one job, release. **Per scraper**, because they
are different sites with different rules — two of them may talk to their own site at the
same time, while each stays strictly serial with itself, which is what the site's
``Crawl-delay`` actually asks of us.

Event-driven rather than polled: adding a watch pokes its scraper and the thread wakes
within milliseconds. The timeout on the wait is the fallback that matters — when the lock
was busy (a scheduled run is in progress) there is no poke to wait for, so the thread
retries on its own.

Lives in the web process: that is where jobs are created, and the process is single
(uvicorn with no ``--workers``), so one thread per scraper is one drainer per scraper.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

from src.core.db import get_engine
from src.core.locks import acquire_scraper_lock
from src.core.plugins.base import ScraperPlugin
from src.core.plugins.context import build_context
from src.core.plugins.manifest import Manifest
from src.core.plugins.registry import LoadedPlugin

log = logging.getLogger("wea.web.jobs")

# How long a drainer waits for a poke before looking anyway. Only matters when the run lock
# was held: with the lock free every enqueue pokes. Small in tests (see conftest).
IDLE_WAIT_S = 5.0


@dataclass
class _Drainer:
    # The plugin is held **narrowed** to ScraperPlugin, and its manifest beside it, rather than
    # the LoadedPlugin that carries both: that one types its plugin as BasePlugin, so keeping it
    # meant either a second field for the narrowed view — two names for one object — or a cast
    # at each of the three uses. The manifest is here only because build_context asks for it.
    plugin_id: str
    plugin: ScraperPlugin
    manifest: Manifest
    wake: threading.Event = field(default_factory=threading.Event)
    stop: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None


_drainers: dict[str, _Drainer] = {}
_guard = threading.Lock()


def _run_one(drainer: _Drainer) -> bool:
    """One attempt: peek, then take the lock and drain a single job. ``False`` if there was
    nothing to do (or the lock was busy), which sends the thread back to waiting.

    The peek comes first and holds no lock. Taking a scraper-wide lock merely to discover an
    empty queue would have this thread churning through it, and a lock held for a peek is a
    lock a scheduled run or a manual scrape cannot have — which is how an idle drainer ended
    up answering 409 to *Scrape now*.
    """
    peek = build_context(drainer.manifest, drainer.plugin)
    try:
        if not drainer.plugin.has_queued_jobs(peek):
            return False
    except Exception:
        log.exception("job drainer for %s could not check its queue", drainer.plugin_id)
        return False
    finally:
        peek.db.close()

    lock = acquire_scraper_lock(get_engine(), drainer.plugin_id)
    if lock is None:
        # A scheduled run or a manual scrape holds it. The job keeps its place in the queue;
        # the page says so, because "first in the queue" with nothing happening reads as a
        # fault otherwise.
        return False
    # build_context owns its session; the caller closes it when the work ends.
    context = build_context(drainer.manifest, drainer.plugin)
    try:
        return drainer.plugin.drain_next_job(context)
    except Exception:
        log.exception("job drainer for %s failed", drainer.plugin_id)
        return False
    finally:
        context.db.close()
        lock.release()


def _loop(drainer: _Drainer) -> None:
    while not drainer.stop.is_set():
        try:
            worked = _run_one(drainer)
        except Exception:  # never let the thread die: it would silently stop the queue
            log.exception("job drainer for %s crashed", drainer.plugin_id)
            worked = False
        if worked:
            continue  # more may be waiting; go straight round again
        drainer.wake.clear()
        drainer.wake.wait(timeout=IDLE_WAIT_S)


def start_drainers(loaded: list[LoadedPlugin]) -> None:
    """Start one drainer per scraper that declares a queue. Idempotent."""
    with _guard:
        for lp in loaded:
            plugin = lp.plugin
            if not isinstance(plugin, ScraperPlugin) or plugin.plugin_id in _drainers:
                continue
            if type(plugin).has_queued_jobs is ScraperPlugin.has_queued_jobs:
                continue  # no queue of its own
            drainer = _Drainer(plugin_id=plugin.plugin_id, plugin=plugin, manifest=lp.manifest)
            drainer.thread = threading.Thread(
                target=_loop, args=(drainer,), name=f"jobs-{plugin.plugin_id}", daemon=True
            )
            _drainers[plugin.plugin_id] = drainer
            drainer.thread.start()
            log.info("job drainer started for %s", plugin.plugin_id)


def stop_drainers(timeout_s: float = 2.0) -> None:
    """Ask every drainer to stop and wait briefly. Called from the web's shutdown."""
    with _guard:
        drainers = list(_drainers.values())
        _drainers.clear()
    for drainer in drainers:
        drainer.stop.set()
        drainer.wake.set()
    for drainer in drainers:
        if drainer.thread is not None:
            drainer.thread.join(timeout=timeout_s)
    if drainers:
        log.info("job drainers stopped (%s)", len(drainers))


def poke(plugin_id: str) -> None:
    """Tell a scraper's drainer there is something to do. A no-op when it has no drainer
    (a plugin without a queue, or a unit test that never started one)."""
    drainer = _drainers.get(plugin_id)
    if drainer is not None:
        drainer.wake.set()


def reclaim_orphans(loaded: list[LoadedPlugin]) -> None:
    """At startup, fail whatever was left mid-flight (see ``reclaim_orphan_jobs``)."""
    for lp in loaded:
        plugin = lp.plugin
        if not isinstance(plugin, ScraperPlugin):
            continue
        if type(plugin).reclaim_orphan_jobs is ScraperPlugin.reclaim_orphan_jobs:
            continue
        context = build_context(lp.manifest, plugin)
        try:
            reclaimed = plugin.reclaim_orphan_jobs(context)
            if reclaimed:
                log.warning(
                    "%s: %s job(s) were left running by the previous process and are now "
                    "marked failed",
                    plugin.plugin_id,
                    reclaimed,
                )
        except Exception:
            log.exception("could not reclaim orphan jobs for %s", plugin.plugin_id)
        finally:
            context.db.close()
