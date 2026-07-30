"""Title sanitiser for Dragon Store (capabilities.md § Sanitizer del titolo).

Site titles carry commercial / edition labels that are not part of the product
name (e.g. ``"OFFERTA RAVEN PRIME - ..."``, ``"EDIZIONE LIMITATA - ..."``). The
known labels live in a plugin-local JSON (``title_labels.json``), loaded once and
maintained by hand over time. ``sanitize_title`` removes any present label from
the title (case-insensitive) and returns the cleaned title plus the canonical
labels found — the plugin turns those into ``tags``
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
# The same characters as a class, so a label can be recognised at the **edge** of what is left
# of the title even when a previous removal left its separator behind ("AMMACCATO - OFFERTA
# RAVEN PRIME - Name" → " - OFFERTA RAVEN PRIME - Name": still an edge, to a reader).
_EDGE = f"[{re.escape(_TRIM)}]*"


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
    leftover separators/whitespace; internal separators are preserved.

    The match is **anchored to the start or the end** of the title. Counted over 139 real
    cards, all 28 label occurrences sat at the start and none was internal, so anchoring loses
    nothing on real data — and it removes the one defect the free-form match carried: cutting a
    label out of the middle leaves a ``" - - "`` residue behind, because separator trimming only
    applies at the ends. A product whose *name* happens to contain a label word also stops
    being mutilated, which is the case nobody would have noticed until it happened.
    """
    found: list[str] = []
    clean = title
    for label in labels:
        escaped = re.escape(label)
        pattern = re.compile(rf"^{_EDGE}{escaped}|{escaped}{_EDGE}$", re.IGNORECASE)
        if pattern.search(clean):
            clean = pattern.sub(" ", clean)
            if label not in found:
                found.append(label)
    clean = re.sub(r"\s{2,}", " ", clean).strip().strip(_TRIM).strip()
    return clean, found
