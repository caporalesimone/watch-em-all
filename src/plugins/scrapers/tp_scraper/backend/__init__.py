"""TP Scraper — a Test Plugin that exercises the plugin backbone AND seeds fake
products into the catalog for manual QA (multi-store carts, delisting, currency
rules).

It owns two tables (isolated MetaData, CTX-R6): a legacy ``pings`` table that
proves discovery/routing, and ``products`` — fake catalog entries a developer
generates from the plugin page. It is deliberately NOT a scheduled scraper: it
does not implement ``run_for_user``, so ``implements_scraping`` stays ``False``
(no scrape-now endpoints, no schedule editor, the worker ignores it).

Each "add" inserts one random product into its own table and re-delivers the
FULL set through ``update_catalog`` (the sanctioned write path — a scraper never
writes the catalog directly); "remove"/"clear" delete rows and re-deliver, so
the core delists what is gone. "edit" (PATCH) changes a product's price/availability
in the plugin's OWN table only; "simulate scrape" (POST /scrape) then delivers the
current values to the catalog — recording the price/availability changes so the alert
engine has something to diff. Throwaway: delete this folder once real multi-store
scrapers exist.
"""

from __future__ import annotations

import base64
import logging
import random
import re
import secrets
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Integer,
    Numeric,
    String,
    delete,
    func,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from src.core.catalog import update_catalog as _update_catalog_service
from src.core.contracts import DeltaCounters, Product
from src.core.errors import APIError
from src.core.plugins.base import ScraperPlugin
from src.core.plugins.context import PluginContext
from src.web.adjust import run_user_alerts
from src.web.deps import SessionDep, UserDep

PLUGIN_ID = "tp_scraper"
# Native id embedded in the fake product URL, e.g. https://tp.test/p/<seed>.
_SEED_RE = re.compile(r"/p/([0-9a-f]+)")
# Currencies a developer may pick; EUR is the default (matches Dragon so a
# cross-store cart can mix the two). A non-EUR product exercises currency_mismatch.
CURRENCIES = ("EUR", "USD", "GBP", "CHF")

# Word pools for readable random names / brands / categories / tags.
_ADJECTIVES = (
    "Rusty",
    "Shiny",
    "Ancient",
    "Cursed",
    "Golden",
    "Broken",
    "Mighty",
    "Tiny",
    "Cosmic",
    "Feral",
)
_NOUNS = (
    "Goblin",
    "Widget",
    "Amulet",
    "Gizmo",
    "Relic",
    "Sprocket",
    "Totem",
    "Gadget",
    "Orb",
    "Trinket",
)
_BRANDS = ("TP Forge", "TP Labs", "TP Works", "TP Co", "TP Industries")
_CATEGORIES = ("Collectibles", "Gadgets", "Relics", "Toys", "Misc")
_TAGS = ("Nuovo", "Raro", "Ammaccato", "Edizione Limitata", "Offerta", "Usato")
_COLORS = ("#6366f1", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6")


class _Base(DeclarativeBase):
    """The plugin's own metadata, separate from the core schema (CTX-R6)."""


class Ping(_Base):
    __tablename__ = "plugin_tp_scraper_pings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    note: Mapped[str] = mapped_column(String(64), nullable=False, default="hello")


class GeneratedProduct(_Base):
    """A fake product a developer generated (the plugin's own catalog input).
    Delivered to the core as a :class:`Product` on every add/remove/clear."""

    __tablename__ = "plugin_tp_scraper_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    seed: Mapped[str] = mapped_column(String(32), nullable=False)  # drives external_id
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(8192), nullable=True)  # data-uri
    brand_text: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    category: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    price_current: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    price_original: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


def _placeholder_image(color: str) -> str:
    """A tiny inline SVG (base64 data-uri) so the thumbnail is not empty offline."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">'
        f'<rect width="200" height="200" fill="{color}"/>'
        '<text x="100" y="112" font-family="sans-serif" font-size="48" '
        'fill="#ffffff" text-anchor="middle">TP</text></svg>'
    )
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def _random_row(user_id: int, currency: str) -> GeneratedProduct:
    """Build (but do not persist) one random fake product for a user."""
    seed = secrets.token_hex(6)
    name = f"TP - {random.choice(_ADJECTIVES)} {random.choice(_NOUNS)} {random.randint(100, 999)}"
    price = (Decimal(random.randint(500, 50000)) / Decimal(100)).quantize(Decimal("0.01"))
    original: Decimal | None = None
    if random.random() < 0.5:  # ~half the products are on discount
        factor = Decimal(random.randint(110, 150)) / Decimal(100)  # +10%..+50% list price
        original = (price * factor).quantize(Decimal("0.01"))
    return GeneratedProduct(
        user_id=user_id,
        seed=seed,
        url=f"https://tp.test/p/{seed}",
        name=name,
        image_url=_placeholder_image(random.choice(_COLORS)),
        brand_text=random.choice(_BRANDS) if random.random() < 0.8 else None,
        tags=random.sample(_TAGS, k=random.randint(0, 2)),
        category=[
            {"text": "TP", "link": None},
            {"text": random.choice(_CATEGORIES), "link": None},
        ],
        price_current=price,
        price_original=original,
        currency=currency,
        is_available=random.random() < 0.75,  # ~a quarter are out of stock
    )


def _user_rows(db: Session, user_id: int) -> list[GeneratedProduct]:
    return list(
        db.scalars(
            select(GeneratedProduct)
            .where(GeneratedProduct.user_id == user_id)
            .order_by(GeneratedProduct.id.asc())
        )
    )


def _write_context(db: Session) -> PluginContext:
    """A context whose ``update_catalog`` writes through the sanctioned Catalog
    Update Service, bound to this request session and this plugin (mirrors
    ``build_context``'s closure without needing the manifest)."""

    def _update(user_id: int, products: list[Product]) -> DeltaCounters:
        return _update_catalog_service(db, user_id, PLUGIN_ID, products)

    return PluginContext(
        engine=db.get_bind(),  # type: ignore[arg-type]
        db=db,
        logger=logging.getLogger(f"wea.plugin.{PLUGIN_ID}"),
        config={},
        update_catalog=_update,
    )


class GenerateBody(BaseModel):
    currency: str = "EUR"


class EditBody(BaseModel):
    """Edit a product's price and/or availability (dev QA). Fields left unset are kept;
    the change stays in the plugin's own table until a "simulate scrape" delivers it."""

    price_current: Decimal | None = None
    is_available: bool | None = None


class ScrapeResult(BaseModel):
    """What a simulated scrape changed in the catalog (from the Catalog Update Service)."""

    found: int
    new: int
    price_changes: int
    removed: int


class GenProductOut(BaseModel):
    id: int
    name: str
    price_current: Decimal
    price_original: Decimal | None = None
    currency: str
    is_available: bool
    image_url: str | None = None
    tags: list[str] = Field(default_factory=list)


def _out(row: GeneratedProduct) -> GenProductOut:
    return GenProductOut(
        id=row.id,
        name=row.name,
        price_current=row.price_current,
        price_original=row.price_original,
        currency=row.currency,
        is_available=row.is_available,
        image_url=row.image_url,
        tags=list(row.tags or []),
    )


class TpScraperPlugin(ScraperPlugin):
    plugin_id = PLUGIN_ID
    table_metadata = _Base.metadata  # DB-R7: declare the plugin's own schema

    def identity_seed(self, raw: Any) -> str | None:
        # The seed embedded in the fake URL makes external_id stable per product.
        match = _SEED_RE.search(str(raw))
        return match.group(1) if match else None

    def initialize(self, context: PluginContext) -> None:
        _Base.metadata.create_all(context.engine)
        context.logger.info("tp_scraper initialized; own tables ensured")

    def delete_user_data(self, context: PluginContext, user_id: int) -> None:
        context.db.execute(delete(GeneratedProduct).where(GeneratedProduct.user_id == user_id))
        context.db.commit()

    # NOTE: intentionally NO run_for_user — TP is not a scheduled scraper
    # (implements_scraping stays False). The catalog write path below is driven
    # only by the developer-facing routes.

    def _to_product(self, context: PluginContext, row: GeneratedProduct) -> Product:
        """One generated row as a ``Product``, through the base's assembler (SCR-R18).

        This used to be a third hand-written copy of the same construction, complete with the
        comment about `discount_pct` copied verbatim from the Dragon Store — and with
        `scraped_at=now()`, the line PROD-R8 forbids a real scraper. Harmless in a generator
        (these rows *are* produced now), and precisely the line a third scraper would have
        copied from here.

        A generator has no site to read availability from, so it states `is_available` itself:
        the schema.org token is what a real scraper carries, and `InStock`/`OutOfStock` is the
        faithful translation of a boolean this plugin invented.
        """
        tags = self.new_tags()
        for tag in row.tags or []:
            tags.add_tag(tag)
        return self.build_product(
            context,
            raw=row.url,
            url=row.url,
            name=row.name,
            price_current=row.price_current,
            price_original=row.price_original,
            availability="InStock" if row.is_available else "OutOfStock",
            brand_text=row.brand_text,
            image_url=row.image_url,
            currency=row.currency,
            breadcrumb=[(c["text"], c.get("link")) for c in (row.category or [])],
            tags=tags,
            # No `fetched_at`: nothing was fetched. These rows are generated, so "now" is the
            # truth here rather than a shortcut — the one context in which it is.
        )

    def _deliver(self, db: Session, user_id: int) -> DeltaCounters:
        """Re-deliver this user's full generated set; the core inserts the new
        ones, records price/availability changes and delists any that are gone.
        Commits the session (adds/deletes). Returns the delta the service computed."""
        context = _write_context(db)
        products = [self._to_product(context, r) for r in _user_rows(db, user_id)]
        return context.update_catalog(user_id, products)

    def router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/ping")
        def ping() -> dict[str, str]:
            return {"plugin": PLUGIN_ID, "status": "ok"}

        @router.get("/products", response_model=list[GenProductOut])
        def list_products(user: UserDep, db: SessionDep) -> list[GenProductOut]:
            return [_out(r) for r in _user_rows(db, user.sub)]

        @router.post("/products", response_model=GenProductOut, status_code=201)
        def add_product(body: GenerateBody, user: UserDep, db: SessionDep) -> GenProductOut:
            currency = body.currency.strip().upper()
            if currency not in CURRENCIES:
                raise APIError(422, "invalid_currency", f"currency must be one of {CURRENCIES}")
            row = _random_row(user.sub, currency)
            db.add(row)
            db.flush()  # assign row.id before building the response / delivering
            out = _out(row)
            self._deliver(db, user.sub)
            return out

        @router.patch("/products/{product_id}", response_model=GenProductOut)
        def edit_product(
            product_id: int, body: EditBody, user: UserDep, db: SessionDep
        ) -> GenProductOut:
            """Edit a product's price and/or availability in the plugin's own table.
            Does NOT touch the catalog — the change lands there only on a simulated
            scrape (POST /scrape), so a developer can stage a change and then 'scrape'
            it to exercise the alert diff."""
            row = db.scalar(
                select(GeneratedProduct).where(
                    GeneratedProduct.id == product_id, GeneratedProduct.user_id == user.sub
                )
            )
            if row is None:
                raise APIError(404, "not_found", "product not found")
            fields = body.model_fields_set
            if "price_current" in fields and body.price_current is not None:
                if body.price_current <= 0:
                    raise APIError(422, "invalid_price", "price_current must be > 0")
                row.price_current = body.price_current
            if "is_available" in fields and body.is_available is not None:
                row.is_available = body.is_available
            db.commit()
            db.refresh(row)
            return _out(row)

        @router.post("/scrape", response_model=ScrapeResult)
        def scrape(user: UserDep, db: SessionDep) -> ScrapeResult:
            """Simulate a scrape: deliver every product's CURRENT values (including any
            edits) to the catalog through the sanctioned Catalog Update Service, which
            records price/availability changes into the history. Then run the alert engine
            for the user (event-driven alerts) so a digest appears immediately if a cart
            changed — exactly what a real scrape does."""
            delta = self._deliver(db, user.sub)
            run_user_alerts(db, user.sub)
            return ScrapeResult(
                found=delta.found,
                new=delta.new,
                price_changes=delta.price_changes,
                removed=delta.removed,
            )

        @router.delete("/products/{product_id}", status_code=204)
        def remove_product(product_id: int, user: UserDep, db: SessionDep) -> None:
            row = db.scalar(
                select(GeneratedProduct).where(
                    GeneratedProduct.id == product_id, GeneratedProduct.user_id == user.sub
                )
            )
            if row is None:
                raise APIError(404, "not_found", "product not found")
            db.delete(row)
            db.flush()
            self._deliver(db, user.sub)  # the removed product is now delisted

        @router.delete("/products", status_code=204)
        def clear_products(user: UserDep, db: SessionDep) -> None:
            db.execute(delete(GeneratedProduct).where(GeneratedProduct.user_id == user.sub))
            db.flush()
            self._deliver(db, user.sub)  # delivering [] delists them all

        return router


plugin = TpScraperPlugin()
