"""Tests for the plugin manifest parser (2.B1)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.core.plugins.manifest import (
    CORE_PLUGIN_API_VERSION,
    ManifestError,
    parse_manifest,
)


def _valid_scraper() -> dict[str, Any]:
    return {
        "name": "tp_scraper",
        "display_name": "TP Scraper",
        "type": "scraper",
        "version": "1.0.0",
        "api_version": CORE_PLUGIN_API_VERSION,
        "enabled": True,
        "icon": "frontend/assets/icon.svg",
        "backend": {"entry": "backend/__init__.py"},
        "frontend": {
            "entry": "frontend/index.ts",
            "route_base": "/plugins/tp-scraper",
            "i18n": "frontend/i18n",
        },
    }


def _valid_notifier() -> dict[str, Any]:
    return {
        "name": "tp_notifier",
        "display_name": "TP Notifier",
        "type": "notifier",
        "version": "1.0.0",
        "api_version": CORE_PLUGIN_API_VERSION,
        "enabled": True,
        "backend": {"entry": "backend/__init__.py", "i18n": "backend/i18n"},
    }


def _write(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_parses_valid_scraper(tmp_path: Path) -> None:
    manifest = parse_manifest(_write(tmp_path, _valid_scraper()), folder_type="scraper")
    assert manifest.name == "tp_scraper"
    assert manifest.type == "scraper"
    assert manifest.frontend is not None
    assert manifest.frontend.route_base == "/plugins/tp-scraper"


def test_parses_valid_notifier_without_frontend(tmp_path: Path) -> None:
    manifest = parse_manifest(_write(tmp_path, _valid_notifier()), folder_type="notifier")
    assert manifest.name == "tp_notifier"
    assert manifest.type == "notifier"
    assert manifest.frontend is None
    assert manifest.backend.i18n == "backend/i18n"


def test_rejects_type_folder_mismatch(tmp_path: Path) -> None:
    path = _write(tmp_path, _valid_scraper())  # declares type=scraper
    with pytest.raises(ManifestError, match="does not match its folder"):
        parse_manifest(path, folder_type="notifier")


def test_rejects_incompatible_api_version(tmp_path: Path) -> None:
    data = _valid_scraper()
    data["api_version"] = CORE_PLUGIN_API_VERSION + 1
    with pytest.raises(ManifestError, match="api_version"):
        parse_manifest(_write(tmp_path, data), folder_type="scraper")


def test_rejects_non_snake_case_name(tmp_path: Path) -> None:
    data = _valid_scraper()
    data["name"] = "TP-Scraper"
    with pytest.raises(ManifestError, match="snake_case"):
        parse_manifest(_write(tmp_path, data), folder_type="scraper")


def test_rejects_non_kebab_route_base(tmp_path: Path) -> None:
    data = _valid_scraper()
    data["frontend"]["route_base"] = "/plugins/TP_Scraper"
    with pytest.raises(ManifestError, match="route_base"):
        parse_manifest(_write(tmp_path, data), folder_type="scraper")


def test_rejects_route_base_without_plugins_prefix(tmp_path: Path) -> None:
    data = _valid_scraper()
    data["frontend"]["route_base"] = "/tp-scraper"
    with pytest.raises(ManifestError, match="route_base"):
        parse_manifest(_write(tmp_path, data), folder_type="scraper")


def test_rejects_missing_backend_entry(tmp_path: Path) -> None:
    data = _valid_scraper()
    del data["backend"]["entry"]
    with pytest.raises(ManifestError, match="invalid"):
        parse_manifest(_write(tmp_path, data), folder_type="scraper")


def test_rejects_unknown_top_level_field(tmp_path: Path) -> None:
    data = _valid_scraper()
    data["enbaled"] = True  # typo of `enabled`
    with pytest.raises(ManifestError, match="invalid"):
        parse_manifest(_write(tmp_path, data), folder_type="scraper")


def test_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text("{ not valid json", encoding="utf-8")
    with pytest.raises(ManifestError, match="not valid JSON"):
        parse_manifest(path, folder_type="scraper")


def test_rejects_non_object_json(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ManifestError, match="must be a JSON object"):
        parse_manifest(path, folder_type="scraper")


def test_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match="cannot read manifest"):
        parse_manifest(tmp_path / "nope.json", folder_type="scraper")
