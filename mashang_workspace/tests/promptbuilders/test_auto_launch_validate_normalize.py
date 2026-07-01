"""
Phase 3: Auto Launch validate + normalize tests.

Covers:
A. validate success
B. validate failure
C. normalize success
D. CLI availability
E. Compatibility with Phase 2 tests
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Paths
_TEST_DIR = Path(__file__).resolve().parent
_WORKSPACE = _TEST_DIR.parent.parent  # mashang_workspace/
VALIDATORS = _WORKSPACE / "promptbuilders" / "auto_launch" / "validators"
EXAMPLES = _WORKSPACE / "promptbuilders" / "auto_launch" / "examples"
AI_OUTPUTS = EXAMPLES / "ai_outputs"
NORMALIZED = EXAMPLES / "normalized"

RADAR_SAMPLE = AI_OUTPUTS / "daily_radar_sample.json"
BRIEF_SAMPLE = AI_OUTPUTS / "event_48h_sample.json"
RADAR_NORM = NORMALIZED / "daily_radar_sample.normalized.json"
BRIEF_NORM = NORMALIZED / "event_48h_sample.normalized.json"

VALIDATE_SCRIPT = VALIDATORS / "validate_ai_response.py"
NORMALIZE_SCRIPT = VALIDATORS / "normalize_ai_response.py"

PYTHON = sys.executable


# ── Helpers ──────────────────────────────────────────────────────


def _run_validate(path, expect_zero=True):
    """Run validate_ai_response.py and return (returncode, stdout)."""
    result = subprocess.run(
        [PYTHON, str(VALIDATE_SCRIPT), str(path)],
        capture_output=True, text=True, cwd=str(_WORKSPACE)
    )
    if expect_zero:
        assert result.returncode == 0, f"validate failed:\n{result.stdout}\n{result.stderr}"
    return result.returncode, result.stdout


def _run_normalize(input_path, output_path, expect_zero=True):
    """Run normalize_ai_response.py and return (returncode, stdout)."""
    result = subprocess.run(
        [PYTHON, str(NORMALIZE_SCRIPT), str(input_path), "--output", str(output_path)],
        capture_output=True, text=True, cwd=str(_WORKSPACE)
    )
    if expect_zero:
        assert result.returncode == 0, f"normalize failed:\n{result.stdout}\n{result.stderr}"
    return result.returncode, result.stdout


# ── A. Validate success ──────────────────────────────────────────


def test_validate_daily_radar_passes():
    code, out = _run_validate(RADAR_SAMPLE)
    assert "[auto_launch validate] OK" in out
    assert "type: event" in out


def test_validate_event_48h_passes():
    code, out = _run_validate(BRIEF_SAMPLE)
    assert "[auto_launch validate] OK" in out
    assert "type: brief" in out


# ── B. Validate failure ─────────────────────────────────────────


def test_validate_fails_on_missing_source_items():
    bad = {"event_id": "test", "battle_field": "test"}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(bad, f)
        tmp = f.name
    try:
        code, out = _run_validate(tmp, expect_zero=False)
        assert code != 0
        assert "[auto_launch validate] FAIL" in out
    finally:
        os.unlink(tmp)


def test_validate_fails_on_missing_confidence_level():
    bad = {
        "event_id": "test_event",
        "event": {"brand": "x", "model": "x", "event_type": "x", "event_date": "2026-01-01"},
        "event_brand": "x",
        "event_model": "x",
        "event_type": "x",
        "event_date": "2026-01-01",
        "battle_field": "test",
        "source_items": [{"tier": 1, "name": "x", "url": "https://x.com"}],
        "confirmed_facts": ["x"],
        "inferences": ["x"],
        "unconfirmed_claims": ["x"],
        "missing_evidence": ["x"],
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(bad, f)
        tmp = f.name
    try:
        code, out = _run_validate(tmp, expect_zero=False)
        assert code != 0
        assert "confidence_level" in out
    finally:
        os.unlink(tmp)


def test_validate_fails_on_missing_confirmed_facts():
    bad = {
        "event_id": "test_event",
        "event": {"brand": "x", "model": "x", "event_type": "x", "event_date": "2026-01-01"},
        "event_brand": "x",
        "event_model": "x",
        "event_type": "x",
        "event_date": "2026-01-01",
        "battle_field": "test",
        "source_items": [{"tier": 1, "name": "x", "url": "https://x.com"}],
        "confidence_level": "high",
        "inferences": ["x"],
        "unconfirmed_claims": ["x"],
        "missing_evidence": ["x"],
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(bad, f)
        tmp = f.name
    try:
        code, out = _run_validate(tmp, expect_zero=False)
        assert code != 0
        assert "confirmed_facts" in out
    finally:
        os.unlink(tmp)


# ── C. Normalize success ────────────────────────────────────────


def test_normalize_daily_radar_record_type():
    assert RADAR_NORM.exists()
    data = json.loads(RADAR_NORM.read_text("utf-8"))
    assert data["record_type"] == "event"
    assert data["raw"]["event_id"] == "li_i6_presale_2026-07-15"


def test_normalize_event_48h_record_type():
    assert BRIEF_NORM.exists()
    data = json.loads(BRIEF_NORM.read_text("utf-8"))
    assert data["record_type"] == "brief"
    assert data["record_key"] == "brief_wenjie_m7_launch_2026-07-20_vs_ls8"


def test_normalize_contains_raw():
    data = json.loads(RADAR_NORM.read_text("utf-8"))
    assert "raw" in data
    assert isinstance(data["raw"], dict)
    assert data["raw"]["event_id"] == "li_i6_presale_2026-07-15"


def test_normalize_classification_not_mixed():
    data = json.loads(RADAR_NORM.read_text("utf-8"))
    # Ensure inferences and unconfirmed_claims don't leak into confirmed_facts
    for inference in data["inferences"]:
        assert inference not in data["confirmed_facts"]
    for claim in data["unconfirmed_claims"]:
        assert claim not in data["confirmed_facts"]

    data2 = json.loads(BRIEF_NORM.read_text("utf-8"))
    for inference in data2["inferences"]:
        assert inference not in data2["confirmed_facts"]
    for claim in data2["unconfirmed_claims"]:
        assert claim not in data2["confirmed_facts"]


# ── D. CLI availability ──────────────────────────────────────────


def test_validate_cli_available():
    assert VALIDATE_SCRIPT.exists()
    # Check it prints usage when called without args
    result = subprocess.run(
        [PYTHON, str(VALIDATE_SCRIPT)],
        capture_output=True, text=True, cwd=str(_WORKSPACE)
    )
    assert result.returncode != 0
    assert "Usage:" in result.stderr


def test_normalize_cli_has_output_flag():
    assert NORMALIZE_SCRIPT.exists()
    result = subprocess.run(
        [PYTHON, str(NORMALIZE_SCRIPT), "--help"],
        capture_output=True, text=True, cwd=str(_WORKSPACE)
    )
    assert result.returncode in (0, 2)
    assert "--output" in result.stdout or "-o" in result.stdout

    # Also verify it fails without --output
    result2 = subprocess.run(
        [PYTHON, str(NORMALIZE_SCRIPT), str(RADAR_SAMPLE)],
        capture_output=True, text=True, cwd=str(_WORKSPACE)
    )
    assert result2.returncode != 0


# ── E. Compatibility with Phase 2 tests ─────────────────────────


def test_phase_2_tests_still_pass():
    """Run the Phase 2 test file as a subprocess to confirm no regression."""
    phase2_test = _TEST_DIR / "test_auto_launch_prompt_workflow.py"
    assert phase2_test.exists()
    result = subprocess.run(
        [PYTHON, "-m", "pytest", str(phase2_test), "-q", "--tb=short"],
        capture_output=True, text=True, cwd=str(_WORKSPACE.parent)
    )
    assert result.returncode == 0, f"Phase 2 tests failed:\n{result.stdout}\n{result.stderr}"


# ── F. URL normalization ─────────────────────────────────────────


def _run_normalize(input_data, output_path):
    """Run normalize as subprocess via process_ai_output (full pipe)."""
    import tempfile
    in_path = os.path.join(tempfile.mkdtemp(), "input.json")
    with open(in_path, "w") as f:
        json.dump(input_data, f)
    result = subprocess.run(
        [PYTHON, str(NORMALIZE_SCRIPT), in_path, "--output", output_path],
        capture_output=True, text=True, cwd=str(_WORKSPACE)
    )
    return result


def test_normalize_cleans_markdown_link_url():
    """source_url in Markdown link format should be cleaned to pure URL."""
    sample = {
        "event_id": "test_event",
        "event": {"brand": "x", "model": "x", "event_type": "x", "event_date": "2026-01-01"},
        "battle_field": "test",
        "source_items": [{"source_url": "[https://example.com](https://example.com)"}],
        "confirmed_facts": ["x"], "inferences": ["x"],
        "unconfirmed_claims": ["x"], "missing_evidence": ["x"],
        "confidence_level": "medium",
    }
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        out = f.name
    try:
        result = _run_normalize(sample, out)
        assert result.returncode == 0
        data = json.loads(Path(out).read_text("utf-8"))
        url = data["source_items"][0]["source_url"]
        assert url == "https://example.com", f"URL not cleaned: {url}"
    finally:
        os.unlink(out)


def test_normalize_keeps_clean_url():
    """Normalize should keep already clean URLs unchanged."""
    sample = {
        "event_id": "test_event",
        "event": {"brand": "x", "model": "x", "event_type": "x", "event_date": "2026-01-01"},
        "battle_field": "test",
        "source_items": [{"source_url": "https://example.com/page"}],
        "confirmed_facts": ["x"], "inferences": ["x"],
        "unconfirmed_claims": ["x"], "missing_evidence": ["x"],
        "confidence_level": "medium",
    }
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        out = f.name
    try:
        result = _run_normalize(sample, out)
        assert result.returncode == 0
        data = json.loads(Path(out).read_text("utf-8"))
        assert data["source_items"][0]["source_url"] == "https://example.com/page"
    finally:
        os.unlink(out)


def test_normalize_handles_empty_url():
    """Normalize should handle missing / empty source_url gracefully."""
    sample = {
        "event_id": "test_event",
        "event": {"brand": "x", "model": "x", "event_type": "x", "event_date": "2026-01-01"},
        "battle_field": "test",
        "source_items": [{"source_url": ""}],
        "confirmed_facts": ["x"], "inferences": ["x"],
        "unconfirmed_claims": ["x"], "missing_evidence": ["x"],
        "confidence_level": "medium",
    }
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        out = f.name
    try:
        result = _run_normalize(sample, out)
        assert result.returncode == 0
        data = json.loads(Path(out).read_text("utf-8"))
        assert data["source_items"][0]["source_url"] == ""
    finally:
        os.unlink(out)
