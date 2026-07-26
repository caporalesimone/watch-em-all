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
``run_test`` is a dry-run: it scrapes the same way but writes nothing (SCR-R11).

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
from sqlalchemy import JSON, DateTime, Integer, String, delete, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from src.core.contracts import Adjustment, BrandRef, CategoryRef, DeltaCounters, Product
from src.core.errors import APIError
from src.core.http import RobotsDenied
from src.core.plugins.base import ScraperPlugin
from src.core.plugins.context import PluginContext, bind_upsert_catalog, build_http_client
from src.core.robots import origin_of
from src.web.deps import SessionDep, UserDep

from .adjustments import ADJUSTMENTS
from .parser import (
    DragonStoreChallenge,
    DragonStoreParseError,
    DragonStoreRateLimited,
    DragonStoreSoftError,
    ParsedProduct,
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
    """A user's product watch (its input — SCR-R1). Phase 3: kind=product only."""

    __tablename__ = "plugin_dragon_store_watches"

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


def _user_watches(db: Session, user_id: int) -> list[Watch]:
    return list(
        db.scalars(
            select(Watch)
            .where(Watch.user_id == user_id, Watch.kind == "product")
            .order_by(Watch.id.asc())
        )
    )


def _no_write(user_id: int, products: list[Product]) -> DeltaCounters:
    raise RuntimeError("run_test must not write to the catalog")


def _request_context(db: Session, *, upsert: bool) -> PluginContext:
    """A context for a scrape driven by a web request, outside a scheduled run.

    The HTTP client comes from :func:`build_http_client`, so these paths get the same
    politeness, timeout, ``robots.txt`` compliance and scrape cache as a scheduled run —
    a hand-rolled client here would quietly ignore the admin config, which is precisely
    the sort of gap that gets a scraper rate-limited.

    ``update_catalog`` is always refused: a single-product delivery must never trigger the
    delisting sweep. ``upsert`` decides whether the product may be *stored* — true when a
    user adds a watch (they asked for it in their catalog), false for the dry-run test.
    """
    logger = logging.getLogger(f"wea.plugin.{PLUGIN_ID}")
    return PluginContext(
        engine=db.get_bind(),  # type: ignore[arg-type]
        db=db,
        logger=logger,
        config={},
        update_catalog=_no_write,
        upsert_catalog=bind_upsert_catalog(db) if upsert else _no_write,
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
    )


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
        return self._to_product(context, url, parsed)

    def _to_product(self, context: PluginContext, url: str, parsed: ParsedProduct) -> Product:
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
            scraped_at=datetime.now(UTC),
            extra=extra,
        )

    # --- runtime (SCR-R4/R5/R11) ---
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

    def run_test(self, context: PluginContext, params: dict[str, Any]) -> list[Product]:
        url = str(params.get("url", "")).strip()
        if not url:
            return []
        try:
            product = self._scrape_one(context, url)
        except DragonStoreRateLimited as exc:
            context.logger.error("dragon_store: test scrape of %s rate-limited (%s)", url, exc)
            return []
        return [product] if product is not None else []

    # --- routes: watches CRUD + dry-run test (per-user) ---
    def router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/watches", response_model=list[WatchOut])
        def list_watches(user: UserDep, db: SessionDep) -> list[WatchOut]:
            return [_watch_out(w) for w in _user_watches(db, user.sub)]

        @router.post("/watches", response_model=WatchOut, status_code=201)
        def add_watch(body: WatchIn, user: UserDep, db: SessionDep) -> WatchOut:
            url = body.url.strip()
            if not url:
                raise APIError(422, "invalid_url", "url must not be empty")
            already = db.scalar(select(Watch).where(Watch.user_id == user.sub, Watch.url == url))
            if already is not None:
                raise APIError(409, "duplicate_watch", "this URL is already watched")
            # One scrape, one purpose: adding a watch both resolves the product and puts it
            # in the catalog. It used to fill only the display snapshot, so the user had to
            # wait for a scheduled run — or press Scrape now — before seeing a price: two
            # rounds of requests to the site for a single intention. The watch stays valid
            # even when the scrape fails; the next run fills it in.
            context = _request_context(db, upsert=True)
            try:
                product = self._scrape_one(context, url)
            except DragonStoreRateLimited as exc:
                context.logger.error(
                    "dragon_store: could not resolve %s while adding the watch — %s", url, exc
                )
                product = None

            watch = Watch(
                user_id=user.sub,
                kind="product",
                url=url,
                snapshot_json=_snapshot(product) if product else None,
            )
            db.add(watch)
            db.commit()
            if product is not None:
                # Never the delisting path: one product says nothing about the others.
                context.upsert_catalog(user.sub, [product])
                context.logger.info(
                    "dragon_store: watch %s added for user %s and stored in the catalog",
                    watch.id,
                    user.sub,
                )
            else:
                context.logger.warning(
                    "dragon_store: watch %s added for user %s but the product could not be "
                    "read now — it will be filled in by the next run",
                    watch.id,
                    user.sub,
                )
            return _watch_out(watch)

        @router.delete("/watches/{watch_id}", status_code=204)
        def remove_watch(watch_id: int, user: UserDep, db: SessionDep) -> None:
            watch = db.scalar(select(Watch).where(Watch.id == watch_id, Watch.user_id == user.sub))
            if watch is None:
                raise APIError(404, "not_found", "watch not found")
            db.delete(watch)
            db.commit()

        @router.post("/test", response_model=list[Product])
        def test(body: WatchIn, user: UserDep, db: SessionDep) -> list[Product]:
            # Dry run (SCR-R11): scrapes exactly like a real run, writes nothing at all.
            return self.run_test(_request_context(db, upsert=False), {"url": body.url})

        return router


plugin = DragonStorePlugin()
