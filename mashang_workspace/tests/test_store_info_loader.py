"""Tests: store_info_schema.json + store_info_loader（门店/经销商主数据）。

数据相关断言在外部 CSV 存在时执行；缺失时跳过（CI 不依赖本机 original 目录）。
"""

import json
from pathlib import Path

import pytest

_PRJ = Path(__file__).resolve().parents[2]
_SCHEMA = _PRJ / "shared" / "schema" / "store_info_schema.json"
_SCHEMA_MD = _PRJ / "shared" / "schema" / "schema.md"
_DATA_PATH_MD = _PRJ / "shared" / "schema" / "data_path.md"

from shared.loaders import store_info_loader as sl

REQUIRED_COLUMNS = {
    "Bloc Name": "经销商集团/投资人名称",
    "Dealer Name Fc": "门店名",
    "Dealer Code": "门店业务代码（主键）",
    "Dealer_type": "门店业态",
    "City Name": "城市",
    "Province Name": "省份",
    "Region Name": "大区",
    "Store Create Status Desc": "门店状态",
}
EXPECTED_FIELDS = [
    "bloc_name", "dealer_type", "region_name", "city_name", "dealer_code", "dealer_name_fc",
]


def test_schema_json_exists_and_valid():
    assert _SCHEMA.exists()
    data = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    assert data["table"] == "store_info"
    assert data["grain"]["key"] == "Dealer Code"
    cols = {c["field"]: c for c in data["columns"]}
    for col, semantic_kw in REQUIRED_COLUMNS.items():
        assert col in cols, f"missing column doc: {col}"
        assert semantic_kw in cols[col]["semantic"] or col in cols[col].get("aliases", [])
    # Bloc Name 应标注经销商集团/聚合用途
    assert "bloc" in json.dumps(cols["Bloc Name"], ensure_ascii=False).lower()


def test_schema_registered_in_schema_md():
    text = _SCHEMA_MD.read_text(encoding="utf-8")
    assert "store_info_schema.json" in text
    assert "Bloc Name" in text and "Dealer Name Fc" in text and "Dealer Code" in text


def test_schema_registered_in_data_path_md():
    text = _DATA_PATH_MD.read_text(encoding="utf-8")
    assert "门店信息" in text
    assert "store_info_loader" in text or "store_info_schema.json" in text


def _has_csv():
    return sl.get_store_info_csv_path() is not None


@pytest.mark.skipif(not _has_csv(), reason="本机 external store_info.csv 不存在")
def test_load_store_info_summary():
    s = sl.summary()
    assert s["loaded"] is True
    assert s["rows"] > 1000
    assert s["unique_blocs"] > 100
    assert s["unique_store_names"] > 500
    assert s["unique_codes"] == s["rows"]


@pytest.mark.skipif(not _has_csv(), reason="本机 external store_info.csv 不存在")
def test_dealer_type_and_status_enums():
    df = sl.load_store_info()
    assert df is not None
    types = set(df["Dealer_type"].dropna().unique())
    statuses = set(df["Store Create Status Desc"].dropna().unique())
    assert types.issubset({"交付店", "体验店", "售后服务店", "未分类"})
    assert statuses.issubset({"开业", "暂停", "在建", "停业"})
    assert "全部" not in statuses and "全部" not in types


@pytest.mark.skipif(not _has_csv(), reason="本机 external store_info.csv 不存在")
def test_resolve_known_stores():
    cases = {
        "合肥包河": {"bloc": "上海易茂"},
        "青岛城阳车城店": {"bloc": "青岛鸿发"},
        "无锡万象城": {"bloc": "无锡海鹏"},
    }
    for store, want in cases.items():
        info = sl.resolve_dealer_info(store)
        assert info is not None, f"{store} 未能解析"
        assert info["bloc_name"] == want["bloc"], f"{store} bloc 不一致: {info}"


@pytest.mark.skipif(not _has_csv(), reason="本机 external store_info.csv 不存在")
def test_resolve_returns_expected_fields():
    info = sl.resolve_dealer_info("上海宝山高境")
    assert info is not None
    for f in EXPECTED_FIELDS:
        assert f in info, f"missing field {f}"
    assert info["store_name"] == "上海宝山高境"


def test_missing_store_returns_none_graceful():
    # 无数据（无 CSV 或查不到）都应返回 None 而非抛异常
    df_exists = _has_csv()
    r = sl.resolve_dealer_info("__不存在的门店__")
    assert r is None
    assert df_exists or sl.summary()["loaded"] is False
