"""Dragon Store scraper — phase-3 MOCK (3.B8/3.B9).

Real identity, fake content: ``run_for_user`` / ``run_test`` return hardcoded
products derived from each watch URL. The native id (``.gp.<id>.uw``) drives
``external_id`` through the base identity template-method (stable across runs);
everything else is invented so the catalog → Product-Picker flow can be exercised
end-to-end before the real parser lands (PR3, 3.B6/3.B7). Watches are product
URLs only (``kind=product``); categories arrive in phase 9.

The write path is the ``context.update_catalog`` callback inside
``run_for_user`` — the scraper never writes the catalog itself. ``run_test`` is a
dry-run: it builds the same products but writes nothing (SCR-R11).
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import DateTime, Integer, String, delete, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from src.core.contracts import DeltaCounters, Product
from src.core.errors import APIError
from src.core.plugins.base import ScraperPlugin
from src.core.plugins.context import PluginContext
from src.web.deps import SessionDep, UserDep

PLUGIN_ID = "dragon_store"
# Native product id in a Dragon Store product URL, e.g. ".../...gp.35880.uw".
_GP_ID_RE = re.compile(r"\.gp\.(\d+)\.uw")


class _Base(DeclarativeBase):
    """Dragon Store's own metadata, separate from the core schema (CTX-R6)."""


class Watch(_Base):
    """A user's product watch (its input — SCR-R1). Phase 3: kind=product only."""

    __tablename__ = "plugin_dragon_store_watches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="product")
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
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


class WatchIn(BaseModel):
    url: str


class WatchOut(BaseModel):
    id: int
    kind: str
    url: str


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

    # --- mock product building (real identity, fake content) ---
    def _mock_product(self, url: str, external_id: str) -> Product:
        # Deterministic fake fields from the (stable) external_id, so re-runs are
        # idempotent — no spurious price-change history (CATSVC-R4).
        n = int(external_id, 16)
        current = Decimal(10 + n % 90) + Decimal("0.99")
        original = (current * Decimal("1.30")).quantize(Decimal("0.01"))
        gp = _GP_ID_RE.search(url)
        label = gp.group(1) if gp else "?"
        return Product(
            plugin_id=PLUGIN_ID,
            external_id=external_id,
            url=url,
            name=f"[MOCK] Dragon Store product {label}",
            image_url=None,
            price_current=current,
            price_original=original,
            discount_pct=None,  # let the core derive it from original/current
            currency="EUR",
            is_available=True,
            scraped_at=datetime.now(UTC),
            extra={"mock": True, "source_url": url},
        )

    def _build_products(self, urls: list[str]) -> list[Product]:
        # external_id via the base template-method; dedup on it (PROD-R3).
        by_id: dict[str, Product] = {}
        for url in urls:
            external_id = self.external_id_for(raw=url, url=url)
            by_id[external_id] = self._mock_product(url, external_id)
        return list(by_id.values())

    # --- runtime (SCR-R4/R5/R11) ---
    def run_for_user(self, context: PluginContext, user_id: int) -> DeltaCounters:
        urls = [w.url for w in _user_watches(context.db, user_id)]
        if not urls:
            # No watches != "site returned nothing": deliver nothing, do NOT delist.
            return DeltaCounters()
        return context.update_catalog(user_id, self._build_products(urls))

    def run_test(self, context: PluginContext, params: dict[str, Any]) -> list[Product]:
        url = str(params.get("url", "")).strip()
        return self._build_products([url]) if url else []

    # --- routes: watches CRUD + dry-run test (per-user) ---
    def router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/watches", response_model=list[WatchOut])
        def list_watches(user: UserDep, db: SessionDep) -> list[WatchOut]:
            return [WatchOut(id=w.id, kind=w.kind, url=w.url) for w in _user_watches(db, user.sub)]

        @router.post("/watches", response_model=WatchOut, status_code=201)
        def add_watch(body: WatchIn, user: UserDep, db: SessionDep) -> WatchOut:
            url = body.url.strip()
            if not url:
                raise APIError(422, "invalid_url", "url must not be empty")
            watch = Watch(user_id=user.sub, kind="product", url=url)
            db.add(watch)
            db.commit()
            return WatchOut(id=watch.id, kind=watch.kind, url=watch.url)

        @router.delete("/watches/{watch_id}", status_code=204)
        def remove_watch(watch_id: int, user: UserDep, db: SessionDep) -> None:
            watch = db.scalar(select(Watch).where(Watch.id == watch_id, Watch.user_id == user.sub))
            if watch is None:
                raise APIError(404, "not_found", "watch not found")
            db.delete(watch)
            db.commit()

        @router.post("/test", response_model=list[Product])
        def test(body: WatchIn, user: UserDep, db: SessionDep) -> list[Product]:
            ctx = PluginContext(
                engine=db.get_bind(),  # type: ignore[arg-type]
                db=db,
                logger=logging.getLogger(f"wea.plugin.{PLUGIN_ID}"),
                config={},
                update_catalog=_no_write,  # dry-run: writing is a bug
            )
            return self.run_test(ctx, {"url": body.url})

        return router


plugin = DragonStorePlugin()
