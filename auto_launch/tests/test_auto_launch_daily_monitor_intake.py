"""
Phase: Daily Monitor intake tests.

Covers:
1. Daily Monitor example passes intake
2. Empty event_candidates (no-event day) passes intake
3. Legacy brief still works
4. task_name detection doesn't cross-contaminate
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_TEST_DIR = Path(__file__).resolve().parent
_WORKSPACE = _TEST_DIR.parent.parent
_PROJECT = _WORKSPACE.parent

AUTO_LAUNCH = _WORKSPACE / "promptbuilders" / "auto_launch"
INTAKE_SCRIPT = AUTO_LAUNCH / "intake" / "process_ai_output.py"
BRIEF_RAW = AUTO_LAUNCH / "examples" / "ai_outputs" / "event_48h_sample.json"
VALIDATE_SCRIPT = AUTO_LAUNCH / "validators" / "validate_ai_response.py"

PYTHON = sys.executable

# ── Daily Monitor sample (matches actual ChatGPT Plan output structure) ──

DAILY_MONITOR_SAMPLE = {
    "task_name": "auto_launch_daily_sales_action_monitor",
    "battle_field": "large_six_seat_suv",
    "our_model": "智己 LS8",
    "monitor_date": "2026-07-01",
    "time_window": {"start": "2026-06-30", "end": "2026-07-01", "fallback_start": "2026-06-29"},
    "input_assets": {
        "watchlist_path": "configs/ls8_competitor_watchlist.csv",
        "event_types_path": "configs/event_types.yaml",
    },
    "event_candidates": [
        {
            "event_model": "问界 M7",
            "event_brand": "问界",
            "event_type": "official_rights_update",
            "event_name": "问界 M7 限时购车权益更新",
            "event_date": "2026-07-01",
            "confidence": "medium",
            "source_items": [
                {"source_name": "鸿蒙智行官网", "source_title": "问界 M7 权益政策",
                 "source_url": "https://example.com", "source_tier": "official", "publish_time": "2026-07-01"}
            ],
            "impact_vs_our_model": {
                "price_pressure": "medium", "rights_pressure": "high",
                "configuration_pressure": "low", "delivery_pressure": "unknown"
            },
            "missing_evidence": ["缺少权益对比数据"]
        }
    ],
    "no_event_models": ["零跑 D19", "小鹏 GX", "理想 i6"],
    "needs_review": []
}

DAILY_MONITOR_EMPTY = {
    "task_name": "auto_launch_daily_sales_action_monitor",
    "battle_field": "large_six_seat_suv",
    "our_model": "智己 LS8",
    "monitor_date": "2026-07-01",
    "time_window": {"start": "2026-06-30", "end": "2026-07-01"},
    "input_assets": {"watchlist_path": "x", "event_types_path": "x"},
    "event_candidates": [],
    "no_event_models": ["零跑 D19", "小鹏 GX", "理想 i6", "问界 M7"],
    "needs_review": []
}


def _run(cmd, expect_zero=True, cwd=None):
    cwd = cwd or str(_WORKSPACE)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if expect_zero and result.returncode != 0:
        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr}")
    return result


# ── 1. Daily Monitor passes intake ──────────────────────────────


def test_daily_monitor_intake_passes():
    """Full intake on Daily Monitor sample produces all output files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        in_path = os.path.join(tmpdir, "input.json")
        with open(in_path, "w") as f:
            json.dump(DAILY_MONITOR_SAMPLE, f)

        result = _run([
            PYTHON, str(INTAKE_SCRIPT), in_path,
            "--output-dir", tmpdir,
        ])
        assert result.returncode == 0

        files = os.listdir(tmpdir)
        for name in ["normalized_daily_monitor.json", "event_candidates.json",
                      "needs_review.json", "no_event_models.json",
                      "intake_summary.md", "intake_manifest.json"]:
            assert name in files, f"Missing: {name}"


def test_daily_monitor_validate_detects_correct_type():
    """Validate detects daily monitor type correctly."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(DAILY_MONITOR_SAMPLE, f)
        tmp = f.name
    try:
        result = _run([PYTHON, str(VALIDATE_SCRIPT), tmp])
        assert result.returncode == 0
        assert "daily_monitor" in result.stdout
    finally:
        os.unlink(tmp)


# ── 2. Empty event_candidates passes intake ─────────────────────


def test_daily_monitor_empty_candidates_passes():
    """No-event day with empty event_candidates should pass intake."""
    with tempfile.TemporaryDirectory() as tmpdir:
        in_path = os.path.join(tmpdir, "input.json")
        with open(in_path, "w") as f:
            json.dump(DAILY_MONITOR_EMPTY, f)

        result = _run([
            PYTHON, str(INTAKE_SCRIPT), in_path,
            "--output-dir", tmpdir,
        ])
        assert result.returncode == 0

        manifest = json.loads(Path(tmpdir, "intake_manifest.json").read_text("utf-8"))
        assert manifest["record_type"] == "daily_monitor"
        assert manifest["event_candidates_count"] == 0
        assert manifest["no_event_models_count"] == 4


def test_daily_monitor_empty_validate_passes():
    """Validate should pass empty event_candidates."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(DAILY_MONITOR_EMPTY, f)
        tmp = f.name
    try:
        result = _run([PYTHON, str(VALIDATE_SCRIPT), tmp])
        assert result.returncode == 0
    finally:
        os.unlink(tmp)


# ── 3. Legacy brief still works ─────────────────────────────────


def test_legacy_brief_still_works():
    """Legacy brief intake should still produce normalized.json + report.md + intake_manifest.json."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _run([
            PYTHON, str(INTAKE_SCRIPT), str(BRIEF_RAW),
            "--output-dir", tmpdir,
        ])
        assert result.returncode == 0

        files = os.listdir(tmpdir)
        assert "normalized.json" in files
        assert "report.md" in files
        assert "intake_manifest.json" in files


def test_legacy_validate_still_works():
    """Validate should still detect brief type for legacy inputs."""
    result = _run([PYTHON, str(VALIDATE_SCRIPT), str(BRIEF_RAW)])
    assert result.returncode == 0
    assert "brief" in result.stdout


# ── 4. No cross-contamination ───────────────────────────────────


def test_daily_monitor_not_confused_with_brief():
    """Daily Monitor should not be detected as brief."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(DAILY_MONITOR_SAMPLE, f)
        tmp = f.name
    try:
        result = _run([PYTHON, str(VALIDATE_SCRIPT), tmp])
        assert "brief" not in result.stdout.split("\n")[1]
    finally:
        os.unlink(tmp)


def test_legacy_not_confused_with_daily_monitor():
    """Legacy brief should not be detected as daily_monitor."""
    result = _run([PYTHON, str(VALIDATE_SCRIPT), str(BRIEF_RAW)])
    assert "daily_monitor" not in result.stdout.split("\n")[1]


# ── 9. Window policy / validator rule tests ─────────────────────


def test_window_policy_accepted():
    """window_policy in payload should not cause intake failure."""
    data = dict(DAILY_MONITOR_SAMPLE)
    data["window_policy"] = {
        "confirmed_event_window": {"primary_start": "2026-06-30", "end": "2026-07-01"},
        "discovery_signal_window": {"default_start": "2026-06-24", "end": "2026-07-01"},
        "context_window": {"start": "2026-06-01", "end": "2026-07-01"},
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        in_path = os.path.join(tmpdir, "input.json")
        with open(in_path, "w") as f:
            json.dump(data, f)
        result = _run([PYTHON, str(INTAKE_SCRIPT), in_path, "--output-dir", tmpdir])
        assert result.returncode == 0


def test_context_window_in_event_fails():
    """event_candidate with window_match=context_window should fail validate."""
    bad = dict(DAILY_MONITOR_SAMPLE)
    bad["event_candidates"] = [dict(bad["event_candidates"][0])]
    bad["event_candidates"][0]["window_match"] = "context_window"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(bad, f)
        tmp = f.name
    try:
        result = _run([PYTHON, str(VALIDATE_SCRIPT), tmp], expect_zero=False)
        assert result.returncode != 0
        assert "context_window" in result.stdout
    finally:
        os.unlink(tmp)


def test_source_pub_unknown_high_conf_generates_warning():
    """event_candidate with source_publish_time=unknown and confidence=high should generate a warning (not hard fail)."""
    bad = dict(DAILY_MONITOR_SAMPLE)
    bad["event_candidates"] = [dict(bad["event_candidates"][0])]
    bad["event_candidates"][0]["source_publish_time"] = "unknown"
    bad["event_candidates"][0]["confidence"] = "high"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(bad, f)
        tmp = f.name
    try:
        result = _run([PYTHON, str(VALIDATE_SCRIPT), tmp], expect_zero=True)
        assert result.returncode == 0
        assert "Warnings" in result.stdout or "advisory" in result.stdout
    finally:
        os.unlink(tmp)


def test_discovery_signal_high_conf_still_fails():
    """discovery_signals with confidence=high should still fail."""
    bad = dict(DAILY_MONITOR_SAMPLE)
    bad["discovery_signals"] = [dict(bad.get("discovery_signals", [{}])[0])] if bad.get("discovery_signals") else [{"event_model": "x", "confidence": "high"}]
    bad["discovery_signals"][0]["confidence"] = "high"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(bad, f)
        tmp = f.name
    try:
        result = _run([PYTHON, str(VALIDATE_SCRIPT), tmp], expect_zero=False)
        assert result.returncode != 0
        assert "cannot be 'high'" in result.stdout
    finally:
        os.unlink(tmp)


def test_review_flags_with_high_conf_fails():
    """event_candidate with review_flags non-empty and confidence=high should fail."""
    bad = dict(DAILY_MONITOR_SAMPLE)
    bad["event_candidates"] = [dict(bad["event_candidates"][0])]
    bad["event_candidates"][0]["review_flags"] = ["naming_mismatch"]
    bad["event_candidates"][0]["confidence"] = "high"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(bad, f)
        tmp = f.name
    try:
        result = _run([PYTHON, str(VALIDATE_SCRIPT), tmp], expect_zero=False)
        assert result.returncode != 0
        assert "review_flags" in result.stdout
    finally:
        os.unlink(tmp)


def test_old_output_without_window_policy_still_works():
    """Old daily monitor output without window_policy should still pass intake."""
    with tempfile.TemporaryDirectory() as tmpdir:
        in_path = os.path.join(tmpdir, "input.json")
        with open(in_path, "w") as f:
            json.dump(DAILY_MONITOR_EMPTY, f)
        result = _run([PYTHON, str(INTAKE_SCRIPT), in_path, "--output-dir", tmpdir])
        assert result.returncode == 0
        manifest = json.loads(Path(tmpdir, "intake_manifest.json").read_text("utf-8"))
        assert manifest["record_type"] == "daily_monitor"
