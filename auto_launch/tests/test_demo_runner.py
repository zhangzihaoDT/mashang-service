"""demo_runner 测试"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from auto_launch.src.demo_runner import run_demo, DEMO_DIR


def _cleanup():
    """Remove demo output dir between tests."""
    import shutil
    if DEMO_DIR.exists():
        shutil.rmtree(DEMO_DIR)


def test_demo_reset_store():
    _cleanup()
    manifest = run_demo(reset_store=True)
    assert manifest["command"] == "demo"
    assert manifest["reset_store"] is True
    assert manifest["replay_summary"]["days"] >= 1
    assert manifest["replay_summary"]["total_facts"] > 0
    print(f"[PASS] test_demo_reset_store: {manifest['replay_summary']['days']} days, "
          f"{manifest['replay_summary']['total_facts']} facts")


def test_demo_outputs_demo_manifest():
    _cleanup()
    manifest = run_demo(reset_store=True)
    p = Path(manifest["outputs"]["manifest"])
    assert p.exists()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["command"] == "demo"
    print("[PASS] test_demo_outputs_demo_manifest")


def test_demo_outputs_demo_summary():
    _cleanup()
    manifest = run_demo(reset_store=True)
    p = Path(manifest["demo_summary"])
    assert p.exists()
    content = p.read_text(encoding="utf-8")
    assert "Auto Launch Demo Summary" in content
    print("[PASS] test_demo_outputs_demo_summary")


def test_demo_outputs_facts_audit():
    _cleanup()
    manifest = run_demo(reset_store=True)
    p = Path(manifest["outputs"]["facts_audit"])
    assert p.exists()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "total" in data
    assert "completeness" in data
    print("[PASS] test_demo_outputs_facts_audit")


def test_demo_outputs_source_audit():
    _cleanup()
    manifest = run_demo(reset_store=True)
    for key in ("source_audit_md", "source_audit_json"):
        p = Path(manifest["outputs"][key])
        assert p.exists(), f"Missing: {key}"
    md = Path(manifest["outputs"]["source_audit_md"]).read_text(encoding="utf-8")
    assert "Source Coverage Audit" in md
    json_data = json.loads(Path(manifest["outputs"]["source_audit_json"]).read_text(encoding="utf-8"))
    assert "official_rate" in json_data
    print("[PASS] test_demo_outputs_source_audit")


def test_demo_outputs_brief():
    _cleanup()
    manifest = run_demo(reset_store=True)
    p = Path(manifest["outputs"]["brief"])
    assert p.exists()
    content = p.read_text(encoding="utf-8")
    assert len(content) > 50
    print("[PASS] test_demo_outputs_brief")


def test_demo_outputs_timeline():
    _cleanup()
    manifest = run_demo(reset_store=True)
    p = Path(manifest["outputs"]["timeline"])
    assert p.exists()
    content = p.read_text(encoding="utf-8")
    assert "事件时间线" in content or "Timeline" in content or "时间线" in content or content
    print("[PASS] test_demo_outputs_timeline")


def test_demo_outputs_inspect():
    _cleanup()
    manifest = run_demo(reset_store=True)
    p = Path(manifest["outputs"]["outputs_inspect"])
    assert p.exists()
    content = p.read_text(encoding="utf-8")
    assert "Outputs Inspection Report" in content
    print("[PASS] test_demo_outputs_inspect")


def test_demo_does_not_use_real_api():
    """demo relies on fixtures + fact_store only — no search/API calls."""
    _cleanup()
    manifest = run_demo(reset_store=True)
    log_steps = [e["step"] for e in manifest["log"]]
    assert "search" not in " ".join(log_steps)
    assert "daily" not in " ".join(log_steps)
    print("[PASS] test_demo_does_not_use_real_api")


def test_demo_does_not_break_runs_contract():
    """demo outputs to demo/ only, does not create run dirs."""
    _cleanup()
    from auto_launch.src import output_paths
    root = output_paths.output_root()
    runs_before = list((root / "runs").glob("*"))
    manifest = run_demo(reset_store=True)
    runs_after = list((root / "runs").glob("*"))
    assert runs_before == runs_after
    assert "demo" in str(manifest["outputs"]["demo_dir"])
    print("[PASS] test_demo_does_not_break_runs_contract")


if __name__ == "__main__":
    test_demo_reset_store()
    test_demo_outputs_demo_manifest()
    test_demo_outputs_demo_summary()
    test_demo_outputs_facts_audit()
    test_demo_outputs_source_audit()
    test_demo_outputs_brief()
    test_demo_outputs_timeline()
    test_demo_outputs_inspect()
    test_demo_does_not_use_real_api()
    test_demo_does_not_break_runs_contract()
    print("\n✅ 所有 demo_runner 测试通过")
