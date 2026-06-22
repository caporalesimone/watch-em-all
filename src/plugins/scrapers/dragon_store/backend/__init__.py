"""Dragon Store scraper — real scraping (3.B6/3.B7).

One HTTP request per product watch (``kind=product``) via ``context.http``; the
page is parsed by :mod:`parser` (JSON-LD ``Product`` primary, DOM list price) and
the title is cleaned by :mod:`sanitizer` (marketing/edition labels become
``product_properties`` tags). The native id (``.gp.<id>.uw``) drives
``external_id`` through the base identity template-method (stable across runs).
Categories, pagination and the "ammaccato" filter are phase 9.

The write path is the ``context.update_catalog`` callback inside
``run_for_user`` — the scraper never writes the catalog itself. ``run_test`` is a
dry-run: it scrapes the same way but writes nothing (SCR-R11).
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import JSON, DateTime, Integer, String, delete, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from src.core.contracts import BrandRef, CategoryRef, DeltaCounters, Product
from src.core.errors import APIError
from src.core.plugins.base import ScraperPlugin
from src.core.plugins.context import PluginContext
from src.web.deps import SessionDep, UserDep

from .parser import DragonStoreParseError, ParsedProduct, parse_product
from .sanitizer import load_title_labels, sanitize_title

PLUGIN_ID = "dragon_store"
# Native product id in a Dragon Store product URL, e.g. ".../...gp.35880.uw".
_GP_ID_RE = re.compile(r"\.gp\.(\d+)\.uw")
# schema.org availability tokens treated as "orderable now" (PreOrder is buyable).
_AVAILABLE_STATES = frozenset({"InStock", "PreOrder"})
_KNOWN_STATES = frozenset({"InStock", "OutOfStock", "PreOrder"})
_PREORDER_PROPERTY = "Pre Order"


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
    # product_properties, category) — set by a one-off scrape on add and refreshed
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


def _dry_context(db: Session) -> PluginContext:
    """A context for a read-only scrape (dry-run / add-time title resolution): a real
    HTTP client, but writing to the catalog is a bug (``_no_write``)."""
    return PluginContext(
        engine=db.get_bind(),  # type: ignore[arg-type]
        db=db,
        logger=logging.getLogger(f"wea.plugin.{PLUGIN_ID}"),
        config={},
        update_catalog=_no_write,
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
    product_properties: list[str] = Field(default_factory=list)
    category: list[CategoryRef] = Field(default_factory=list)


def _snapshot(product: Product) -> dict[str, Any]:
    """The watch's display snapshot of a scraped product (stored as JSON)."""
    return {
        "name": product.name,
        "image_url": product.image_url,
        "brand": product.brand.model_dump() if product.brand else None,
        "product_properties": list(product.product_properties),
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
        product_properties=snap.get("product_properties") or [],
        category=snap.get("category") or [],
    )


class DragonStorePlugin(ScraperPlugin):
    plugin_id = PLUGIN_ID

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

    # --- scraping (SCR-R4/R5/R6): one HTTP request per watch, via context.http ---
    def _scrape_products(self, context: PluginContext, urls: list[str]) -> list[Product]:
        by_id: dict[str, Product] = {}  # dedup on external_id (PROD-R3)
        for url in urls:
            product = self._scrape_one(context, url)
            if product is not None:
                by_id[product.external_id] = product
        return list(by_id.values())

    def _scrape_one(self, context: PluginContext, url: str) -> Product | None:
        """Fetch + parse one product page; ``None`` (logged) on any failure, so a
        single bad page never aborts the whole run."""
        try:
            response = context.http.get(url)
        except OSError as exc:  # network/timeout after retries
            context.logger.warning("dragon_store: fetch failed for %s: %s", url, exc)
            return None
        if response.status_code != 200:
            context.logger.warning("dragon_store: %s returned HTTP %s", url, response.status_code)
            return None
        try:
            parsed = parse_product(response.content, url)
        except DragonStoreParseError as exc:
            context.logger.warning("dragon_store: parse failed for %s: %s", url, exc)
            return None
        return self._to_product(context, url, parsed)

    def _to_product(self, context: PluginContext, url: str, parsed: ParsedProduct) -> Product:
        clean_name, labels = sanitize_title(parsed.name, load_title_labels())
        props = self.new_properties()
        for label in labels:
            props.add_property(label)

        if parsed.availability and parsed.availability not in _KNOWN_STATES:
            context.logger.warning(
                "dragon_store: unknown availability %r for %s", parsed.availability, url
            )
        is_available = parsed.availability in _AVAILABLE_STATES
        if parsed.availability == "PreOrder":
            props.add_property(_PREORDER_PROPERTY)

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
            product_properties=props.get_properties(),
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
            return DeltaCounters()
        products = self._scrape_products(context, [w.url for w in watches])
        # Refresh each watch's display snapshot from this run; the update_catalog
        # call below commits this session, persisting these too.
        by_url = {p.url: p for p in products}
        for watch in watches:
            product = by_url.get(watch.url)
            if product is not None:
                watch.snapshot_json = _snapshot(product)
        return context.update_catalog(user_id, products)

    def run_test(self, context: PluginContext, params: dict[str, Any]) -> list[Product]:
        url = str(params.get("url", "")).strip()
        if not url:
            return []
        product = self._scrape_one(context, url)
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
            # The scraper intervenes once here to resolve the product title (best-effort,
            # no catalog write); the watch stays valid even if the fetch fails.
            product = self._scrape_one(_dry_context(db), url)
            watch = Watch(
                user_id=user.sub,
                kind="product",
                url=url,
                snapshot_json=_snapshot(product) if product else None,
            )
            db.add(watch)
            db.commit()
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
            return self.run_test(_dry_context(db), {"url": body.url})

        return router


plugin = DragonStorePlugin()
