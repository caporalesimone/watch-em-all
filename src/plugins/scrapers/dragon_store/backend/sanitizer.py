"""Title sanitiser for Dragon Store (capabilities.md § Sanitizer del titolo).

Site titles carry commercial / edition labels that are not part of the product
name (e.g. ``"OFFERTA RAVEN PRIME - ..."``, ``"EDIZIONE LIMITATA - ..."``). The
known labels live in a plugin-local JSON (``title_labels.json``), loaded once and
maintained by hand over time. ``sanitize_title`` removes any present label from
the title (case-insensitive) and returns the cleaned title plus the canonical
labels found — the plugin turns those into ``product_properties`` tags
(PROD-R5 / SCR-R16).

Scraper-specific by design: NOT a core capability. Another scraper may have no
sanitiser at all.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

_LABELS_PATH = Path(__file__).with_name("title_labels.json")
_TRIM = " \t\r\n-–—:|·"


@lru_cache(maxsize=1)
def load_title_labels() -> tuple[str, ...]:
    """The configured title labels, loaded once (admin-viewable; maintained by hand)."""
    try:
        raw = json.loads(_LABELS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    labels = raw.get("title_labels", []) if isinstance(raw, dict) else raw
    return tuple(str(x) for x in labels if str(x).strip())


def sanitize_title(title: str, labels: Iterable[str]) -> tuple[str, list[str]]:
    """Strip known labels from ``title`` (case-insensitive); return
    ``(clean_title, canonical labels found)``. The residual title is trimmed of
    leftover separators/whitespace; internal separators are preserved."""
    found: list[str] = []
    clean = title
    for label in labels:
        pattern = re.compile(re.escape(label), re.IGNORECASE)
        if pattern.search(clean):
            clean = pattern.sub(" ", clean)
            if label not in found:
                found.append(label)
    clean = re.sub(r"\s{2,}", " ", clean).strip().strip(_TRIM).strip()
    return clean, found
