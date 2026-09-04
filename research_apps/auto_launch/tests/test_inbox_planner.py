"""inbox_planner 集成测试 — Planner 日报管线验收"""
import sys, os, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from auto_launch.src.inbox_parser import parse_text, parse_contract
from auto_launch.src.inbox_filter import route
from auto_launch.src.inbox_runner import run_text
from auto_launch.src.fact_store import FactStore

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "planner_daily_report.md"
PLANNER_TEXT = FIXTURE.read_text(encoding="utf-8")


# ── P0 验收标准 ────────────────────────────────────────────────

def test_planner_p0_acceptance():
    summary = run_text(PLANNER_TEXT, date="2026-07-27", write_facts=False)
    assert summary["source_type"] == "planner_daily_report"
    assert summary["confirmed_facts"] == 1
    assert summary["review_signals"] == 2
    assert summary["brand_statuses"] == 22
    assert summary["brand_volumes"] == 2
    assert summary["total_items"] == 27
    print(f"[PASS] P0 验收: {summary['confirmed_facts']}+{summary['review_signals']}+{summary['brand_statuses']}+{summary['brand_volumes']}={summary['total_items']}")


# ── Parse contract ────────────────────────────────────────────

def test_parse_contract_planner():
    contract = parse_contract(PLANNER_TEXT, default_date="2026-07-27")
    assert contract["source_type"] == "planner_daily_report"
    assert len(contract["sections"]) == 4
    section_types = {s["section_type"] for s in contract["sections"]}
    assert "brand_events" in section_types
    assert "review_signals" in section_types
    assert "brand_status" in section_types
    assert "brand_volume" in section_types
    total_rows = sum(s["row_count"] for s in contract["sections"])
    assert total_rows == 27
    print(f"[PASS] parse_contract: {len(contract['sections'])} sections, {total_rows} rows")


def test_parse_contract_section_counts():
    contract = parse_contract(PLANNER_TEXT)
    sections = {s["section_type"]: s["row_count"] for s in contract["sections"]}
    assert sections.get("brand_events") == 1
    assert sections.get("review_signals") == 2
    assert sections.get("brand_status") == 22
    assert sections.get("brand_volume") == 2
    print(f"[PASS] section_counts: {sections}")


# ── Routing ───────────────────────────────────────────────────

def test_route_brand_event():
    r = route({"brand": "理想", "section_type": "brand_events", "event_type": "partnership"})
    assert r["route_to"] == "confirmed_fact"


def test_route_review_signal():
    r = route({"brand": "极氪", "section_type": "review_signals", "claim": "锁车争议"})
    assert r["route_to"] == "review_signal"


def test_route_brand_status():
    r = route({"brand": "问界", "section_type": "brand_status"})
    assert r["route_to"] == "brand_status"


def test_route_brand_volume():
    r = route({"brand": "小米", "section_type": "brand_volume"})
    assert r["route_to"] == "brand_volume"


# ── Field mapping ─────────────────────────────────────────────

def test_field_mapping_brand_event():
    items = parse_text(PLANNER_TEXT)
    events = [i for i in items if i.get("section_type") == "brand_events"]
    assert len(events) == 1
    e = events[0]
    assert e["brand"] == "智己"
    assert e["model"] == "LS6"
    assert e["event_type"] == "权益调整"
    assert "5000 元尾款减免" in (e.get("claim") or "")
    print(f"[PASS] brand_event field mapping: brand={e['brand']} type={e['event_type']}")


def test_field_mapping_brand_status():
    items = parse_text(PLANNER_TEXT)
    statuses = [i for i in items if i.get("section_type") == "brand_status"]
    assert len(statuses) == 22
    brands = {s["brand"] for s in statuses}
    assert "智己" in brands
    assert "特斯拉" in brands
    zhiji = next(s for s in statuses if s["brand"] == "智己")
    assert zhiji.get("status_phase") == "产品投放期"
    print(f"[PASS] brand_status: 22 brands, field mapping ok")


# ── Fact store full pipeline ─────────────────────────────────

def test_fact_store_full_pipeline():
    db_path = tempfile.mktemp(suffix=".sqlite")
    import auto_launch.src.fact_store as fs
    original = fs.DEFAULT_DB_PATH
    fs.DEFAULT_DB_PATH = Path(db_path)
    try:
        summary = run_text(PLANNER_TEXT, date="2026-07-27", write_facts=True)
        store = FactStore(db_path)
        cov = store.audit_coverage()
        assert cov["facts_total"] == 1
        assert cov["signals_total"] == 2
        assert cov["brand_status_total"] == 22
        assert cov["brand_volume_total"] == 2
        assert cov["evidence_total"] >= 1
        assert len(cov["brands_with_status"]) == 22
        store.close()
    finally:
        fs.DEFAULT_DB_PATH = original
        if os.path.exists(db_path):
            os.unlink(db_path)
    print(f"[PASS] full pipeline: 1 fact + 2 signals + 22 status + 2 volume + evidence")


# ── Legacy backward compat ────────────────────────────────────

def test_parse_text_returns_list():
    items = parse_text(PLANNER_TEXT)
    assert isinstance(items, list)
    assert len(items) == 27
    for item in items:
        assert "section_type" in item
        assert "source_type" in item
    print(f"[PASS] parse_text returns list with section_type/source_type")


def test_source_type_always_planner():
    contract = parse_contract(PLANNER_TEXT)
    assert contract["source_type"] == "planner_daily_report"
    print(f"[PASS] source_type always planner")


if __name__ == "__main__":
    test_planner_p0_acceptance()
    test_parse_contract_planner()
    test_parse_contract_section_counts()
    test_route_brand_event()
    test_route_review_signal()
    test_route_brand_status()
    test_route_brand_volume()
    test_field_mapping_brand_event()
    test_field_mapping_brand_status()
    test_fact_store_full_pipeline()
    test_parse_text_returns_list()
    test_source_type_always_planner()
    print("\n✅ 所有测试通过")
