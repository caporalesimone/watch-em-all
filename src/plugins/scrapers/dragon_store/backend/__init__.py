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
from dataclasses import dataclass
from datetime import UTC, datetime
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

from src.core.contracts import Adjustment, BrandRef, CategoryRef, DeltaCounters, Product
from src.core.db import new_session
from src.core.errors import APIError
from src.core.http import RobotsDenied
from src.core.plugins.base import ScraperPlugin
from src.core.plugins.context import PluginContext, bind_upsert_catalog, build_http_client
from src.core.robots import origin_of
from src.web.deps import SessionDep, UserDep
from src.web.jobs import poke

from .adjustments import ADJUSTMENTS
from .parser import (
    DragonStoreChallenge,
    DragonStoreParseError,
    DragonStoreRateLimited,
    DragonStoreSoftError,
    ParsedProduct,
    classify_url,
    parse_product,
)
from .sanitizer import load_title_labels, sanitize_title

if TYPE_CHECKING:
    from decimal import Decimal

    from src.core.models import CatalogProduct

PLUGIN_ID = "dragon_store"
# Native product id in a Dragon Store product URL, e.g. ".../...gp.35880.uw".
_GP_ID_RE = re.compile(r"\.gp\.(\d+)\.uw")
# schema.org availability tokens treated as "orderable now" (PreOrder is buyable).
_AVAILABLE_STATES = frozenset({"InStock", "PreOrder"})
_KNOWN_STATES = frozenset({"InStock", "OutOfStock", "PreOrder"})
_PREORDER_TAG = "Pre Order"
# The interstitial's own checkbox clears the session with this single GET (see the page's
# inline JS); the cleared flag then rides the ASP session cookie the client keeps for the
# run. robots.txt allows crawling here — it publishes no Disallow, only Crawl-delay: 10 —
# so the honest way through is to obey that delay and identify ourselves, which we do.
_SESSION_CLEAR_PATH = "/ajaxRequests.asp?cmd=captcha_check_ok"
_SESSION_CLEAR_HEADERS = {"ReadyAjaxAuth": "readypro"}
_SESSION_CLEAR_OK = "OK"


@dataclass
class _ScrapeOutcome:
    """What a pass over the watches produced, and whether it can be trusted as complete.

    ``complete`` is the whole point: only a run that read every watch may go through
    ``update_catalog``, which delists what it does not see. Anything less goes through
    ``upsert_catalog`` — see CATSVC-R2.
    """

    products: list[Product]
    failed: int
    aborted: bool  # stopped early (rate-limited): the remaining watches were never asked

    @property
    def complete(self) -> bool:
        return not self.aborted and self.failed == 0


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
    # Progress in **requests**, which is where the time goes: 11s of politeness each. The
    # total is known from the first page, which states "N risultati (50 per pagina - K in
    # totale)"; NULL until then, and 1 for a single product.
    progress_done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Cooperative cancellation (9.X6f): a running job reads this at the same checkpoints
    # that write progress. A thread cannot be killed, and does not need to be.
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- what the last scan of this watch yielded (9.F1/9.F3) ---
    products_included: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    products_excluded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def _user_watches(db: Session, user_id: int) -> list[Watch]:
    return list(
        db.scalars(
            select(Watch)
            .where(Watch.user_id == user_id, Watch.kind == "product")
            .order_by(Watch.id.asc())
        )
    )


def _refuse_delisting(user_id: int, products: list[Product]) -> DeltaCounters:
    raise RuntimeError("a single-product delivery must never run the delisting sweep")


def _request_context(db: Session) -> PluginContext:
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
        http=build_http_client(db, PLUGIN_ID, logger),
    )


class WatchIn(BaseModel):
    url: str


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


def _snapshot(product: Product) -> dict[str, Any]:
    """The watch's display snapshot of a scraped product (stored as JSON)."""
    return {
        "name": product.name,
        "image_url": product.image_url,
        "brand": product.brand.model_dump() if product.brand else None,
        "tags": list(product.tags),
        "category": [c.model_dump() for c in product.category],
    }


def _watch_out(watch: Watch) -> WatchOut:
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
        status_detail=watch.status_detail,
        progress_done=watch.progress_done,
        progress_total=watch.progress_total,
    )


def _resolve_watch(plugin: DragonStorePlugin, watch_id: int) -> None:
    """Resolve one freshly added watch, outside the request (9.X6b).

    Runs on its own session: the request's is closed by the time this starts. Every exit
    — success, failure, a site that will not answer — has to leave the row in a terminal
    state, or the page would poll a job that never ends.
    """
    logger = logging.getLogger(f"wea.plugin.{PLUGIN_ID}")
    db = new_session()
    try:
        watch = db.get(Watch, watch_id)
        if watch is None:  # removed while it sat in the queue
            return
        watch.status = "running"
        watch.started_at = datetime.now(UTC)
        db.commit()

        context = _request_context(db)
        product: Product | None = None
        detail: str | None = None
        try:
            product = plugin._scrape_one(context, watch.url)
            if product is None:
                detail = "the site did not return a readable product"
        except DragonStoreRateLimited as exc:
            detail = "the site is rate-limiting us; the next run will fill this in"
            logger.error("dragon_store: could not resolve %s while adding it — %s", watch.url, exc)

        if product is not None:
            # Never the delisting path: one product says nothing about the others.
            context.upsert_catalog(watch.user_id, [product])
            watch.snapshot_json = _snapshot(product)
            watch.products_included = 1
            logger.info(
                "dragon_store: watch %s resolved for user %s and stored in the catalog",
                watch.id,
                watch.user_id,
            )
        else:
            logger.warning(
                "dragon_store: watch %s could not be resolved now — %s", watch.id, detail
            )
        # The watch is kept either way: "we could not read it" is not "it is not there",
        # and the next scheduled run will try again.
        watch.status = "ready" if product is not None else "failed"
        watch.status_detail = detail
        watch.progress_done = 1
        watch.finished_at = datetime.now(UTC)
        watch.last_scanned_at = watch.finished_at
        db.commit()
    except Exception:  # background task: log it, there is no response to fail
        logger.exception("dragon_store: resolving watch %s crashed", watch_id)
        db.rollback()
        _mark_failed(db, watch_id, "an internal error stopped this; the next run will retry")
    finally:
        db.close()


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

    def get_adjustments(
        self, products: list[CatalogProduct], cart_total: Decimal
    ) -> list[Adjustment]:
        # DRG-R5: a non-cumulative threshold discount + shipping (free above a threshold),
        # applied to the cart's discounted total. Rules live in adjustments.py.
        return ADJUSTMENTS.compute(cart_total)

    # --- scraping (SCR-R4/R5/R6): one HTTP request per watch, via context.http ---
    def _scrape_products(self, context: PluginContext, urls: list[str]) -> _ScrapeOutcome:
        by_id: dict[str, Product] = {}  # dedup on external_id (PROD-R3)
        failed = 0
        for index, url in enumerate(urls):
            try:
                product = self._scrape_one(context, url)
            except DragonStoreRateLimited as exc:
                # The site is explicitly telling us to slow down. Carrying on through the
                # remaining watches is what got us throttled in the first place.
                remaining = len(urls) - index
                context.logger.error(
                    "dragon_store: rate-limited by the site (%s) — aborting this run with "
                    "%s of %s watch(es) unread; they are deliberately not attempted",
                    exc,
                    remaining,
                    len(urls),
                )
                return _ScrapeOutcome(list(by_id.values()), failed + remaining, aborted=True)
            if product is None:
                failed += 1
            else:
                by_id[product.external_id] = product
        return _ScrapeOutcome(list(by_id.values()), failed, aborted=False)

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
            raise
        except DragonStoreSoftError as exc:
            context.http.forget(url)
            context.logger.error("dragon_store: %s", exc)
            return None
        except DragonStoreParseError as exc:
            context.logger.error("dragon_store: parse failed for %s: %s", url, exc)
            return None
        return self._to_product(context, url, parsed, response.fetched_at)

    def _to_product(
        self,
        context: PluginContext,
        url: str,
        parsed: ParsedProduct,
        fetched_at: datetime | None = None,
    ) -> Product:
        clean_name, labels = sanitize_title(parsed.name, load_title_labels())
        tags = self.new_tags()
        for label in labels:
            tags.add_tag(label)

        if parsed.availability and parsed.availability not in _KNOWN_STATES:
            context.logger.warning(
                "dragon_store: unknown availability %r for %s", parsed.availability, url
            )
        is_available = parsed.availability in _AVAILABLE_STATES
        if parsed.availability == "PreOrder":
            tags.add_tag(_PREORDER_TAG)

        category = self.new_category()
        for crumb_name, crumb_url in parsed.breadcrumb:
            category.add_child(crumb_name, crumb_url)

        brand = (
            BrandRef(text=parsed.brand_text, link=parsed.brand_link) if parsed.brand_text else None
        )
        extra = {
            key: value
            for key, value in {
                "sku": parsed.sku,
                "price_valid_until": parsed.price_valid_until,
                "category": parsed.category,
                "description": parsed.description,
            }.items()
            if value is not None
        }
        return Product(
            plugin_id=PLUGIN_ID,
            external_id=self.external_id_for(raw=url, url=url),
            url=url,
            name=clean_name or parsed.name,  # fall back if the title was all label
            image_url=parsed.image_url,
            brand=brand,
            tags=tags.get_tags(),
            category=category.get_path(),
            price_current=parsed.price_current,
            price_original=parsed.price_original,
            discount_pct=None,  # the core derives it from original/current (CATSVC)
            currency=parsed.currency,
            is_available=is_available,
            # When the *site* answered: the cache's own timestamp on a hit, the clock on a
            # real fetch. Stamping "now" either way would date a 12-hour-old page to today.
            scraped_at=fetched_at or datetime.now(UTC),
            extra=extra,
        )

    # --- runtime (SCR-R4/R5) ---
    def run_for_user(self, context: PluginContext, user_id: int) -> DeltaCounters:
        watches = _user_watches(context.db, user_id)
        if not watches:
            # No watches != "site returned nothing": deliver nothing, do NOT delist.
            context.logger.info("dragon_store: user %s has no watches — nothing to do", user_id)
            return DeltaCounters()

        context.logger.info(
            "dragon_store: starting run for user %s — %s watch(es)", user_id, len(watches)
        )
        outcome = self._scrape_products(context, [w.url for w in watches])
        # Refresh each watch's display snapshot from this run; the catalog write below
        # commits this session, persisting these too.
        by_url = {p.url: p for p in outcome.products}
        for watch in watches:
            product = by_url.get(watch.url)
            if product is not None:
                watch.snapshot_json = _snapshot(product)

        context.logger.info(
            "dragon_store: run for user %s read %s of %s watch(es) — %s HTTP request(s), "
            "%s cache hit(s)",
            user_id,
            len(outcome.products),
            len(watches),
            context.http.request_count,
            context.http.cache_hits,
        )
        if outcome.complete:
            return context.update_catalog(user_id, outcome.products)

        # Incomplete: we cannot tell "gone from the site" from "we could not read it", so
        # the delisting sweep must not run (CATSVC-R2). Anything else would wipe the user's
        # catalog for this scraper on any gate or outage.
        context.logger.error(
            "dragon_store: incomplete run for user %s (%s watch(es) unread%s) — delivering "
            "%s product(s) WITHOUT delisting; the catalog keeps its current state",
            user_id,
            outcome.failed,
            ", aborted early" if outcome.aborted else "",
            len(outcome.products),
        )
        return context.upsert_catalog(user_id, outcome.products)

    # --- routes: watches CRUD (per-user) ---
    def router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/watches", response_model=list[WatchOut])
        def list_watches(user: UserDep, db: SessionDep) -> list[WatchOut]:
            out = []
            for watch in _user_watches(db, user.sub):
                item = _watch_out(watch)
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
            if kind == "category":
                # Recognised, and refused until 9.B2/9.B3 can read one: a queued category
                # would be a job nothing is able to resolve.
                raise APIError(422, "unsupported_url", "category watches are not available yet")

            watch = Watch(
                user_id=user.sub,
                kind=kind,
                url=url,
                status="queued",
                queued_at=datetime.now(UTC),
                progress_total=1,  # one product page, one request
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

        @router.delete("/watches/{watch_id}", status_code=204)
        def remove_watch(watch_id: int, user: UserDep, db: SessionDep) -> None:
            watch = db.scalar(select(Watch).where(Watch.id == watch_id, Watch.user_id == user.sub))
            if watch is None:
                raise APIError(404, "not_found", "watch not found")
            db.delete(watch)
            db.commit()

        return router


plugin = DragonStorePlugin()
