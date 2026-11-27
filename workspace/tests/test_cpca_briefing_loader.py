"""Tests for the CPCA briefing read adapter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shared.loaders.cpca_briefing_loader import (
    CONTRACT,
    ENV_VAR,
    SECTION_KEYS,
    CpcaBriefingInvalid,
    CpcaBriefingNotFound,
    get_briefing_path,
    get_cpca_briefing_edition,
    get_cpca_briefing_metric,
    get_cpca_briefing_section,
    get_default_briefing_path,
    get_service_root,
    latest_cpca_briefing,
    load_cpca_briefing,
)


def _metric(value: float = 37.3, estimated: bool = True) -> dict:
    return {
        "value": value,
        "unit": "万辆",
        "yoy_pct": -25.0,
        "estimated": estimated,
        "basis": "由相邻两期累计值及累计同比反推" if estimated else "原文发布",
    }


def _section(key: str, value: float = 37.3) -> dict:
    estimated = key == "week"
    return {
        "key": key,
        "label": key,
        "period": {"start": "2026-11-16", "end": "2026-11-22", "days": 7},
        "metrics": {
            "passenger_retail": _metric(value, estimated=estimated),
            "nev_retail": _metric(value / 2, estimated=estimated),
        },
    }


def _edition(edition_id: str) -> dict:
    return {
        "edition": edition_id,
        "period": {"start": "2026-11-01", "end": edition_id, "days": 22},
        "report_status": "preliminary",
        "source": {
            "publisher": "CPCA",
            "origin": "official",
            "article_id": "4396",
            "title": "test",
            "url": "https://example.com",
            "published_at": "2026-11-25 16:13:47",
            "published_date": "2026-11-25",
        },
        "sections": [
            _section("week"),
            _section("month_to_date", 98.4),
            _section("year_to_date", 1596.2),
        ],
    }


def _briefing(
    *,
    schema_version: str = "1.0",
    contract: str = CONTRACT,
    latest: str = "2026-11-22",
    editions: list[dict] | None = None,
) -> dict:
    if editions is None:
        editions = [_edition("2026-11-22"), _edition("2026-11-15")]
    return {
        "schema_version": schema_version,
        "contract": contract,
        "generated_at": "2026-11-26T00:00:00Z",
        "source": {
            "publisher": "CPCA",
            "data_through": latest,
            "edition_count": len(editions),
        },
        "latest_edition": latest,
        "editions": editions,
    }


def _write(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_default_path_is_sibling_mashang_data(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    path = get_default_briefing_path()
    assert path.name == "briefing.v1.json"
    assert path.parent.name == "cpca"
    assert path.parent.parent.name == "exports"
    assert path.parent.parent.parent.name == "mashang-data"
    assert path.parent.parent.parent.parent == get_service_root().parent


def test_explicit_path_wins(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "from-env.json"))
    target = tmp_path / "explicit.json"
    assert get_briefing_path(target) == target.resolve()


def test_env_override(tmp_path, monkeypatch):
    target = tmp_path / "from-env.json"
    monkeypatch.setenv(ENV_VAR, str(target))
    assert get_briefing_path() == target.resolve()


def test_load_uses_env_override(tmp_path, monkeypatch):
    target = _write(tmp_path / "from-env.json", _briefing())
    monkeypatch.setenv(ENV_VAR, str(target))
    latest = latest_cpca_briefing()
    assert latest["edition"] == "2026-11-22"


def test_relative_env_resolves_against_service_root(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "relative/briefing.json")
    assert get_briefing_path() == (get_service_root() / "relative/briefing.json").resolve()


def test_load_and_latest(tmp_path):
    path = _write(tmp_path / "briefing.json", _briefing())
    data = load_cpca_briefing(path)
    assert data["contract"] == CONTRACT
    assert data["latest_edition"] == "2026-11-22"
    latest = latest_cpca_briefing(path)
    assert latest["edition"] == "2026-11-22"
    assert [section["key"] for section in latest["sections"]] == list(SECTION_KEYS)


def test_missing_file_raises(tmp_path):
    with pytest.raises(CpcaBriefingNotFound, match="make export-cpca-briefing"):
        load_cpca_briefing(tmp_path / "missing.json")


def test_malformed_json_raises(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(CpcaBriefingInvalid, match="无法读取"):
        load_cpca_briefing(path)


def test_non_object_raises(tmp_path):
    path = tmp_path / "briefing.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(CpcaBriefingInvalid, match="顶层必须是对象"):
        load_cpca_briefing(path)


def test_empty_editions_raises(tmp_path):
    data = _briefing(editions=[])
    path = _write(tmp_path / "briefing.json", data)
    with pytest.raises(CpcaBriefingInvalid, match="editions"):
        load_cpca_briefing(path)


def test_unsupported_schema_version_raises(tmp_path):
    path = _write(tmp_path / "briefing.json", _briefing(schema_version="2.0"))
    with pytest.raises(CpcaBriefingInvalid, match="schema_version"):
        load_cpca_briefing(path)


def test_wrong_contract_raises(tmp_path):
    path = _write(tmp_path / "briefing.json", _briefing(contract="other.contract"))
    with pytest.raises(CpcaBriefingInvalid, match="contract"):
        load_cpca_briefing(path)


def test_latest_mismatch_raises(tmp_path):
    data = _briefing()
    data["latest_edition"] = "2026-11-15"
    path = _write(tmp_path / "briefing.json", data)
    with pytest.raises(CpcaBriefingInvalid, match="latest_edition"):
        load_cpca_briefing(path)


def test_edition_lookup(tmp_path):
    path = _write(tmp_path / "briefing.json", _briefing())
    edition = get_cpca_briefing_edition("2026-11-15", path)
    assert edition is not None
    assert edition["edition"] == "2026-11-15"
    assert get_cpca_briefing_edition("2099-01-01", path) is None


def test_section_and_metric_lookup(tmp_path):
    path = _write(tmp_path / "briefing.json", _briefing())
    latest = latest_cpca_briefing(path)

    week = get_cpca_briefing_section(latest, "week")
    assert week is not None
    assert week["key"] == "week"
    assert get_cpca_briefing_section(latest, "missing") is None

    metric = get_cpca_briefing_metric(latest, "week", "passenger_retail")
    assert metric is not None
    assert metric["value"] == 37.3
    assert metric["estimated"] is True
    assert get_cpca_briefing_metric(latest, "week", "missing") is None
    assert get_cpca_briefing_metric(latest, "missing", "passenger_retail") is None


def test_real_export_when_available():
    path = get_default_briefing_path()
    if not path.is_file():
        pytest.skip(f"platform export not present: {path}")
    data = load_cpca_briefing(path)
    latest = data["editions"][0]
    assert latest["edition"] == data["latest_edition"]
    assert data["source"]["data_through"] == data["latest_edition"]
    assert {section["key"] for section in latest["sections"]} <= set(SECTION_KEYS)
    for section in latest["sections"]:
        assert "passenger_retail" in section["metrics"]
        assert "nev_retail" in section["metrics"]
