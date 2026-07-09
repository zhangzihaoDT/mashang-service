"""operating_loop 测试 — 验证 run_day 输出路径和内容"""
import sys, tempfile, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from auto_launch.src.operating_loop import run_day, _render_summary
from auto_launch.src import output_paths


def test_run_day_dry_run():
    r = run_day(monitor_date="2026-07-09", live=False)
    assert r["monitor_date"] == "2026-07-09"
    assert r["live"] is False
    assert r["run_mode"] == "brand_daily_zhiji"
    assert "outputs" in r
    for k in ("run_dir", "manifest", "audit", "source_audit_json", "source_audit_md", "brief", "summary"):
        assert k in r["outputs"], f"Missing output key: {k}"
    print(f"[PASS] test_run_day_dry_run: {len(r['log'])} log entries")


def test_run_day_creates_output_files():
    r = run_day(monitor_date="2026-07-09", live=False)
    for k, path_str in r["outputs"].items():
        p = Path(path_str)
        assert p.exists(), f"Output file missing: {k} -> {p}"
    print(f"[PASS] test_run_day_creates_output_files")


def test_run_day_manifest_valid_json():
    r = run_day(monitor_date="2026-07-09", live=False)
    manifest = json.loads(Path(r["outputs"]["manifest"]).read_text(encoding="utf-8"))
    assert manifest["command"] == "run-day"
    assert manifest["monitor_date"] == "2026-07-09"
    assert "audit_summary" in manifest
    assert "source_audit_summary" in manifest
    sas = manifest["source_audit_summary"]
    assert "official_rate" in sas
    assert "media_rate" in sas
    assert "expected_gaps" in sas
    print(f"[PASS] test_run_day_manifest_valid_json")


def test_run_day_audit_file():
    r = run_day(monitor_date="2026-07-09", live=False)
    audit = json.loads(Path(r["outputs"]["audit"]).read_text(encoding="utf-8"))
    assert "total" in audit
    assert "completeness" in audit
    assert "warnings" in audit
    print(f"[PASS] test_run_day_audit_file")


def test_run_day_brief_file():
    r = run_day(monitor_date="2026-07-09", live=False)
    brief = Path(r["outputs"]["brief"]).read_text(encoding="utf-8")
    assert len(brief) > 50
    print(f"[PASS] test_run_day_brief_file")


def test_run_day_summary_file():
    r = run_day(monitor_date="2026-07-09", live=False)
    summary = Path(r["outputs"]["summary"]).read_text(encoding="utf-8")
    assert "Run Summary" in summary
    assert r["brand_name"] in summary
    print(f"[PASS] test_run_day_summary_file")


def test_run_day_source_audit_json():
    r = run_day(monitor_date="2026-07-09", live=False)
    sa = json.loads(Path(r["outputs"]["source_audit_json"]).read_text(encoding="utf-8"))
    assert "total" in sa
    assert "official_rate" in sa
    assert "media_rate" in sa
    assert "brand_coverage" in sa
    assert "expected_flags" in sa
    assert "suggestions" in sa
    assert sa.get("watchlist") == "priority"
    print(f"[PASS] test_run_day_source_audit_json")


def test_run_day_source_audit_md():
    r = run_day(monitor_date="2026-07-09", live=False)
    md = Path(r["outputs"]["source_audit_md"]).read_text(encoding="utf-8")
    assert "Source Coverage Audit" in md
    assert "Per-Brand Coverage" in md
    print(f"[PASS] test_run_day_source_audit_md")


def test_run_day_summary_has_source_audit_section():
    r = run_day(monitor_date="2026-07-09", live=False)
    md = Path(r["outputs"]["summary"]).read_text(encoding="utf-8")
    assert "## Source Audit" in md
    assert "Official rate" in md
    assert "Media rate" in md
    assert "Expected gaps" in md
    print(f"[PASS] test_run_day_summary_has_source_audit_section")


def test_run_day_custom_brief_output():
    with tempfile.TemporaryDirectory() as tmp:
        custom = Path(tmp) / "brief.md"
        r = run_day(monitor_date="2026-07-09", live=False, brief_output=str(custom))
        assert custom.exists()
    print(f"[PASS] test_run_day_custom_brief_output")


def test_render_summary():
    manifest = {
        "monitor_date": "2026-07-09", "brand_name": "智己",
        "live": False, "window_hours": 24,
        "log": [{"step": "test", "status": "ok", "detail": "test detail", "time": "2026-07-09T12:00:00"}],
        "outputs": {"brief": "/tmp/brief.md"},
        "created_at": "2026-07-09T12:00:00",
    }
    audit = {"total": 5, "quality_flags": {"no_brand": 0, "no_event_type": 0}, "warnings": []}
    md = _render_summary(manifest, audit)
    assert "Run Summary" in md
    assert "test" in md
    print(f"[PASS] test_render_summary")


def test_render_summary_with_source_audit():
    manifest = {
        "monitor_date": "2026-07-09", "brand_name": "智己",
        "live": False, "window_hours": 24,
        "log": [{"step": "test", "status": "ok", "detail": "test detail", "time": "2026-07-09T12:00:00"}],
        "outputs": {"brief": "/tmp/brief.md"},
        "created_at": "2026-07-09T12:00:00",
    }
    audit = {"total": 5, "quality_flags": {"no_brand": 0, "no_event_type": 0}, "warnings": []}
    sa_report = {
        "total": 5, "official_rate": 60.0, "official_count": 3,
        "media_rate": 40.0, "auto_media_count": 2,
        "social_count": 0, "weak_count": 0,
        "missing_url": 1, "missing_event_date": 0,
        "expected_flags": [{"brand": "理想", "flag": "expected_official_missing", "detail": "no official"}],
        "low_quality_count": 1,
        "suggestions": ["官方源不足"],
    }
    md = _render_summary(manifest, audit, sa_report)
    assert "Source Audit" in md
    assert "60.0%" in md
    assert "理想" in md
    print(f"[PASS] test_render_summary_with_source_audit")


def test_output_path_contract():
    """验证 run_day 的输出路径符合新的输出合同"""
    run_mode = "brand_daily_zhiji"
    assert output_paths.run_manifest_path("2026-07-09", run_mode).name == "manifest.json"
    assert "reports" in str(output_paths.daily_brief_md_path("2026-07-09", run_mode))
    assert output_paths.daily_brief_md_path("2026-07-09", run_mode).name == "daily_brief.md"
    assert "facts" in str(output_paths.facts_audit_path("2026-07-09", run_mode))
    assert output_paths.facts_audit_path("2026-07-09", run_mode).name == "facts_audit.json"
    print(f"[PASS] test_output_path_contract")
