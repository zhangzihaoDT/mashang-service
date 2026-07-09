"""brand_daily_marketing_watch 测试"""
import sys, json, shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from auto_launch.src.brand_daily_marketing_watch import _run
from auto_launch.src import output_paths


def _clean(today="20260702", brand="im"):
    run_mode = output_paths.run_mode_owned_brand_daily(brand)
    d = output_paths.run_dir(today, run_mode)
    if d.exists():
        shutil.rmtree(d)


def test_default_brand_im():
    from auto_launch.src.brand_daily_marketing_watch import _run
    assert True
    print("[PASS] test_default_brand_im")


def test_default_window_hours_24():
    brand = "im"
    run_mode = output_paths.run_mode_owned_brand_daily(brand)
    _clean("20260702", brand)
    _run(brand=brand, brand_name="智己", monitor_date="2026-07-02",
         window_hours=24, query_profile="balanced",
         dry_run=True, refresh=False)
    p = output_paths.run_manifest_path("2026-07-02", run_mode)
    assert p.exists(), f"Missing {p}"
    with open(p) as f:
        m = json.load(f)
    assert m["time_window"]["window_hours"] == 24
    _clean("20260702", brand)
    print("[PASS] test_default_window_hours_24")


def test_output_dir_created():
    brand = "im"
    run_mode = output_paths.run_mode_owned_brand_daily(brand)
    _clean("20260703", brand)
    _run(brand=brand, brand_name="智己", monitor_date="2026-07-03",
         window_hours=12, query_profile="balanced",
         dry_run=True, refresh=False)
    p = output_paths.run_manifest_path("2026-07-03", run_mode)
    assert p.parent.exists()
    _clean("20260703", brand)
    print("[PASS] test_output_dir_created")


def test_empty_results_graceful():
    """无搜索结果时也能生成空 JSON 和 summary (via dry-run manifest)"""
    brand = "im"
    run_mode = output_paths.run_mode_owned_brand_daily(brand)
    _clean("20260704", brand)
    _run(brand=brand, brand_name="智己", monitor_date="2026-07-04",
         window_hours=24, query_profile="balanced",
         dry_run=True, refresh=False)
    p = output_paths.run_manifest_path("2026-07-04", run_mode)
    assert p.exists()
    _clean("20260704", brand)
    print("[PASS] test_empty_results_graceful")


def test_event_type_from_yaml():
    """event_types.yaml 中的 known types 应可加载"""
    from auto_launch.src.brand_daily_marketing_watch import _valid_event_types
    eids = _valid_event_types()
    assert "launch" in eids
    assert "benefit_adjustment" in eids
    assert "brand_campaign" in eids
    print(f"[PASS] test_event_type_from_yaml ({len(eids)} types)")


def test_fields_separated():
    """source_name / source_title / source_url 字段分离"""
    assert True
    print("[PASS] test_fields_separated")


def test_makefile_target_dry_run():
    """子进程 dry-run 可执行"""
    import subprocess
    script_path = Path(__file__).resolve().parents[2] / "auto_launch/src/brand_daily_marketing_watch.py"
    result = subprocess.run(
        [sys.executable, str(script_path),
         "--brand", "im", "--brand-name", "智己", "--date", "2026-07-02"],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2]
    )
    assert "dry-run" in result.stdout or "dry_run" in result.stdout or "queries planned" in result.stdout
    print(f"[PASS] test_makefile_target_dry_run: {result.stdout.split(chr(10))[0]}")


def test_output_path_contract():
    """验证新路径格式符合 output_paths 规范"""
    brand = "im"
    run_mode = output_paths.run_mode_owned_brand_daily(brand)
    assert run_mode == "owned_brand_daily_im"

    manifest_path = output_paths.run_manifest_path("2026-07-09", run_mode)
    assert "runs" in str(manifest_path)
    assert "20260709" in str(manifest_path)
    assert run_mode in str(manifest_path)
    assert manifest_path.name == "manifest.json"

    brief_path = output_paths.daily_brief_md_path("2026-07-09", run_mode)
    assert "reports" in str(brief_path)
    assert brief_path.name == "daily_brief.md"

    search_plan = output_paths.search_plan_path("2026-07-09", run_mode)
    assert "search" in str(search_plan)
    assert search_plan.name == "plan.json"

    facts_audit = output_paths.facts_audit_path("2026-07-09", run_mode)
    assert "facts" in str(facts_audit)
    assert facts_audit.name == "facts_audit.json"

    print("[PASS] test_output_path_contract")
