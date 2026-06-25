"""Scrape response cache (CTX-R9, 4.B8): a thin, swappable read-through cache backing
``context.http``.

The class below is the **seam**: today it is Postgres-backed (the ``scrape_cache`` table);
a Redis backend would be a localized replacement of this one module, leaving ``HttpClient``
and the runner untouched. ``ttl_min <= 0`` disables the cache (no read, no write). Only
``GET`` is cached (POST never is — enforced by the caller). Cache failures degrade to a
miss/no-op: a cache problem must never break a scrape.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from src.core.db import new_session
from src.core.models import ScrapeCache as ScrapeCacheRow

# Default half-life until the per-plugin admin config (4.B10, cache_ttl_min) overrides it.
DEFAULT_CACHE_TTL_MIN = 60


@dataclass(frozen=True)
class CachedResponse:
    """A cache hit, enough to rebuild an ``HttpResponse`` (status + body + content-type)."""

    status_code: int
    content: bytes
    content_type: str | None


def _normalize_url(url: str) -> str:
    """Lowercase scheme/host, sort the query params, drop the fragment (CTX-R9)."""
    parts = urlsplit(url)
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, query, ""))


def cache_key(plugin_id: str, method: str, url: str) -> str:
    """sha256 of the normalised request, scoped to the plugin (CTX-R9)."""
    raw = f"{plugin_id}\n{method.upper()}\n{_normalize_url(url)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def purge_expired(session: Session, plugin_id: str, now: datetime | None = None) -> int:
    """Delete this plugin's **expired** cache rows (POOL-R3: run-start cleanup). Returns the
    number removed. Commits."""
    cutoff = now if now is not None else datetime.now(UTC)
    res = session.execute(
        delete(ScrapeCacheRow).where(
            ScrapeCacheRow.plugin_id == plugin_id, ScrapeCacheRow.expires_at <= cutoff
        )
    )
    session.commit()
    return int(getattr(res, "rowcount", 0) or 0)


def clear(session: Session, plugin_id: str) -> int:
    """Delete **all** cache rows for a plugin (manual *Svuota cache*, 4.B9). Returns the
    number removed. Commits."""
    res = session.execute(delete(ScrapeCacheRow).where(ScrapeCacheRow.plugin_id == plugin_id))
    session.commit()
    return int(getattr(res, "rowcount", 0) or 0)


def _aware(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; treat a naive value as UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


class ScrapeCache:
    """Per-plugin read-through cache over the ``scrape_cache`` table. Uses its own
    short-lived session per op so a cache write commits independently of the catalog
    transaction. All errors are swallowed (degrade to miss/no-op)."""

    def __init__(
        self, engine: Engine, plugin_id: str, ttl_min: int = DEFAULT_CACHE_TTL_MIN
    ) -> None:
        self._engine = engine
        self._plugin_id = plugin_id
        self._ttl_min = ttl_min

    @property
    def enabled(self) -> bool:
        return self._ttl_min > 0

    def get(self, method: str, url: str) -> CachedResponse | None:
        """Return a non-expired hit for this (plugin, method, url), else ``None``."""
        if not self.enabled:
            return None
        key = cache_key(self._plugin_id, method, url)
        try:
            session = new_session()
            try:
                row = session.scalar(
                    select(ScrapeCacheRow).where(
                        ScrapeCacheRow.plugin_id == self._plugin_id,
                        ScrapeCacheRow.cache_key == key,
                    )
                )
                if row is None or _aware(row.expires_at) <= datetime.now(UTC):
                    return None
                meta = row.response_meta_json or {}
                return CachedResponse(
                    status_code=int(meta.get("status", 200)),
                    content=bytes(row.response_body),
                    content_type=meta.get("content_type"),
                )
            finally:
                session.close()
        except Exception:
            return None

    def put(
        self, method: str, url: str, status_code: int, content: bytes, content_type: str | None
    ) -> None:
        """Store/refresh the cached response with a fresh expiry (now + half-life)."""
        if not self.enabled:
            return
        key = cache_key(self._plugin_id, method, url)
        now = datetime.now(UTC)
        meta = {"status": status_code, "content_type": content_type}
        try:
            session = new_session()
            try:
                row = session.scalar(
                    select(ScrapeCacheRow).where(
                        ScrapeCacheRow.plugin_id == self._plugin_id,
                        ScrapeCacheRow.cache_key == key,
                    )
                )
                if row is None:
                    session.add(
                        ScrapeCacheRow(
                            plugin_id=self._plugin_id,
                            cache_key=key,
                            response_body=content,
                            response_meta_json=meta,
                            fetched_at=now,
                            expires_at=now + timedelta(minutes=self._ttl_min),
                        )
                    )
                else:
                    row.response_body = content
                    row.response_meta_json = meta
                    row.fetched_at = now
                    row.expires_at = now + timedelta(minutes=self._ttl_min)
                session.commit()
            finally:
                session.close()
        except Exception:
            return
