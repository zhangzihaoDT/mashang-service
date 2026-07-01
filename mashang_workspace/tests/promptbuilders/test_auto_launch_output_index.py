"""
Phase 6: Auto Launch Output Index / Archive tests.

Covers:
A. Empty directory
B. Multiple intake outputs
C. index.md content
D. Corrupt manifest handling
E. Makefile anti-regression
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# ── Paths ────────────────────────────────────────────────────────
_TEST_DIR = Path(__file__).resolve().parent
_WORKSPACE = _TEST_DIR.parent.parent
_PROJECT = _WORKSPACE.parent

AUTO_LAUNCH = _WORKSPACE / "promptbuilders" / "auto_launch"
INDEXER_SCRIPT = AUTO_LAUNCH / "indexers" / "build_output_index.py"
INTAKE_SCRIPT = AUTO_LAUNCH / "intake" / "process_ai_output.py"
BRIEF_RAW = AUTO_LAUNCH / "examples" / "ai_outputs" / "event_48h_sample.json"
RADAR_RAW = AUTO_LAUNCH / "examples" / "ai_outputs" / "daily_radar_sample.json"
GITIGNORE = _PROJECT / ".gitignore"

PYTHON = sys.executable


def _run(cmd, expect_zero=True, cwd=None):
    cwd = cwd or str(_WORKSPACE)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if expect_zero and result.returncode != 0:
        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr}")
    return result


def _intake(raw_path, output_dir):
    """Helper: run intake to produce one output-dir."""
    return _run([
        PYTHON, str(INTAKE_SCRIPT), str(raw_path),
        "--output-dir", output_dir,
    ])


# ── A. Empty directory ──────────────────────────────────────────


def test_index_empty_dir():
    """Empty input-dir generates index with total_records=0."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _run([
            PYTHON, str(INDEXER_SCRIPT),
            "--input-dir", tmpdir,
            "--index-json", os.path.join(tmpdir, "index.json"),
            "--index-md", os.path.join(tmpdir, "index.md"),
        ])
        assert result.returncode == 0

        idx = json.loads(Path(tmpdir, "index.json").read_text("utf-8"))
        assert idx["total_records"] == 0

        md = Path(tmpdir, "index.md").read_text("utf-8")
        assert "暂无 intake 记录" in md


def test_index_non_existent_dir():
    """Non-existent input-dir does not crash; generates empty index."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _run([
            PYTHON, str(INDEXER_SCRIPT),
            "--input-dir", os.path.join(tmpdir, "nonexistent"),
            "--index-json", os.path.join(tmpdir, "index.json"),
            "--index-md", os.path.join(tmpdir, "index.md"),
        ])
        assert result.returncode == 0
        idx = json.loads(Path(tmpdir, "index.json").read_text("utf-8"))
        assert idx["total_records"] == 0


# ── B. Multiple intake outputs ──────────────────────────────────


def test_index_two_records():
    """Index with 2 intake output-dirs finds both records."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Generate 2 intake outputs
        _intake(BRIEF_RAW, os.path.join(tmpdir, "event_48h"))
        _intake(RADAR_RAW, os.path.join(tmpdir, "daily_radar"))

        result = _run([
            PYTHON, str(INDEXER_SCRIPT),
            "--input-dir", tmpdir,
            "--index-json", os.path.join(tmpdir, "index.json"),
            "--index-md", os.path.join(tmpdir, "index.md"),
        ])
        assert result.returncode == 0

        idx = json.loads(Path(tmpdir, "index.json").read_text("utf-8"))
        assert idx["total_records"] == 2
        assert idx["generated_at"] is not None
        assert idx["input_dir"] == os.path.abspath(tmpdir)

        # Should have both types
        types = {r["record_type"] for r in idx["records"]}
        assert "event" in types
        assert "brief" in types

        # Check record keys
        keys = {r["record_key"] for r in idx["records"]}
        assert "brief_wenjie_m7_launch_2026-07-20_vs_ls8" in keys
        assert "li_i6_presale_2026-07-15" in keys


def test_index_records_have_file_paths():
    """Each record has report_path / normalized_path / raw_ai_output_path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _intake(BRIEF_RAW, os.path.join(tmpdir, "event_48h"))

        _run([
            PYTHON, str(INDEXER_SCRIPT),
            "--input-dir", tmpdir,
            "--index-json", os.path.join(tmpdir, "index.json"),
            "--index-md", os.path.join(tmpdir, "index.md"),
        ])

        idx = json.loads(Path(tmpdir, "index.json").read_text("utf-8"))
        rec = idx["records"][0]
        for field in ["report_path", "normalized_path", "raw_ai_output_path"]:
            assert field in rec, f"missing {field}"
            assert rec[field] is not None, f"{field} is None"


# ── C. index.md content ─────────────────────────────────────────


def test_index_md_contains_header():
    """index.md contains header and record_key."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _intake(BRIEF_RAW, os.path.join(tmpdir, "event_48h"))
        _intake(RADAR_RAW, os.path.join(tmpdir, "daily_radar"))

        _run([
            PYTHON, str(INDEXER_SCRIPT),
            "--input-dir", tmpdir,
            "--index-json", os.path.join(tmpdir, "index.json"),
            "--index-md", os.path.join(tmpdir, "index.md"),
        ])

        md = Path(tmpdir, "index.md").read_text("utf-8")
        assert "Auto Launch Output Index" in md
        # record_key is truncated in table, check for visible portion
        assert "brief_wenj" in md or "li_i6_pres" in md
        assert "report.md" in md
        assert "confidence" in md or "medium" in md or "high" in md


# ── D. Corrupt manifest ─────────────────────────────────────────


def test_corrupt_manifest_does_not_crash():
    """A subdir with corrupt intake_manifest.json is skipped with warning."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a valid intake first
        _intake(BRIEF_RAW, os.path.join(tmpdir, "valid_record"))

        # Create a corrupt manifest
        corrupt_dir = Path(tmpdir, "corrupt_record")
        corrupt_dir.mkdir()
        (corrupt_dir / "intake_manifest.json").write_text("not valid json{{{")

        result = _run([
            PYTHON, str(INDEXER_SCRIPT),
            "--input-dir", tmpdir,
            "--index-json", os.path.join(tmpdir, "index.json"),
            "--index-md", os.path.join(tmpdir, "index.md"),
        ])
        assert result.returncode == 0

        idx = json.loads(Path(tmpdir, "index.json").read_text("utf-8"))
        # Only the valid record should be indexed
        assert idx["total_records"] == 1
        # Warnings should exist
        assert idx["warnings"] is not None
        assert len(idx["warnings"]) >= 1
        assert "corrupt" in idx["warnings"][0].lower()


# ── E. Makefile anti-regression ─────────────────────────────────


def test_makefile_has_index_target():
    makefile = _PROJECT / "Makefile"
    text = makefile.read_text("utf-8")
    assert "auto-launch-index:" in text


def test_makefile_no_old_monitor():
    makefile = _PROJECT / "Makefile"
    text = makefile.read_text("utf-8")
    assert "auto-launch-monitor:" not in text


def test_help_text_not_monitor():
    """Help text should not describe index target as monitor."""
    makefile = _PROJECT / "Makefile"
    text = makefile.read_text("utf-8")
    idx_lines = [l for l in text.split("\n")
                 if "auto-launch-index" in l and "echo" in l]
    for line in idx_lines:
        assert "monitor" not in line.lower()
        assert "index" in line.lower() or "archive" in line.lower()
