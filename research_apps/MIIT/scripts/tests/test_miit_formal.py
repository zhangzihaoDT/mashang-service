"""MIIT 正式公告 + canonical merge 测试（fixture 驱动，不依赖实时网络）。

覆盖：
  A. MIIT formal metadata / parser（fixture HTML + fixture road txt）
  B. canonical merge（proposed→confirmed，rich fields 保留，MIIT formal > EIDC > proposed）
  C. historical formal only（只有正式附件 → confirmed 主键正常建立）
  D. variant 型号对齐（完整申报型号 → 目录基码）
"""
import importlib.util
import json
import sys
from pathlib import Path

MIIT = Path(__file__).resolve().parents[2]
SCRIPTS = MIIT / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(SCRIPTS))

from vehicle_record_builder import (  # noqa: E402
    merge_rows_by_key,
    apply_formal_confirmation,
    match_base_model_code,
    observation_rank as _rank,
)

CONFIRMED_SOURCES = [("miit_gov", "confirmed"), ("eidc", "confirmed")]


def _load_formal_entrypoint():
    """03_fetch_miit_formal_batch.py 文件名以数字开头，用 importlib 加载。"""
    path = SCRIPTS / "03_fetch_miit_formal_batch.py"
    spec = importlib.util.spec_from_file_location("fetch_miit_formal_batch", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _row(vid, source, stage, **overrides):
    """构造 canonical 行（含最小必需字段）。"""
    batch, model = vid.split(":", 1)
    base = {
        "vehicle_record_id": vid,
        "observation_id": f"{vid}:{stage}",
        "batch_no": batch,
        "model_code": model,
        "brand": "测试牌",
        "manufacturer": "测试企业",
        "product_name": "纯电动轿车",
        "common_name": "",
        "detail_url": "",
        "publish_date": "",
        "source": source,
        "stage": stage,
        "record_quality": "high",
        "source_vehicle_type": "纯电动轿车",
        "vehicle_category": "passenger_vehicle",
        "vehicle_subcategory": "sedan",
        "analysis_scope": "in_scope",
        "catalog_no": "",
        "source_section": "",
        "vehicle_tax_match_flag": "0",
        "purchase_tax_match_flag": "0",
        "multi_enterprise_count": "1",
        "multi_brand_flag": "0",
        "tax_catalog_match_flag": "0",
    }
    base.update(overrides)
    return base


# ── A. MIIT formal metadata / parser ──────────────────────────────

def test_formal_metadata_from_fixture():
    import miit_formal_source as mfs

    html = (FIXTURES / "formal_409_detail.html").read_text(encoding="utf-8")
    url = "https://www.miit.gov.cn/jgsj/zbys/wjfb/art/2026/art_4951b91392884d049c623d59387f6172.html"
    meta = mfs.parse_formal_metadata(html, url)

    assert meta["batch_no"] == "409"
    assert meta["source_url"] == url
    assert "第409批" in meta["title"]
    assert meta["vehicle_tax_batch"] == "88"
    assert meta["purchase_tax_batch"] == "33"
    assert "2026年第21号" in meta["announcement_no"]
    assert len(meta["attachments"]) == 3
    road = [a for a in meta["attachments"] if "道路机动车辆" in a["title"]]
    assert len(road) == 1
    assert road[0]["url"].startswith("https://www.miit.gov.cn/cms_files/")
    assert road[0]["filename"].endswith(".doc")


def test_formal_manifest_contract():
    """import_manifest contract：source=miit_gov, stage=confirmed, batch_no=409。"""
    mod = _load_formal_entrypoint()
    html = (FIXTURES / "formal_409_detail.html").read_text(encoding="utf-8")
    url = "https://www.miit.gov.cn/jgsj/zbys/wjfb/art/2026/art_4951b91392884d049c623d59387f6172.html"
    import miit_formal_source as mfs
    meta = mfs.parse_formal_metadata(html, url)
    manifest = mod.build_manifest("409", meta, url, [{"model_code_raw": "AAA1234"}])
    assert manifest["batch_no"] == "409"
    assert manifest["source"] == "miit_gov"
    assert manifest["stage"] == "confirmed"
    assert manifest["source_url"] == url
    assert manifest["raw_product_rows"] == 1


def test_formal_road_fixture_parses_product_list():
    """正式附件（road txt）→ product_list 非空，且能识别乘用车型。"""
    import eidc_parser
    txt = (FIXTURES / "formal_road_sample.txt").read_text(encoding="utf-8")
    recs = eidc_parser.parse_road_products(txt, "409")
    assert recs, "product_list 为空"
    codes = {r["model_code_raw"] for r in recs}
    assert {"AAA1234", "BBB5678", "BBB5679", "CCC9000"} <= codes
    assert all(r["batch_no"] == "409" for r in recs)
    assert all("source_section" in r for r in recs)


# ── B. canonical merge（synthetic） ───────────────────────────────

def test_merge_proposed_only_stays_proposed():
    rows = [_row("409:AAA1234", "miit_gov", "proposed", length_mm="5000")]
    merged = merge_rows_by_key(rows)
    assert len(merged) == 1
    assert merged[0]["stage"] == "proposed"
    assert merged[0]["source"] == "miit_gov"
    assert merged[0]["observation_id"] == "409:AAA1234:proposed"


def test_merge_proposed_plus_formal_promotes_and_keeps_rich():
    rows = [
        _row("409:AAA1234", "miit_gov", "proposed",
             length_mm="5000", battery_capacity_kwh="80", detail_url="https://x/detail"),
        _row("409:AAA1234", "miit_gov", "confirmed",
             common_name="测试A", catalog_no="1"),
    ]
    merged = merge_rows_by_key(rows)
    assert len(merged) == 1, "同一 vehicle_record_id 不应重复"
    m = merged[0]
    assert m["stage"] == "confirmed"
    assert m["source"] == "miit_gov"
    assert m["observation_id"] == "409:AAA1234:confirmed"
    # formal 确认字段生效
    assert m["common_name"] == "测试A"
    # proposed rich fields 不丢失
    assert m["length_mm"] == "5000"
    assert m["battery_capacity_kwh"] == "80"
    assert m["detail_url"] == "https://x/detail"


def test_merge_formal_beats_eidc_and_proposed():
    rows = [
        _row("409:AAA1234", "miit_gov", "proposed", length_mm="5000"),
        _row("409:AAA1234", "eidc", "confirmed", common_name="EIDC名"),
        _row("409:AAA1234", "miit_gov", "confirmed", common_name="MIIT正式名"),
    ]
    merged = merge_rows_by_key(rows)
    assert len(merged) == 1
    m = merged[0]
    assert m["source"] == "miit_gov"
    assert m["stage"] == "confirmed"
    assert m["common_name"] == "MIIT正式名", "MIIT formal 应优先于 EIDC formal"
    assert m["length_mm"] == "5000", "proposed rich field 应保留"


def test_observation_rank_order():
    assert _rank("miit_gov", "confirmed") > _rank("eidc", "confirmed") > _rank("miit_gov", "proposed")


# ── C. historical formal only ─────────────────────────────────────

def test_formal_only_establishes_confirmed_identity():
    rows = [_row("401:AFN6490", "miit_gov", "confirmed", common_name="历史正式")]
    merged = merge_rows_by_key(rows)
    assert len(merged) == 1
    m = merged[0]
    assert m["vehicle_record_id"] == "401:AFN6490"
    assert m["stage"] == "confirmed"
    assert m["source"] == "miit_gov"
    assert m["observation_id"] == "401:AFN6490:confirmed"


# ── D. formal confirmation matching（完整申报型号保留；base 只做确认） ──

def test_match_base_model_code_longest_prefix():
    bases = ["XMA6500", "XMA6530", "AHC6510"]
    assert match_base_model_code("XMA6500KREEVA1", bases) == "XMA6500"
    assert match_base_model_code("XMA6530ABC", bases) == "XMA6530"
    assert match_base_model_code("AHC6510SHEVX0A", bases) == "AHC6510"
    assert match_base_model_code("ZZZ9999", bases) is None
    assert match_base_model_code("", bases) is None


def test_formal_confirmation_two_variants_one_base_keeps_two_rows():
    """请求的核心用例：同一 base code 下两个 proposed variants + 一个 formal
    → canonical 仍两行，两行均 confirmed，完整 model_code 保留，formal base 行不出现。"""
    rows = [
        _row("409:XMA6500KREEVA1", "miit_gov", "proposed",
             model_code="XMA6500KREEVA1", length_mm="4960"),
        _row("409:XMA6500KREEVF3", "miit_gov", "proposed",
             model_code="XMA6500KREEVF3", length_mm="4965"),
        _row("409:XMA6500", "miit_gov", "confirmed", model_code="XMA6500",
             common_name="小米澎程N70", catalog_no="217"),
    ]
    out = apply_formal_confirmation(rows, CONFIRMED_SOURCES)
    assert len(out) == 2, f"应保留两个 variant 行，实得 {len(out)}"
    ids = sorted(r["vehicle_record_id"] for r in out)
    assert ids == ["409:XMA6500KREEVA1", "409:XMA6500KREEVF3"]
    for r in out:
        assert r["stage"] == "confirmed"
        assert r["source"] == "miit_gov"
        assert r["observation_id"].endswith(":confirmed")
        assert r["model_code"] in ("XMA6500KREEVA1", "XMA6500KREEVF3"), "完整申报型号应保留"
        # formal 基码字段补缺
        assert r["common_name"] == "小米澎程N70"
        assert r["catalog_no"] == "217"
    # rich fields 保留
    lengths = {r["model_code"]: r["length_mm"] for r in out}
    assert lengths["XMA6500KREEVA1"] == "4960"
    assert lengths["XMA6500KREEVF3"] == "4965"
    # formal base 行不出现
    assert "409:XMA6500" not in ids


def test_formal_confirmation_is_fill_only_not_overwrite():
    """formal 字段只补缺：variant 已有的 product_name 不被 formal 覆盖。"""
    rows = [
        _row("409:AAA1234", "miit_gov", "proposed", model_code="AAA1234",
             product_name="纯电动轿车（variant）", common_name=""),
        _row("409:AAA1234", "miit_gov", "confirmed", model_code="AAA1234",
             product_name="纯电动轿车（formal 族级）", common_name="某通用名"),
    ]
    out = apply_formal_confirmation(rows, CONFIRMED_SOURCES)
    assert len(out) == 1
    m = out[0]
    assert m["product_name"] == "纯电动轿车（variant）", "formal 不应覆盖 variant 具体字段"
    assert m["common_name"] == "某通用名", "variant 空字段应由 formal 补齐"
    assert m["stage"] == "confirmed"


def test_formal_confirmation_unmatched_proposed_stays_proposed():
    """proposed variant 与同批 formal 基码不匹配 → 保持 proposed；formal 行保留。"""
    rows = [
        _row("409:ZZZ1234", "miit_gov", "proposed", model_code="ZZZ1234"),
        _row("409:AAA1234", "miit_gov", "confirmed", model_code="AAA1234"),
    ]
    out = apply_formal_confirmation(rows, CONFIRMED_SOURCES)
    by_id = {r["vehicle_record_id"]: r for r in out}
    assert by_id["409:ZZZ1234"]["stage"] == "proposed"
    assert by_id["409:AAA1234"]["stage"] == "confirmed"


def test_formal_confirmation_no_formal_keeps_proposed():
    rows = [
        _row("411:XMA6500KREEVA1", "miit_gov", "proposed", model_code="XMA6500KREEVA1"),
    ]
    out = apply_formal_confirmation(rows, CONFIRMED_SOURCES)
    assert out[0]["vehicle_record_id"] == "411:XMA6500KREEVA1"
    assert out[0]["stage"] == "proposed"


def test_formal_confirmation_formal_only_uses_base_identity():
    """无 Gov 详情的 formal-only 行 → base 身份，confirmed。"""
    rows = [
        _row("409:ZZZ9999", "miit_gov", "confirmed", model_code="ZZZ9999"),
    ]
    out = apply_formal_confirmation(rows, CONFIRMED_SOURCES)
    assert len(out) == 1
    assert out[0]["vehicle_record_id"] == "409:ZZZ9999"
    assert out[0]["stage"] == "confirmed"


def test_formal_confirmation_strict_fallback_to_eidc():
    """MIIT formal 无匹配时回落到 EIDC formal（strict fallback）。"""
    rows = [
        _row("409:EEE1234", "miit_gov", "proposed", model_code="EEE1234"),
        _row("409:EEE1234", "eidc", "confirmed", model_code="EEE1234"),
    ]
    out = apply_formal_confirmation(rows, CONFIRMED_SOURCES)
    assert len(out) == 1
    assert out[0]["source"] == "eidc"
    assert out[0]["stage"] == "confirmed"
    assert out[0]["vehicle_record_id"] == "409:EEE1234"


def test_formal_confirmation_miit_beats_eidc_no_duplicate_base():
    """MIIT formal 命中时，同基码 EIDC formal 不重复出现。"""
    rows = [
        _row("409:AAA1234", "miit_gov", "proposed", model_code="AAA1234"),
        _row("409:AAA1234", "miit_gov", "confirmed", model_code="AAA1234"),
        _row("409:AAA1234", "eidc", "confirmed", model_code="AAA1234"),
    ]
    out = apply_formal_confirmation(rows, CONFIRMED_SOURCES)
    assert len(out) == 1
    assert out[0]["source"] == "miit_gov"
    assert out[0]["vehicle_record_id"] == "409:AAA1234"


def test_formal_confirmation_does_not_consume_other_prefix_bases():
    """consume matched base only：确认较长的 base 不应消费另一个仍被需要的短 base。"""
    rows = [
        _row("409:XMA6500KREEVA1", "miit_gov", "proposed", model_code="XMA6500KREEVA1"),
        _row("409:XMA6500ABC", "miit_gov", "proposed", model_code="XMA6500ABC"),
        _row("409:XMA6500KREEV", "miit_gov", "confirmed", model_code="XMA6500KREEV"),
        _row("409:XMA6500", "miit_gov", "confirmed", model_code="XMA6500"),
    ]
    out = apply_formal_confirmation(rows, CONFIRMED_SOURCES)
    by_id = {r["vehicle_record_id"]: r for r in out}
    # XMA6500KREEVA1 由 XMA6500KREEV 确认；XMA6500ABC 由 XMA6500 确认
    assert by_id["409:XMA6500KREEVA1"]["stage"] == "confirmed"
    assert by_id["409:XMA6500ABC"]["stage"] == "confirmed"
    # XMA6500KREEV 被消费；XMA6500 被 XMA6500ABC 消费
    assert "409:XMA6500KREEV" not in by_id
    assert "409:XMA6500" not in by_id
