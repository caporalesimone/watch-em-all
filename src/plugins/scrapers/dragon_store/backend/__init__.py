"""Dragon Store scraper — real scraping (3.B6/3.B7).

One HTTP request per product watch (``kind=product``) via ``context.http``; the
page is parsed by :mod:`parser` (JSON-LD ``Product`` primary, DOM list price) and
the title is cleaned by :mod:`sanitizer` (marketing/edition labels become
``tags``). The native id (``.gp.<id>.uw``) drives
``external_id`` through the base identity template-method (stable across runs).
Categories, pagination and the "ammaccato" filter are phase 9.

The write path is a ``context`` callback — the scraper never writes the catalog itself —
and *which* callback matters: ``update_catalog`` for a run that read every watch (it
delists whatever it did not see), ``upsert_catalog`` for anything partial or failed.

Since 2026-07-25 the site gates the first request of every session behind an anti-bot
interstitial served as **HTTP 200**, so the status code is no evidence and the body must be
classified (see :mod:`parser`). Three answers, three reactions: the interstitial is cleared
once per run and the page retried; a soft ``429`` aborts the run, because continuing is
what earns the rate limit; anything else is logged as an error and skipped. Their
``robots.txt`` publishes no ``Disallow`` and asks ``Crawl-delay: 10`` — the core client
enforces both (CTX-R10), which is the actual fix for what looked like a parser bug.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    delete,
    func,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from src.core.contracts import (
    Adjustment,
    BrandRef,
    CategoryRef,
    ConfigField,
    DeltaCounters,
    Product,
    ProductSourceRef,
)
from src.core.db import new_session
from src.core.errors import APIError
from src.core.http import RobotsDenied
from src.core.plugin_jobs import JobProgress
from src.core.plugins.base import ScraperPlugin, Tags
from src.core.plugins.context import (
    JobBook,
    PluginContext,
    bind_forget_source,
    bind_upsert_catalog,
    build_http_client,
)
from src.core.robots import origin_of
from src.core.run_log import record_traffic
from src.core.scraper_config import plugin_config
from src.core.scraper_stats import bump
from src.web.deps import SessionDep, UserDep
from src.web.jobs import poke

from .adjustments import DragonAdjustments, config_schema
from .parser import (
    DragonStoreChallenge,
    DragonStoreParseError,
    DragonStoreRateLimited,
    DragonStoreSoftError,
    ParsedCard,
    ParsedCategory,
    ParsedProduct,
    classify_url,
    page_url,
    parse_category,
    parse_product,
)
from .sanitizer import load_title_labels, sanitize_title

if TYPE_CHECKING:
    from src.core.models import CatalogProduct

PLUGIN_ID = "dragon_store"
# Native product id in a Dragon Store product URL, e.g. ".../...gp.35880.uw".
_GP_ID_RE = re.compile(r"\.gp\.(\d+)\.uw")
# The schema.org availability vocabulary moved to the scraper base (SCR-R18): those tokens are
# a web standard rather than this site's, and reading them per scraper was three copies of one
# rule. What stays here is what Dragon Store actually invented.
# The canonical label the sanitiser produces for a damaged listing; the category filter reads
# THIS, never a second search of the title (9.B5).
_DENTED_TAG = "Ammaccato"
# Ours, not the site's: a product the site offers with no price at all is a free download
# (9.B2b). English like "Pre Order", the other tag we invent; the site's own labels stay
# Italian because that is how they are printed.
_FREE_TAG = "Free"
# The interstitial's own checkbox clears the session with this single GET (see the page's
# inline JS); the cleared flag then rides the ASP session cookie the client keeps for the
# run. robots.txt allows crawling here — it publishes no Disallow, only Crawl-delay: 10 —
# so the honest way through is to obey that delay and identify ourselves, which we do.
_SESSION_CLEAR_PATH = "/ajaxRequests.asp?cmd=captcha_check_ok"
_SESSION_CLEAR_HEADERS = {"ReadyAjaxAuth": "readypro"}
_SESSION_CLEAR_OK = "OK"


@dataclass
class _CategoryOutcome:
    """What one category walk produced. ``complete`` false means a page could not be read, and
    the caller must then keep the delisting sweep away (CATSVC-R2b)."""

    products: list[Product]
    unpriced: list[ParsedCard]  # cards the listing showed without a price (9.B2b)
    excluded: int  # dented listings the watch asked not to see
    complete: bool
    # The category's own breadcrumb, read from page one: what the watch is *called*. Without
    # it the list of watches can only show the URL of a listing, which is unreadable (9.F1).
    breadcrumb: list[tuple[str, str | None]] = field(default_factory=list)


def _note(context: PluginContext, **deltas: int) -> None:
    """Record something only this plugin can see (9.B6c) — a gate, a rate limit, a page that
    would not parse. Never allowed to break a scrape: a statistic is not worth a run."""
    try:
        bump(context.db, PLUGIN_ID, deltas)
    except Exception:
        context.logger.exception("dragon_store: could not record %s", sorted(deltas))


def _mark_progress(
    context: PluginContext,
    watch: Watch,
    *,
    done: int,
    total: int | None = None,
    detail: str | None = None,
) -> None:
    """Progress is counted in **requests**, which is where the time goes: about eleven seconds
    of politeness each. The total is known from page one, so the bar is a real fraction.

    Published through the core (CTX-R13), not written on this session: it has to be committed
    while the walk is still running for the page to see it, and on a scheduled run this session
    belongs to the **worker** — committing it there made a half-filled `scrape_user_log` row
    durable in the middle of `run_for_user` (C10).
    """
    context.jobs.progress(str(watch.id), done=done, total=total, detail=detail)


def _record_scan(watch: Watch, *, included: int, excluded: int) -> None:
    """What this scan of the watch yielded — a photograph on the row, which is what the UI reads
    (9.F1/9.F3). Not a link from each product back here: a product can arrive from several
    watches at once, so a foreign key would be wrong at the first overlap."""
    watch.products_included = included
    watch.products_excluded = excluded
    watch.last_scanned_at = datetime.now(UTC)


class _Base(DeclarativeBase):
    """Dragon Store's own metadata, separate from the core schema (CTX-R6)."""


class Watch(_Base):
    """A user's watch — a single product page or a whole category (SCR-R1).

    The row doubles as the **job** that resolves it (9.X6): adding a watch writes and
    commits this row first and scrapes afterwards, so the state that describes a two-minute
    (or, for a category, several-minute) wait lives where a page reload can find it again
    instead of in a component that a refresh throws away.

    A category stays **one row**: the run re-scrapes the category, never the hundred
    products that came out of it, and the products carry no link back here — one product
    can arrive from several watches at once, so the honest model is "the catalog is what a
    complete delivery contains" (CATSVC-R2), not a foreign key. What the UI wants to show
    is kept here as counters, which are a photograph and cannot fall out of sync.
    """

    __tablename__ = "plugin_dragon_store_watches"
    # The duplicate check used to be a SELECT before an INSERT with a two-minute scrape in
    # between: a race with a window that wide, not a guarantee. Two quick submissions of the
    # same URL wrote two rows.
    __table_args__ = (UniqueConstraint("user_id", "url", name="uq_dragon_store_watch_user_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="product")
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    # Display snapshot of the last scraped product (name, image_url, brand,
    # tags, category) — set by a one-off scrape on add and refreshed
    # on each run. Null until the first successful scrape (UI falls back to the URL).
    snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # --- category options (9.B5) ---
    # Dented items are separate listings whose title starts with the label; off by default,
    # per category, and never applied to a single-product watch (DRG-R4/R7).
    include_ammaccati: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- job state (9.X6b/c/d/e/f) ---
    # queued -> running -> ready | failed | cancelled. A fresh row starts queued; the drainer
    # takes one scraper's oldest queued job at a time, holding the per-scraper lock.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    # Either the current step ("page 3 of 21") or why it failed — one field, because to the
    # user both answer "what is happening with this".
    status_detail: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # Progress and cooperative cancellation are **not** here any more (C9/C10): they live in
    # the core's book of in-flight jobs, keyed by this row's id, because publishing progress
    # means committing while the work runs — and on a scheduled run the session this plugin
    # holds is the worker's. What stays is the lifecycle nobody else has an opinion about.
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- what the last scan of this watch yielded (9.F1/9.F3) ---
    products_included: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    products_excluded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def _user_watches(db: Session, user_id: int) -> list[Watch]:
    """Every watch of this user, whatever its kind — this feeds the list the user reads, and
    hiding a category from it would hide the thing they just asked for."""
    return list(db.scalars(select(Watch).where(Watch.user_id == user_id).order_by(Watch.id.asc())))


def _product_watches(db: Session, user_id: int) -> list[Watch]:
    """The watches a run can currently resolve. Until 9.B3 teaches the run to walk a
    category's pages, handing it one would scrape a listing page as if it were a product."""
    return [w for w in _user_watches(db, user_id) if w.kind == "product"]


def _refuse_delisting(user_id: int, products: list[Product]) -> DeltaCounters:
    raise RuntimeError("a single-product delivery must never run the delisting sweep")


def _request_context(db: Session, *, sleep: Callable[[float], None] | None = None) -> PluginContext:
    """A context for a scrape driven by a web request, outside a scheduled run.

    The HTTP client comes from :func:`build_http_client`, so these paths get the same
    politeness, timeout, ``robots.txt`` compliance and scrape cache as a scheduled run —
    a hand-rolled client here would quietly ignore the admin config, which is precisely
    the sort of gap that gets a scraper rate-limited.

    Writes go through ``upsert_catalog``; ``update_catalog`` is wired to raise, because a
    delivery of one product says nothing about the others and must never delist them.
    """
    logger = logging.getLogger(f"wea.plugin.{PLUGIN_ID}")
    return PluginContext(
        engine=db.get_bind(),  # type: ignore[arg-type]
        db=db,
        logger=logger,
        config={},
        update_catalog=_refuse_delisting,
        upsert_catalog=bind_upsert_catalog(db),
        forget_source=bind_forget_source(db, PLUGIN_ID),
        # Same book the scheduled run publishes to, under this plugin's id: a context that let
        # this default would write progress into a namespace nobody reads.
        jobs=JobBook(plugin_id=PLUGIN_ID),
        http=build_http_client(db, PLUGIN_ID, logger, sleep=sleep),
    )


class WatchIn(BaseModel):
    url: str
    # Only a category can carry it (DRG-R4/R7); on a product URL it is ignored rather than
    # refused, because the page only offers the toggle when the URL is a category anyway.
    include_ammaccati: bool = False


class WatchPatch(BaseModel):
    """What can be changed on an existing watch (9.F1): the dented filter, and nothing else.
    The URL is the watch's identity — changing it would be a different watch."""

    include_ammaccati: bool


class WatchKindOut(BaseModel):
    """What kind of URL this is, decided by the backend (9.F2).

    The page asks while the user is still pasting, so it can offer the dented toggle for a
    category and not for a product. It exists rather than a second copy of the rule in
    TypeScript: the URL grammar is the plugin's, and two copies drift — the debt 9.F8 already
    declared for the price-difference rule, not repeated here. Costs no HTTP request."""

    kind: str | None


class WatchOut(BaseModel):
    id: int
    kind: str
    url: str
    # Display fields from the watch's product snapshot (null/empty until first scrape).
    name: str | None = None
    image_url: str | None = None
    brand: BrandRef | None = None
    tags: list[str] = Field(default_factory=list)
    category: list[CategoryRef] = Field(default_factory=list)
    # Job state (9.X6b): what is happening to this watch right now. It is read back from
    # the database, so a page that reloads mid-resolution finds it again.
    status: str = "ready"
    status_detail: str | None = None
    progress_done: int = 0
    progress_total: int | None = None
    # How many jobs of this scraper are ahead of this one; 0 while it is not queued.
    queue_position: int = 0
    # What the watch is set to, and what its last scan yielded (9.F1/9.F3). The counters are
    # a photograph of that scan, not a live count of the catalog: a product can arrive from
    # several watches, so "how many are mine" is not a question a watch can answer.
    include_ammaccati: bool = False
    products_included: int = 0
    products_excluded: int = 0
    last_scanned_at: datetime | None = None


class JobStatus(BaseModel):
    """The user's in-flight add (9.X6d): what the progress bar reads, one small GET.

    ``active`` false means there is nothing going on — the page shows a normal form. The
    remaining fields describe the one operation the user has in flight, since only one is
    allowed at a time.
    """

    active: bool
    watch_id: int | None = None
    kind: str | None = None
    url: str | None = None
    status: str | None = None
    status_detail: str | None = None
    progress_done: int = 0
    progress_total: int | None = None
    queue_position: int = 0
    cancellable: bool = False


def _snapshot(product: Product) -> dict[str, Any]:
    """The watch's display snapshot of a scraped product (stored as JSON)."""
    return {
        "name": product.name,
        "image_url": product.image_url,
        "brand": product.brand.model_dump() if product.brand else None,
        "tags": list(product.tags),
        "category": [c.model_dump() for c in product.category],
    }


def _category_snapshot(breadcrumb: list[tuple[str, str | None]]) -> dict[str, Any] | None:
    """The same display snapshot, for a **category** watch (9.F1).

    A category never gets one from the products it delivers — none of them lives at the
    watch's URL — so the list of watches could only print the listing URL, which says
    nothing. The breadcrumb the site prints on the listing is its name: the leaf is the
    category, what precedes it is where it sits. ``None`` when the page had no breadcrumb,
    so the caller keeps whatever name it already had rather than replacing it with nothing."""
    if not breadcrumb:
        return None
    leaf_text, _leaf_link = breadcrumb[-1]
    return {
        "name": leaf_text,
        "image_url": None,
        "brand": None,
        "tags": [],
        "category": [{"text": text, "link": link} for text, link in breadcrumb[:-1]],
    }


def _watch_out(watch: Watch, job: JobProgress | None = None) -> WatchOut:
    snap = watch.snapshot_json or {}
    return WatchOut(
        id=watch.id,
        kind=watch.kind,
        url=watch.url,
        name=snap.get("name"),
        image_url=snap.get("image_url"),
        brand=snap.get("brand"),
        tags=snap.get("tags") or [],
        category=snap.get("category") or [],
        status=watch.status,
        # One field, two kinds of news, and which one wins depends on whether the job is still
        # going: while it runs the step is what the user wants ("page 3 of 21"), and the moment
        # it is over the outcome is ("some pages could not be read"). Preferring the step either
        # way left a finished walk showing where it had got to instead of why it stopped.
        status_detail=(
            job.detail
            if job is not None and job.detail and watch.status in ("queued", "running")
            else watch.status_detail
        ),
        progress_done=job.done if job is not None else 0,
        progress_total=job.total if job is not None else None,
        include_ammaccati=watch.include_ammaccati,
        products_included=watch.products_included,
        products_excluded=watch.products_excluded,
        last_scanned_at=watch.last_scanned_at,
    )


class _JobCancelled(Exception):
    """The user asked this job to stop (9.X6f). Raised from the interruptible wait."""


def _cancellable_sleep(jobs: JobBook, watch_id: int) -> Callable[[float], None]:
    """A politeness wait that notices a cancellation.

    Almost all of a scrape's wall-clock is this wait — 11 seconds per request, by the site's
    own request — so a cancellation that only took effect between requests would feel broken.
    Checks four times a second and gives up the moment the flag is set.

    The reading is the core's (CTX-R13). It used to open a session of its own here, which was
    right for the wrong owner: the flag is committed by a web request, so a session that has
    already read the row would keep answering with its own snapshot — and this plugin should
    not be opening sessions to find out.
    """

    def sleep(seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while True:
            if jobs.cancelled(str(watch_id)):
                raise _JobCancelled
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(0.25, remaining))

    return sleep


def _resolve_watch(plugin: DragonStorePlugin, watch_id: int) -> None:
    """Resolve one freshly added watch, outside the request (9.X6b).

    Runs on its own session: the request's is closed by the time this starts. Every exit
    — success, failure, a site that will not answer — has to leave the row in a terminal
    state, or the page would poll a job that never ends.
    """
    logger = logging.getLogger(f"wea.plugin.{PLUGIN_ID}")
    db = new_session()
    # Declared out here so the `finally` can record what this resolution cost the site even
    # when it ended badly (10.B20): the requests were made either way.
    context: PluginContext | None = None
    try:
        watch = db.get(Watch, watch_id)
        if watch is None:  # removed while it sat in the queue
            return
        watch.status = "running"
        watch.started_at = datetime.now(UTC)
        db.commit()

        jobs = JobBook(plugin_id=PLUGIN_ID)
        # Opens the job in the core's book: progress at zero and any cancellation from a
        # previous attempt cleared, so a stale request cannot kill this one.
        jobs.begin(str(watch_id), total=1 if watch.kind == "product" else None)
        context = _request_context(db, sleep=_cancellable_sleep(jobs, watch_id))
        product: Product | None = None
        products: list[Product] = []
        detail: str | None = None
        try:
            if watch.kind == "category":
                # A category resolves to many products over several pages; the walk keeps the
                # row's progress up to date as it goes, which is what the page is polling.
                outcome = plugin._scrape_category(context, watch)
                # The tail pass settles the priceless cards **into this dict**, so it has to
                # be the dict we then deliver. It used to be built inline, one throwaway
                # argument: the detail pages were fetched — politeness wait included — and
                # their prices dropped on the floor, leaving those products in the catalog at
                # 0,00 with a Free tag until a scheduled run happened to fix them.
                delivered = {p.external_id: p for p in outcome.products}
                plugin._resolve_unpriced(context, outcome.unpriced, delivered)
                products = list(delivered.values())
                if not products:
                    detail = "the site returned no products for this category"
                elif not outcome.complete:
                    detail = "some pages could not be read; the next run will complete it"
                _record_scan(watch, included=len(products), excluded=outcome.excluded)
                watch.snapshot_json = _category_snapshot(outcome.breadcrumb) or watch.snapshot_json
            else:
                product = plugin._scrape_one(context, watch.url)
                if product is None:
                    detail = "the site did not return a readable product"
                else:
                    products = [product]
                # Through the same helper the scheduled run uses for a single watch: the
                # counters had two authors, one of them writing them by hand below.
                _record_scan(watch, included=len(products), excluded=0)
                # A product costs exactly one request and it has just been made, readable page
                # or not. Nothing counts steps on this path, so the step is recorded where it
                # happens — inferring it at the end is what made a half-read category lie (C20).
                _mark_progress(context, watch, done=1, total=1)
        except DragonStoreRateLimited as exc:
            detail = "the site is rate-limiting us; the next run will fill this in"
            logger.error("dragon_store: could not resolve %s while adding it — %s", watch.url, exc)
        except _JobCancelled:
            # **Nothing is delivered.** Cancelling means "I did not want this", so the products
            # read so far are dropped with the exception rather than half-filling a catalog the
            # user just said no to (C1). The comment here used to claim the opposite, along with
            # the message on the page and the phase doc — the code was the honest one.
            #
            # No work is wasted by that: every page fetched is already in the scrape cache,
            # committed at fetch time and independent of this transaction (CTX-R9), so a later
            # run of the same category gets those pages free for the rest of the half-life.
            #
            # The watch survives, and the next scheduled run reads it — a cancelled *add* is
            # not a removed input.
            watch.status = "cancelled"
            watch.status_detail = "cancelled while it was running"
            watch.finished_at = datetime.now(UTC)
            db.commit()
            logger.info("dragon_store: watch %s cancelled by the user", watch.id)
            return

        if products:
            # The snapshot first: it is what names this watch, and the provenance below reads
            # that name. Delivering before naming recorded a URL as the source of a product
            # whose title we were holding.
            if product is not None:
                watch.snapshot_json = _snapshot(product)
            # Never the delisting path: this delivery covers one input, and says nothing about
            # the user's other products (CATSVC-R2b). Everything here came from this one watch.
            source = _source_ref(watch)
            products = [p.model_copy(update={"sources": [source]}) for p in products]
            context.upsert_catalog(watch.user_id, products)
            logger.info(
                "dragon_store: watch %s resolved for user %s — %s product(s) stored",
                watch.id,
                watch.user_id,
                len(products),
            )
        else:
            logger.warning(
                "dragon_store: watch %s could not be resolved now — %s", watch.id, detail
            )
        # The watch is kept either way: "we could not read it" is not "it is not there",
        # and the next scheduled run will try again.
        watch.status = "ready" if products else "failed"
        watch.status_detail = detail
        # Nothing fills the bar to its total here, deliberately (C20): progress counts the
        # requests actually made, and a walk stopped by an unreadable page or a rate limit made
        # fewer than the total. Filling it left "21 of 21 read" on a row whose detail said some
        # pages could not be read — and DRG-R2 promises the count of pages read, not a bar that
        # always ends full. Each path records its own steps; a terminal job is terminal because
        # of `status`, which is what the page reads.
        watch.finished_at = datetime.now(UTC)
        # Deliberately after `_record_scan`, and deliberately not conditional: this stamps the
        # **attempt**, so a resolution that read nothing at all — a rate limit, an unreadable
        # page — still says when we last looked. `_record_scan` stamps what a scan *yielded*,
        # which is why the scheduled run needs it there and this one overwrites it here.
        watch.last_scanned_at = watch.finished_at
        db.commit()
    except Exception:  # background task: log it, there is no response to fail
        logger.exception("dragon_store: resolving watch %s crashed", watch_id)
        db.rollback()
        _mark_failed(db, watch_id, "an internal error stopped this; the next run will retry")
    finally:
        # This context builds its own HTTP client (see `_request_context`), so the core's job
        # drainer cannot see what it did: the traffic is recorded here, beside the client that
        # made it, and that is why the helper lives in the core and only the call is here.
        if context is not None:
            record_traffic(db, PLUGIN_ID, context.http)
        db.close()


def _source_ref(watch: Watch) -> ProductSourceRef:
    """This watch described as a source (C14).

    The key is the watch's id — stable for its whole life, and what ``forget_source`` is called
    with when it is deleted. The label is the name the user reads in their list, so it is taken
    from the snapshot and falls back to the URL only while the first scan has not named it yet.
    Built **after** a run has refreshed the snapshots, or a first-ever scan would record the URL
    of a listing page as the name of a category that now has one.
    """
    snapshot = watch.snapshot_json or {}
    return ProductSourceRef(
        key=str(watch.id),
        kind=watch.kind,
        label=str(snapshot.get("name") or watch.url),
    )


def _queue_position(db: Session, watch: Watch) -> int:
    """How many jobs of this scraper are queued ahead of this one (0 = next)."""
    ahead = db.scalar(
        select(func.count()).select_from(Watch).where(Watch.status == "queued", Watch.id < watch.id)
    )
    return int(ahead or 0)


def _mark_failed(db: Session, watch_id: int, detail: str) -> None:
    """Leave a terminal state behind even when the resolution crashed."""
    try:
        watch = db.get(Watch, watch_id)
        if watch is not None and watch.status == "running":
            watch.status = "failed"
            watch.status_detail = detail
            watch.finished_at = datetime.now(UTC)
            db.commit()
    except Exception:  # nothing left to do: the row stays as it is
        db.rollback()


class DragonStorePlugin(ScraperPlugin):
    plugin_id = PLUGIN_ID
    table_metadata = _Base.metadata  # DB-R7: declare the plugin's own schema

    # The cart rules, read from config once and kept until they change (10.B22).
    _adjust_cache: DragonAdjustments | None = None

    # --- identity (SCR-R10): the native gp id, else None -> URL fallback ---
    def identity_seed(self, raw: Any) -> str | None:
        match = _GP_ID_RE.search(str(raw))
        return match.group(1) if match else None

    def initialize(self, context: PluginContext) -> None:
        _Base.metadata.create_all(context.engine)
        context.logger.info("dragon_store initialized; watches table ensured")

    def delete_user_data(self, context: PluginContext, user_id: int) -> None:
        context.db.execute(delete(Watch).where(Watch.user_id == user_id))
        context.db.commit()

    # --- job queue (9.X6c): the watches table *is* the queue ---
    def has_queued_jobs(self, context: PluginContext) -> bool:
        return (
            context.db.scalar(select(Watch.id).where(Watch.status == "queued").limit(1))
        ) is not None

    def drain_next_job(self, context: PluginContext) -> bool:
        """Resolve the oldest queued watch. The core's drainer holds the run lock for us.

        One at a time on purpose: the site asks 10 seconds between requests, and a queue
        that ran two jobs at once would honour that per job while breaking it in aggregate —
        each ``HttpClient`` keeps its own politeness clock.
        """
        watch = context.db.scalars(
            select(Watch).where(Watch.status == "queued").order_by(Watch.id.asc()).limit(1)
        ).first()
        if watch is None:
            return False
        _resolve_watch(self, watch.id)
        return True

    def reclaim_orphan_jobs(self, context: PluginContext) -> int:
        """Fail whatever the previous process left running (9.X6c).

        Jobs live in the web process, so a row still claiming to be running cannot be: it is
        a leftover of a restart. Leaving it would be worse than a lost scrape, because that
        state blocks the user's next submission — a lock with no expiry shuts them out of
        their own plugin.
        """
        orphans = list(context.db.scalars(select(Watch).where(Watch.status == "running")))
        for watch in orphans:
            watch.status = "failed"
            watch.status_detail = "interrupted by a restart; the next run will fill this in"
            watch.finished_at = datetime.now(UTC)
        if orphans:
            context.db.commit()
        return len(orphans)

    def configured_users(self, context: PluginContext) -> list[int]:
        # Users a scheduled run scrapes: everyone with at least one watch (SCR-R3).
        return list(context.db.scalars(select(Watch.user_id).distinct().order_by(Watch.user_id)))

    def get_admin_config_schema(self) -> list[ConfigField]:
        """The cart rules, editable by an admin (10.B22). Declared here rather than hard-wired
        in `adjustments.py`, where phase 5 left a note promising exactly this move."""
        return config_schema()

    def get_adjustments(
        self, products: list[CatalogProduct], cart_total: Decimal
    ) -> list[Adjustment]:
        # DRG-R5: a non-cumulative threshold discount + shipping (free above a threshold),
        # applied to the cart's discounted total. Rules live in adjustments.py.
        return self._adjustments().compute(cart_total)

    def _adjustments(self) -> DragonAdjustments:
        """The rules built from the stored config, cached until the config changes (10.B22).

        Cached because this signature has no session — the cart engine calls it per cart, and
        opening one to read four numbers each time would put a query on the path of every
        recomputation. `on_config_changed` drops the cache, so a threshold saved in the admin
        page takes effect on the next evaluation without a restart, which is what the MVP asks.
        """
        if self._adjust_cache is None:
            db = new_session()
            try:
                self._adjust_cache = DragonAdjustments(
                    plugin_config(db, PLUGIN_ID, config_schema())
                )
            finally:
                db.close()
        return self._adjust_cache

    def on_config_changed(self) -> None:
        self._adjust_cache = None

    # --- scraping (SCR-R4/R5/R6): one HTTP request per watch, via context.http ---
    def _clear_session(self, context: PluginContext, url: str) -> bool:
        """Tick the interstitial's "I am not a robot" box the way the page's own JS does:
        one GET that flips a flag on our ASP session. Returns ``True`` when the site
        confirmed with ``OK``."""
        endpoint = origin_of(url) + _SESSION_CLEAR_PATH
        context.logger.warning(
            "dragon_store: anti-bot interstitial served for %s — clearing the session via %s",
            url,
            endpoint,
        )
        # Counted, not just logged (9.B6c): during the July block the question was "since when
        # and how often", and a log line cannot answer either.
        _note(context, gate_hits_total=1)
        try:
            response = context.http.get(endpoint, headers=_SESSION_CLEAR_HEADERS)
        except OSError as exc:
            context.logger.error("dragon_store: session clear request failed: %s", exc)
            return False
        finally:
            # Never let this GET sit in the cache: a cached "OK" would make later runs
            # believe the session was cleared when nothing was actually sent.
            context.http.forget(endpoint)

        body = response.text.strip()
        if response.status_code != 200 or body != _SESSION_CLEAR_OK:
            context.logger.error(
                "dragon_store: session clear refused (HTTP %s, body %r) — cannot reach the "
                "product pages",
                response.status_code,
                body[:80],
            )
            return False
        context.logger.warning(
            "dragon_store: session cleared (site answered %r) — retrying the page", body
        )
        _note(context, gate_cleared_total=1)
        return True

    def _scrape_one(
        self, context: PluginContext, url: str, *, may_clear_session: bool = True
    ) -> Product | None:
        """Fetch + parse one product page; ``None`` (logged as an error) on failure, so a
        single bad page never aborts the whole run. Rate limiting is the one exception: it
        propagates, because it is about the site as a whole, not about this page."""
        try:
            response = context.http.get(url)
        except RobotsDenied as exc:
            context.logger.error("dragon_store: not fetching %s — %s", url, exc)
            return None
        except OSError as exc:  # network/timeout after retries
            context.logger.error("dragon_store: fetch failed for %s: %s", url, exc)
            return None
        if response.status_code != 200:
            context.logger.error("dragon_store: %s returned HTTP %s", url, response.status_code)
            return None

        try:
            parsed = parse_product(response.content, url)
        except DragonStoreChallenge as exc:
            # A 200 carrying a gate must not be replayed from cache for the next 12 hours.
            context.http.forget(url)
            if not may_clear_session:
                context.logger.error(
                    "dragon_store: still gated after clearing the session for %s (%s) — "
                    "giving up on this page",
                    url,
                    exc,
                )
                return None
            if not self._clear_session(context, url):
                return None
            return self._scrape_one(context, url, may_clear_session=False)
        except DragonStoreRateLimited:
            context.http.forget(url)
            _note(context, rate_limited_total=1)
            raise
        except DragonStoreSoftError as exc:
            # Deliberately not a parse failure: the page parsed fine and *says* it is an error
            # (their error pages carry the real status inside a 200). Counting it would put the
            # site's own 404s in a statistic that is supposed to mean "our reading broke".
            context.http.forget(url)
            context.logger.error("dragon_store: %s", exc)
            return None
        except DragonStoreParseError as exc:
            context.logger.error("dragon_store: parse failed for %s: %s", url, exc)
            # Counted here too, not only on a listing (9.B6c): the statistic was asymmetric, so
            # "the product pages stopped parsing" — a site redesign, the shape of every
            # breakage we have had — was the one thing it could not show.
            _note(context, parse_failures_total=1)
            return None
        return self._to_product(context, url, parsed, response.fetched_at)

    def _to_product(
        self,
        context: PluginContext,
        url: str,
        parsed: ParsedProduct,
        fetched_at: datetime | None = None,
    ) -> Product:
        """A product **detail page** as a ``Product``: site knowledge only, the contract is the
        base's (SCR-R18). What is Dragon Store's here is the sanitiser's labels, the price the
        site does not always print, and the four keys worth keeping in ``extra``."""
        tags = self._tags_from_title(parsed.name)
        return self.build_product(
            context,
            raw=url,
            url=url,
            name=sanitize_title(parsed.name, load_title_labels())[0] or parsed.name,
            price_current=self._resolve_price(
                context,
                url=url,
                price_current=parsed.price_current,
                price_original=parsed.price_original,
                tags=tags,
            ),
            price_original=parsed.price_original,
            availability=parsed.availability,
            brand_text=parsed.brand_text,
            brand_link=parsed.brand_link,
            image_url=parsed.image_url,
            currency=parsed.currency,
            breadcrumb=parsed.breadcrumb,
            tags=tags,
            extra={
                "sku": parsed.sku,
                "price_valid_until": parsed.price_valid_until,
                "category": parsed.category,
                "description": parsed.description,
            },
            fetched_at=fetched_at,
        )

    def _tags_from_title(self, name: str) -> Tags:
        """The labels the site prints in a title, as tags (DRG-R4/9.B5).

        The one piece both conversions genuinely share and that is genuinely ours: which words
        are labels is Dragon Store's knowledge, and the sanitiser is the only reader of it.
        """
        tags = self.new_tags()
        for label in sanitize_title(name, load_title_labels())[1]:
            tags.add_tag(label)
        return tags

    # --- categories (9.B2/9.B3/9.B5/9.B2b) ---
    def _resolve_price(
        self,
        context: PluginContext,
        *,
        url: str,
        price_current: Decimal | None,
        price_original: Decimal | None,
        tags: Tags,
    ) -> Decimal:
        """The price to store when the site shows none (9.B2b).

        Three cases, told apart because guessing gets them wrong in an expensive way. A price:
        use it. No price but a list price — a product withheld from sale, `L'Isola Proibita` at
        24,95 — use that. Neither: it is genuinely free (a digital download), so 0,00 plus a
        tag that says so. Calling the middle case free would put a 25-euro game in the catalog
        at zero and fire a price-drop alert on it.
        """
        if price_current is not None:
            return price_current
        if price_original is not None:
            context.logger.info(
                "dragon_store: %s has no current price; using its list price %s",
                url,
                price_original,
            )
            return price_original
        tags.add_tag(_FREE_TAG)
        return Decimal("0.00")

    def _card_to_product(
        self,
        context: PluginContext,
        card: ParsedCard,
        breadcrumb: list[tuple[str, str | None]],
        fetched_at: datetime | None,
    ) -> Product:
        """A listing card as a ``Product``. The breadcrumb comes from the category page: a card
        does not carry one, and the page's own is the same one the product's detail page
        publishes (verified on 36099).

        The two conversions differ in exactly what a card and a detail page differ in — where
        the breadcrumb comes from, and that a card carries two of the four ``extra`` keys. Every
        other line was the same, which is how they drifted: the discarded ``fetched_at`` of C3,
        and an ``extra`` filter that had become truthiness here and ``is not None`` there, so an
        empty description survived one path and was dropped by the other. The shared part now
        lives once, in the base (SCR-R18), and cannot drift again.
        """
        tags = self._tags_from_title(card.name)
        return self.build_product(
            context,
            raw=card.url,
            url=card.url,
            name=sanitize_title(card.name, load_title_labels())[0] or card.name,
            price_current=self._resolve_price(
                context,
                url=card.url,
                price_current=card.price_current,
                price_original=card.price_original,
                tags=tags,
            ),
            price_original=card.price_original,
            availability=card.availability,
            brand_text=card.brand_text,
            brand_link=card.brand_link,
            image_url=card.image_url,
            currency=card.currency,
            breadcrumb=breadcrumb,
            tags=tags,
            extra={"sku": card.code, "description": card.description},
            fetched_at=fetched_at,
        )

    def _fetch_category_page(
        self, context: PluginContext, url: str, page: int
    ) -> tuple[ParsedCategory, datetime | None] | None:
        """One page of a listing, clearing the session once if the gate answers instead.

        Returns the page **and when the site answered** — the cache's own timestamp on a hit,
        the clock on a real fetch (PROD-R8). Discarding it, as this used to, dated fifty
        products to "now" off a page that might be twelve hours old: `last_seen_at` then
        reported when we last re-served a listing instead of when the site last spoke, and the
        per-product statistics counted a replay as a fresh observation.
        """
        target = page_url(url, page)
        try:
            response = context.http.get(target)
        except RobotsDenied as exc:
            # Fail closed, and fail *quietly*: a run must never raise out of here, or the
            # caller cannot report an incomplete delivery — and an exception escaping would
            # take the whole user's run with it.
            context.logger.error("dragon_store: not fetching %s — %s", target, exc)
            return None
        except OSError as exc:  # network/timeout after retries
            context.logger.error("dragon_store: fetch failed for %s: %s", target, exc)
            return None
        if response.status_code != 200:
            context.logger.error("dragon_store: %s returned HTTP %s", target, response.status_code)
            return None
        try:
            return parse_category(response.content, target), response.fetched_at
        except DragonStoreChallenge:
            context.http.forget(target)
            if not self._clear_session(context, target):
                return None
            response = context.http.get(target)
            try:
                return parse_category(response.content, target), response.fetched_at
            except DragonStoreParseError as exc:
                context.logger.error("dragon_store: %s unreadable after the gate — %s", target, exc)
                return None
        except DragonStoreRateLimited:
            context.http.forget(target)
            _note(context, rate_limited_total=1)
            raise
        except DragonStoreParseError as exc:
            context.logger.error("dragon_store: %s is not a readable listing — %s", target, exc)
            _note(context, parse_failures_total=1)
            return None

    def _scrape_category(self, context: PluginContext, watch: Watch) -> _CategoryOutcome:
        """Walk one category and deliver its products (9.B3).

        Pages come from the site's own ``&pg=N`` links, one request at a time; the page count
        is printed on page one, so the progress the user sees is a real fraction from the first
        request rather than a guess. A page that cannot be read makes the delivery
        **incomplete**, which keeps the delisting sweep away from it (CATSVC-R2b): "we could
        not read page 7" is not "those products are gone".
        """
        products: dict[str, Product] = {}
        unpriced: list[ParsedCard] = []
        breadcrumb: list[tuple[str, str | None]] = []
        excluded = 0
        page = 1
        total_pages = 1
        complete = True
        while page <= total_pages:
            fetched = self._fetch_category_page(context, watch.url, page)
            if fetched is None:
                complete = False
                break
            parsed, fetched_at = fetched
            if page == 1:
                total_pages = parsed.total_pages or 1
                breadcrumb = parsed.breadcrumb
                _mark_progress(context, watch, done=0, total=total_pages)
                context.logger.info(
                    "dragon_store: category %s has %s product(s) over %s page(s)",
                    watch.url,
                    parsed.total_items,
                    total_pages,
                )
            _note(context, pages_fetched_total=1)
            for card in parsed.cards:
                # The dented filter reads the sanitiser's tag, never a second search of its
                # own: the sanitiser strips the label from the name, so a detector running
                # after it would find nothing, and one running before would be the same rule
                # written twice, free to drift (DRG-R4, rewritten in 9.B5).
                # `fetched_at` is this page's, not the walk's: page 1 can come off the cache
                # while page 2 is fetched for real, and each card belongs to its own page.
                product = self._card_to_product(context, card, parsed.breadcrumb, fetched_at)
                if _DENTED_TAG in product.tags and not watch.include_ammaccati:
                    excluded += 1
                    continue
                if card.price_current is None:
                    unpriced.append(card)
                products[product.external_id] = product
            # Published through the core, which commits its own session (C10). This used to
            # commit `context.db` right here — the worker's session on a scheduled run, holding
            # a half-filled `scrape_user_log` row that a crash would then leave behind for ever.
            _mark_progress(
                context, watch, done=page, total=total_pages, detail=f"page {page} of {total_pages}"
            )
            page += 1

        return _CategoryOutcome(
            products=list(products.values()),
            unpriced=unpriced,
            excluded=excluded,
            complete=complete,
            breadcrumb=breadcrumb,
        )

    def _resolve_unpriced(
        self, context: PluginContext, cards: list[ParsedCard], delivered: dict[str, Product]
    ) -> None:
        """The tail pass of 9.B2b: open the detail page of every product a listing showed
        without a price and settle it there.

        Runs **last**, after the categories and the single-product watches, so a product that
        is also watched on its own has already been read and costs nothing here. On the sample
        this is 2-4% of a category — 20-40 requests on a thousand-product one.
        """
        for card in cards:
            external_id = self.external_id_for(raw=card.url, url=card.url)
            existing = delivered.get(external_id)
            if existing is not None and existing.price_current != Decimal("0.00"):
                continue  # already resolved by a detail-page read in this same run
            resolved = self._scrape_one(context, card.url)
            if resolved is not None:
                delivered[external_id] = resolved

    # --- runtime (SCR-R4/R5, order and de-duplication: 9.B4) ---
    def run_for_user(self, context: PluginContext, user_id: int) -> DeltaCounters:
        """Scrape everything this user watches, in the order that costs the site least.

        **Categories first, then the single products they did not already deliver, then the
        products no listing could price.** The saving is not the HTTP cache — a listing page and
        a detail page are different URLs — but identity: a card yields the same ``external_id``
        as the detail page, so a product a category already delivered needs no request of its
        own (DRG-R3). Five single watches covered by one category go from 77 seconds to 22.
        """
        watches = _user_watches(context.db, user_id)
        if not watches:
            # No watches != "site returned nothing": deliver nothing, do NOT delist.
            context.logger.info("dragon_store: user %s has no watches — nothing to do", user_id)
            return DeltaCounters()

        categories = [w for w in watches if w.kind == "category"]
        singles = [w for w in watches if w.kind == "product"]
        context.logger.info(
            "dragon_store: starting run for user %s — %s category(ies), %s single product(s)",
            user_id,
            len(categories),
            len(singles),
        )

        delivered: dict[str, Product] = {}
        # Which watches delivered each product (C14). Ids, not descriptions: the labels are
        # read at the end, once this run has refreshed every snapshot, so a category scanned
        # for the first time is recorded under the name it just learned.
        from_watches: dict[str, set[int]] = {}
        unpriced: list[ParsedCard] = []
        excluded = 0  # dented listings this run left out, for the run record (9.B5)
        failed = 0
        aborted = False

        # 1. Categories.
        for watch in categories:
            try:
                outcome = self._scrape_category(context, watch)
            except DragonStoreRateLimited as exc:
                context.logger.error(
                    "dragon_store: rate-limited by the site while reading %s (%s) — aborting "
                    "this run; carrying on is what earns the rate limit",
                    watch.url,
                    exc,
                )
                aborted = True
                break
            for product in outcome.products:
                delivered[product.external_id] = product
                from_watches.setdefault(product.external_id, set()).add(watch.id)
            unpriced.extend(outcome.unpriced)
            excluded += outcome.excluded
            failed += 0 if outcome.complete else 1
            _record_scan(watch, included=len(outcome.products), excluded=outcome.excluded)
            watch.snapshot_json = _category_snapshot(outcome.breadcrumb) or watch.snapshot_json
            context.logger.info(
                "dragon_store: category %s delivered %s product(s), %s excluded as dented",
                watch.url,
                len(outcome.products),
                outcome.excluded,
            )

        # 2. Single products a category has not already delivered.
        if not aborted:
            for index, watch in enumerate(singles):
                external_id = self.external_id_for(raw=watch.url, url=watch.url)
                if external_id in delivered:
                    context.logger.info(
                        "dragon_store: %s already came from a category this run — not asking "
                        "the site again",
                        watch.url,
                    )
                    # Still one of its sources: it is watched on its own as well, so deleting
                    # the product would bring it back even if that category went away.
                    from_watches.setdefault(external_id, set()).add(watch.id)
                    _record_scan(watch, included=1, excluded=0)
                    continue
                try:
                    resolved = self._scrape_one(context, watch.url)
                except DragonStoreRateLimited as exc:
                    remaining = len(singles) - index
                    context.logger.error(
                        "dragon_store: rate-limited by the site (%s) — aborting with %s of %s "
                        "single watch(es) unread",
                        exc,
                        remaining,
                        len(singles),
                    )
                    aborted = True
                    failed += remaining
                    break
                if resolved is None:
                    failed += 1
                    continue
                delivered[resolved.external_id] = resolved
                from_watches.setdefault(resolved.external_id, set()).add(watch.id)
                _record_scan(watch, included=1, excluded=0)

        # 3. The products no listing could price (9.B2b), last so the reads above count.
        if not aborted and unpriced:
            context.logger.info(
                "dragon_store: resolving %s product(s) a listing showed without a price",
                len(unpriced),
            )
            try:
                self._resolve_unpriced(context, unpriced, delivered)
            except DragonStoreRateLimited as exc:
                context.logger.error(
                    "dragon_store: rate-limited while resolving priceless products (%s)", exc
                )
                aborted = True

        # Refresh each watch's display snapshot from this run; the catalog write below commits
        # this session, persisting these too.
        by_url = {p.url: p for p in delivered.values()}
        for watch in watches:
            latest = by_url.get(watch.url)
            if latest is not None:
                watch.snapshot_json = _snapshot(latest)

        # Provenance last, so every label above is the current one (C14).
        by_id = {w.id: w for w in watches}
        products = [
            p.model_copy(
                update={
                    "sources": [
                        _source_ref(by_id[wid])
                        for wid in sorted(from_watches.get(p.external_id, ()))
                        if wid in by_id
                    ]
                }
            )
            for p in delivered.values()
        ]

        context.logger.info(
            "dragon_store: run for user %s delivered %s product(s) — %s HTTP request(s), "
            "%s cache hit(s)",
            user_id,
            len(products),
            context.http.request_count,
            context.http.cache_hits,
        )
        if not aborted and failed == 0:
            delta = context.update_catalog(user_id, products)
            delta.excluded = excluded  # the service cannot know: it is handed the survivors
            return delta

        # Incomplete: we cannot tell "gone from the site" from "we could not read it", so the
        # delisting sweep must not run (CATSVC-R2). Anything else would wipe the user's catalog
        # for this scraper on any gate or outage.
        context.logger.error(
            "dragon_store: incomplete run for user %s (%s input(s) unread%s) — delivering %s "
            "product(s) WITHOUT delisting; the catalog keeps its current state",
            user_id,
            failed,
            ", aborted early" if aborted else "",
            len(products),
        )
        delta = context.upsert_catalog(user_id, products)
        delta.excluded = excluded
        return delta

    # --- routes: watches CRUD (per-user) ---
    def router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/classify", response_model=WatchKindOut)
        def classify(url: str, user: UserDep) -> WatchKindOut:
            """What kind of URL this is — asked while the user is pasting (9.F2).

            Authenticated but otherwise free: it reads a string and answers, so the page can
            offer the dented toggle for a category and not for a product without shipping a
            second copy of the URL grammar in TypeScript.
            """
            return WatchKindOut(kind=classify_url(url.strip()))

        @router.get("/watches", response_model=list[WatchOut])
        def list_watches(user: UserDep, db: SessionDep) -> list[WatchOut]:
            jobs = JobBook(plugin_id=PLUGIN_ID)
            out = []
            for watch in _user_watches(db, user.sub):
                # The last job's progress outlives the job (C20): "read 2 of 21 pages" is what
                # a walk stopped early has to keep saying afterwards.
                item = _watch_out(watch, jobs.read(str(watch.id)))
                if watch.status == "queued":
                    item.queue_position = _queue_position(db, watch)
                out.append(item)
            return out

        @router.post("/watches", response_model=WatchOut, status_code=201)
        def add_watch(body: WatchIn, user: UserDep, db: SessionDep) -> WatchOut:
            """Write the row first, scrape afterwards (9.X6b).

            It used to be the other way round, and the wait — the site's ``Crawl-delay``
            plus its access check, up to a couple of minutes — sat inside the request, with
            everything describing it living in the page. A reload wiped the spinner but not
            the scrape: the work finished and wrote, invisibly, and the user, seeing
            nothing, added the same URL again. Now the row is committed in milliseconds and
            **is** the job: reloading re-reads it, and a process that dies mid-scrape leaves
            a row the next scheduled run resolves by itself.
            """
            url = body.url.strip()
            kind = classify_url(url)
            if kind is None:
                raise APIError(422, "invalid_url", "not a Dragon Store product or category URL")
            # One in flight per user (9.X6d). The refusal lives HERE, not in the page: a
            # disabled button stops nothing, and this is precisely the state a reload used to
            # throw away — the user saw a usable form and submitted again.
            in_flight = db.scalar(
                select(Watch).where(
                    Watch.user_id == user.sub, Watch.status.in_(("queued", "running"))
                )
            )
            if in_flight is not None:
                raise APIError(
                    409, "add_in_progress", "another URL of yours is still being resolved"
                )

            watch = Watch(
                user_id=user.sub,
                kind=kind,
                url=url,
                # A single product is watched as it is, label and all: the filter is a
                # property of a listing, and applying it here would silently refuse the
                # product the user asked for (DRG-R7).
                include_ammaccati=body.include_ammaccati and kind == "category",
                status="queued",
                queued_at=datetime.now(UTC),
            )
            db.add(watch)
            try:
                db.commit()
            except IntegrityError:
                # The UNIQUE is the guarantee; this is just how it reaches the user.
                db.rollback()
                raise APIError(409, "duplicate_watch", "this URL is already watched") from None
            db.refresh(watch)
            # The queue is drained by this scraper's own drainer, which holds the run lock
            # (9.X6c) — so an add never competes with a scheduled run. Poking it just saves
            # the wait until its next look.
            poke(PLUGIN_ID)
            out = _watch_out(watch)
            out.queue_position = _queue_position(db, watch)
            return out

        @router.get("/watches/job", response_model=JobStatus)
        def job_status(user: UserDep, db: SessionDep) -> JobStatus:
            """The user's in-flight add, if any (9.X6d) — what the progress bar polls.

            Same shape as the ``scrape-now`` cooldown pair: one small GET the page can ask
            repeatedly. It reads the row, so a reload finds the operation again instead of
            losing it, and it answers *why* nothing is moving — waiting in the queue, or a
            scheduled run holding this scraper.
            """
            watch = db.scalar(
                select(Watch)
                .where(Watch.user_id == user.sub, Watch.status.in_(("queued", "running")))
                .order_by(Watch.id.asc())
            )
            if watch is None:
                return JobStatus(active=False)
            # Progress comes from the core's book (CTX-R13), which is what the running job
            # publishes to; the row supplies the lifecycle around it.
            job = JobBook(plugin_id=PLUGIN_ID).read(str(watch.id))
            return JobStatus(
                active=True,
                watch_id=watch.id,
                kind=watch.kind,
                url=watch.url,
                status=watch.status,
                status_detail=(
                    job.detail if job is not None and job.detail else watch.status_detail
                ),
                progress_done=job.done if job is not None else 0,
                progress_total=job.total if job is not None else None,
                queue_position=_queue_position(db, watch) if watch.status == "queued" else 0,
                cancellable=watch.kind == "category"
                and not (job is not None and job.cancel_requested),
            )

        @router.post("/watches/{watch_id}/cancel", status_code=202)
        def cancel_watch_job(watch_id: int, user: UserDep, db: SessionDep) -> dict[str, str]:
            """Ask a running (or queued) job to stop (9.X6f).

            Cooperative: a thread cannot be killed, and does not need to be — the job reads
            this flag at the checkpoints that write its progress, and the politeness wait is
            interruptible, so it stops within a second rather than at the end of the page it
            was waiting for.

            **Nothing read so far is delivered** (C1): cancelling an add means the user did not
            want it, and half a category is not what they asked for either. The requests are not
            wasted — the pages sit in the scrape cache (CTX-R9), so a later run of the same
            category has them for free. The watch itself stays, and the next scheduled run reads
            it: stopping an add is not removing an input.
            """
            watch = db.scalar(select(Watch).where(Watch.id == watch_id, Watch.user_id == user.sub))
            if watch is None:
                raise APIError(404, "not_found", "watch not found")
            if watch.status not in ("queued", "running"):
                raise APIError(409, "not_running", "this watch is not being resolved")
            if watch.status == "queued":
                # Never started: nothing to stop, nothing was written.
                watch.status = "cancelled"
                watch.status_detail = "cancelled before it started"
                watch.finished_at = datetime.now(UTC)
                db.commit()
                return {"status": "cancelled"}
            # Whether it was cancellable was decided just above, from the status this plugin
            # owns; the flag itself lives in the core's book, where the running job reads it
            # without either side sharing a session (C9/C10).
            JobBook(plugin_id=PLUGIN_ID).request_cancel(str(watch_id))
            return {"status": "cancelling"}

        @router.patch("/watches/{watch_id}", response_model=WatchOut)
        def update_watch(
            watch_id: int, body: WatchPatch, user: UserDep, db: SessionDep
        ) -> WatchOut:
            """Change the dented filter on an existing category watch (9.F1/9.F2).

            It takes effect on the **next** scan, not retroactively: turning it off does not
            remove the dented products already in the catalog (that is what the cleanups of
            9.F4 are for), and turning it on does not fetch them now.

            Refused while the watch is being resolved. The walk reads this very column between
            pages, so a change landing mid-scan would apply to the second half of a category
            and not the first — a state no one asked for and nothing records.
            """
            watch = db.scalar(select(Watch).where(Watch.id == watch_id, Watch.user_id == user.sub))
            if watch is None:
                raise APIError(404, "not_found", "watch not found")
            if watch.kind != "category":
                raise APIError(
                    422, "not_a_category", "the dented filter only applies to a category"
                )
            if watch.status in ("queued", "running"):
                raise APIError(409, "watch_busy", "this watch is being resolved; try again after")
            watch.include_ammaccati = body.include_ammaccati
            db.commit()
            db.refresh(watch)
            return _watch_out(watch)

        @router.delete("/watches/{watch_id}", status_code=204)
        def remove_watch(watch_id: int, user: UserDep, db: SessionDep) -> None:
            watch = db.scalar(select(Watch).where(Watch.id == watch_id, Watch.user_id == user.sub))
            if watch is None:
                raise APIError(404, "not_found", "watch not found")
            db.delete(watch)
            db.commit()
            # The products it delivered stay in the catalog — removing an input has never
            # removed what it found. What must go is their claim to still come from it, or the
            # catalog would keep promising that deleting one of them brings it back (C14).
            bind_forget_source(db, PLUGIN_ID)(user.sub, str(watch_id))
            JobBook(plugin_id=PLUGIN_ID).forget(str(watch_id))

        return router


plugin = DragonStorePlugin()
