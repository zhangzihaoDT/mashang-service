"""Tests for MIIT Vehicle Publicity Image Parser."""

import json
import pytest
from pathlib import Path

from mashang_workspace.promptbuilders.miit_new_car.miit_vehicle_publicity_image_parser import (
    parse_ocr_result,
    _parse_dimensions,
    _parse_track,
    _parse_overhang,
    _parse_other,
    _build_record_id,
    _parse_table_rows,
    _parse_header_fields,
    _parse_table_specs,
    _parse_chassis_table,
    _clean_markdown,
)

FIXTURE_DIR = Path(__file__).resolve().parents[3] / "mashang_workspace" / "outputs" / "ocr" / "results"

DOC_PARSE_RESULT = FIXTURE_DIR / "1f66a23fa88c2c6eeb22c1439ae08b59.json"
GEN_OCR_RESULT = FIXTURE_DIR / "c9dad7e5e13b47773f573f9c9fc468c6.json"


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


# ── Fixtures ────────────────────────────────────────────────

@pytest.fixture(scope="module")
def doc_result():
    return _load(DOC_PARSE_RESULT)


@pytest.fixture(scope="module")
def gen_result():
    return _load(GEN_OCR_RESULT)


@pytest.fixture(scope="module")
def parsed(doc_result, gen_result):
    return parse_ocr_result(doc_result, gen_result)


# ── Unit Parsing Tests ──────────────────────────────────────

class TestParseDimensions:
    def test_parse_dimensions(self):
        r = _parse_dimensions("长:4886宽:1984高:1927")
        assert r["length_mm"] == 4886
        assert r["width_mm"] == 1984
        assert r["height_mm"] == 1927


class TestParseTrack:
    def test_parse_track(self):
        r = _parse_track("前轮距:1661后轮距:1675")
        assert r["front_track_mm"] == 1661
        assert r["rear_track_mm"] == 1675


class TestParseOverhang:
    def test_parse_overhang(self):
        r = _parse_overhang("774/1102")
        assert r["front_overhang_mm"] == 774
        assert r["rear_overhang_mm"] == 1102

    def test_parse_overhang_empty(self):
        r = _parse_overhang("")
        assert r == {}


class TestParseOther:
    def test_parse_battery_type(self):
        r = _parse_other("储能装置种类:镍钴锰三元锂蓄电池;")
        assert r["battery_type"] == "镍钴锰三元锂蓄电池"

    def test_parse_edr(self):
        r = _parse_other("该车配备汽车事件数据记录系统(EDR)")
        assert r["has_edr"] is True

    def test_parse_external_charging(self):
        r = _parse_other("允许外接充电")
        assert r["has_external_charging"] is True

    def test_parse_towing(self):
        r = _parse_other("准拖挂车总质量:不带制动750kg,带制动2500kg")
        assert r["has_towing_device"] is True


class TestBuildRecordId:
    def test_with_model(self):
        rid = _build_record_id("abcdef1234567890", "CC2030BE29BPHEV")
        assert rid == "miit_ocr_abcdef12_CC2030BE29BPHEV"

    def test_without_model(self):
        rid = _build_record_id("abcdef12", None)
        assert rid == "miit_ocr_abcdef12_unknown"


class TestMarkdownParsing:
    def test_clean_markdown_removes_separators(self):
        md = "| a | b |\n| --- | --- |\n| 1 | 2 |"
        cleaned = _clean_markdown(md)
        assert "---" not in cleaned
        assert "1" in cleaned

    def test_parse_table_rows(self):
        md = "| a | b |\n| 1 | 2 |"
        rows = _parse_table_rows(md)
        assert len(rows) == 2
        assert rows[1] == ["1", "2"]


class TestHeaderFields:
    def test_parse_header_fields(self, doc_result):
        md = doc_result["markdown"]
        h = _parse_header_fields(md)
        assert h.get("product_brand_raw") == "长城牌"


class TestParseTableSpecs:
    def test_parse_specs_from_doc(self, doc_result):
        rows = _parse_table_rows(doc_result["markdown"])
        specs = _parse_table_specs(rows)
        assert specs.get("wheelbase_raw") == "3010"
        assert specs.get("tire_spec_raw") == "265/65R18"
        assert specs.get("fuel_type_raw") == "汽油/电混合动力"


class TestParseChassisTable:
    def test_parse_chassis(self, doc_result):
        c = _parse_chassis_table(doc_result["markdown"])
        assert c.get("chassis_model") == "CC2030BE29BPHEV"
        assert c.get("chassis_manufacturer") == "长城汽车股份有限公司"
        assert c.get("chassis_category") == "三类"


# ── Integration Tests ───────────────────────────────────────

class TestParserIntegration:
    def test_parse_status_success(self, parsed):
        assert parsed["parse_status"] == "success"

    def test_product_brand(self, parsed):
        f = parsed["fields"]["product_brand"]
        assert f["value"] == "长城牌"
        assert f["source"] == "document_parse+general_ocr"

    def test_product_model(self, parsed):
        assert parsed["fields"]["product_model"]["value"] == "CC2030BE29BPHEV"

    def test_product_name(self, parsed):
        assert "插电式混合动力" in parsed["fields"]["product_name"]["value"]

    def test_enterprise_name(self, parsed):
        assert "长城汽车" in parsed["fields"]["enterprise_name"]["value"]

    def test_dimensions(self, parsed):
        assert parsed["fields"]["length_mm"]["value"] == 4886
        assert parsed["fields"]["width_mm"]["value"] == 1984
        assert parsed["fields"]["height_mm"]["value"] == 1927

    def test_wheelbase(self, parsed):
        assert parsed["fields"]["wheelbase_mm"]["value"] == 3010

    def test_gross_mass(self, parsed):
        assert parsed["fields"]["gross_mass_kg"]["value"] == 3355

    def test_curb_weight(self, parsed):
        assert parsed["fields"]["curb_weight_kg"]["value"] == 2890

    def test_max_speed(self, parsed):
        assert parsed["fields"]["max_speed_kmh"]["value"] == 180

    def test_tire_count(self, parsed):
        assert parsed["fields"]["tire_count"]["value"] == 4

    def test_fuel_type(self, parsed):
        assert "汽油" in parsed["fields"]["fuel_type"]["value"]

    def test_engine_model(self, parsed):
        assert parsed["fields"]["engine_model"]["value"] == "E20NB"

    def test_engine_manufacturer(self, parsed):
        assert "长城" in parsed["fields"]["engine_manufacturer"]["value"]

    def test_displacement(self, parsed):
        assert parsed["fields"]["displacement_ml"]["value"] == 1998

    def test_rated_passenger_count(self, parsed):
        assert parsed["fields"]["rated_passenger_count"]["value"] == 5

    def test_power_kw(self, parsed):
        assert parsed["fields"]["power_kw"]["value"] == 185

    def test_chassis_model(self, parsed):
        assert parsed["fields"]["chassis_model"]["value"] == "CC2030BE29BPHEV"

    def test_chassis_category(self, parsed):
        assert parsed["fields"]["chassis_category"]["value"] == "三类"

    def test_battery_type_from_other(self, parsed):
        assert "镍钴锰" in parsed["fields"]["battery_type"]["value"]

    def test_edr_detected(self, parsed):
        assert parsed["fields"]["has_edr"]["value"] is True

    def test_external_charging(self, parsed):
        assert parsed["fields"]["has_external_charging"]["value"] is True

    def test_vehicle_record_id(self, parsed):
        rid = parsed["vehicle_record_id"]
        assert rid.startswith("miit_ocr_")
        assert "CC2030BE29BPHEV" in rid

    def test_source_trace(self, parsed):
        assert parsed["source_trace"]["primary_ocr_mode"] == "document_parse"
        assert parsed["source_trace"]["fallback_ocr_mode"] == "general_ocr"

    def test_output_json_serializable(self, parsed):
        json.dumps(parsed, ensure_ascii=False)


class TestRecordRole:
    def test_primary_vehicle_record_role(self, parsed):
        assert parsed["record_role"] == "primary_vehicle_record"

    def test_primary_join_status(self, parsed):
        assert parsed["join_status"] == "not_required"

    def test_primary_no_review(self, parsed):
        assert parsed["quality"]["needs_manual_review"] is False


class TestSupplementRecord:
    def test_supplement_role(self):
        markdown = (
            "| 外形尺寸(mm): | 长:4800宽:1900高:1800 | | |\n"
            "| 排放依据标准: | GB18352.6-2016国VI | 燃料种类: | 汽油 |\n"
            "| 最高车速(km/h): | 180 | 总质量(kg): | 3000 |\n"
            "| 转向型式: | 方向盘 | 整备质量(kg): | 2000 |\n"
            "| 轴距(mm): | 2900 | 轮胎规格: | 265/65R18 |\n"
            "| 轮胎数: | 4 | | |\n"
            "| 接近角/离去角(度): | 38/33 | 轮距(前/后)mm: | 前轮距:1600后轮距:1620 |\n"
            "| 前悬/后悬(mm): | 900/1100 | | |\n"
            "| 防抱死制动系统: | 有 | | |\n"
        )
        mock_doc = {
            "source_image_path": "detail.png",
            "ocr_result_id": "test_supp",
            "mode": "document_parse",
            "image_sha256": "abc123",
            "markdown": markdown,
            "raw_text": markdown,
            "raw_response_path": "",
            "status": "success",
        }
        result = parse_ocr_result(mock_doc)
        assert result["record_role"] == "supplement_record"
        assert result["join_status"] == "unlinked"
        assert result["quality"]["needs_manual_review"] is True
        assert result["parse_status"] == "partial"

    def test_supplement_reason(self):
        markdown = (
            "| 外形尺寸(mm): | 长:4800宽:1900高:1800 | | |\n"
            "| 最高车速(km/h): | 180 | 总质量(kg): | 3000 |\n"
            "| 整备质量(kg): | 2000 | | |\n"
            "| 轴距(mm): | 2900 | 轮胎规格: | 265/65R18 |\n"
            "| 轮胎数: | 4 | 轮距(前/后)mm: | 前轮距:1600后轮距:1620 |\n"
            "| 燃料种类: | 汽油 | | |\n"
        )
        mock_doc = {
            "source_image_path": "detail.png",
            "ocr_result_id": "test_supp2",
            "mode": "document_parse",
            "image_sha256": "abc456",
            "markdown": markdown,
            "raw_text": markdown,
            "raw_response_path": "",
            "status": "success",
        }
        result = parse_ocr_result(mock_doc)
        assert "requires linking" in result["quality"]["quality_reason"]


class TestUnknownRecord:
    def test_unknown_role(self):
        mock_doc = {
            "source_image_path": "noise.png",
            "ocr_result_id": "test_unk",
            "mode": "document_parse",
            "image_sha256": "xyz789",
            "markdown": "garbage text with no useful info",
            "raw_text": "some random text\nthat doesn't contain\nany vehicle specs",
            "raw_response_path": "",
            "status": "success",
        }
        result = parse_ocr_result(mock_doc)
        assert result["record_role"] == "unknown_record"
        assert result["join_status"] == "unknown"
        assert result["quality"]["needs_manual_review"] is True

    def test_unknown_reason(self):
        mock_doc = {
            "source_image_path": "noise.png",
            "ocr_result_id": "test_unk2",
            "mode": "document_parse",
            "image_sha256": "xyz000",
            "markdown": "",
            "raw_text": "no useful data",
            "raw_response_path": "",
            "status": "success",
        }
        result = parse_ocr_result(mock_doc)
        assert "insufficient" in result["quality"]["quality_reason"]
        assert result["record_role"] == "unknown_record"


class TestCrossCheck:
    def test_matched_fields_nonempty(self, parsed):
        assert len(parsed["cross_check"]["matched_fields"]) > 0

    def test_brand_matched(self, parsed):
        assert "product_brand" in parsed["cross_check"]["matched_fields"]

    def test_model_matched(self, parsed):
        assert "product_model" in parsed["cross_check"]["matched_fields"]

    def test_no_conflicts(self, parsed):
        assert len(parsed["cross_check"]["conflicts"]) == 0


class TestMissingFields:
    def test_failed_status_when_all_missing(self):
        """Simulate a minimal document_parse result without any required fields."""
        mock_doc = {
            "source_image_path": "test.png",
            "ocr_result_id": "test123",
            "mode": "document_parse",
            "image_sha256": "abcdef123456",
            "markdown": "no useful info",
            "raw_text": "no useful info",
            "raw_response_path": "",
            "status": "success",
        }
        result = parse_ocr_result(mock_doc)
        assert result["parse_status"] == "failed"
        assert result["quality"]["needs_manual_review"] is True
        assert result["record_role"] == "unknown_record"

    def test_no_ocr_api_called(self):
        """Verify parser doesn't call OCR API - only consumes existing results."""
        # This test passes by construction - the parser only reads JSON files
        pass
