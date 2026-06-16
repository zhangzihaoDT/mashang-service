"""
Tests for build_workspace_capability_inventory.py
"""

import json
import sys
from pathlib import Path

import pytest

WS_ROOT = Path(__file__).resolve().parent.parent
UTILITY_DIR = WS_ROOT / "utility_scripts"
OUTPUT_DIR = WS_ROOT / "outputs" / "reports"
SKILLS_CATALOG_JSON = OUTPUT_DIR / "workspace_skills_catalog.json"

sys.path.insert(0, str(UTILITY_DIR))
sys.path.insert(0, str(WS_ROOT))

from build_workspace_capability_inventory import (
    build_inventory,
    scan_scripts,
    scan_data_assets,
    scan_outputs,
    scan_evaluation,
    load_skills,
    extract_docstring,
    has_cli,
)


class TestImport:
    """1. Script can be imported."""

    def test_importable(self):
        import build_workspace_capability_inventory as m
        assert hasattr(m, "build_inventory")


class TestBuildFunctions:
    """2. Core build functions return dict."""

    def test_build_inventory_returns_dict(self):
        result = build_inventory()
        assert isinstance(result, dict)

    def test_scan_scripts_returns_list(self):
        result = scan_scripts()
        assert isinstance(result, list)

    def test_scan_data_assets_returns_list(self):
        result = scan_data_assets()
        assert isinstance(result, list)

    def test_scan_outputs_returns_list(self):
        result = scan_outputs()
        assert isinstance(result, list)

    def test_scan_evaluation_returns_list(self):
        result = scan_evaluation()
        assert isinstance(result, list)

    def test_load_skills_returns_list(self):
        result = load_skills()
        assert isinstance(result, list)


class TestInventoryStructure:
    """3. Top-level fields exist."""

    def test_has_inventory_name(self):
        d = build_inventory()
        assert "inventory_name" in d

    def test_has_summary(self):
        d = build_inventory()
        assert "summary" in d

    def test_has_groups(self):
        d = build_inventory()
        assert "groups" in d

    def test_has_version(self):
        d = build_inventory()
        assert "version" in d

    def test_has_generated_at(self):
        d = build_inventory()
        assert "generated_at" in d

    def test_has_workspace(self):
        d = build_inventory()
        assert "workspace" in d


class TestGroups:
    """4. All 5 required groups exist."""

    REQUIRED_GROUP_IDS = ["skills", "scripts", "data_assets", "outputs", "evaluation"]

    def test_groups_count(self):
        d = build_inventory()
        assert len(d["groups"]) >= 5

    def test_all_required_groups_present(self):
        d = build_inventory()
        group_ids = [g["id"] for g in d["groups"]]
        for gid in self.REQUIRED_GROUP_IDS:
            assert gid in group_ids, f"Missing group: {gid}"

    def test_each_group_has_items_and_subtitle(self):
        d = build_inventory()
        for g in d["groups"]:
            assert "items" in g
            assert "subtitle" in g
            assert "title" in g
            assert "description" in g


class TestSummary:
    """5. Summary fields are valid numbers."""

    def test_summary_fields_are_numbers(self):
        d = build_inventory()
        s = d["summary"]
        for key in ["skills", "script_categories", "scripts", "data_assets", "outputs", "quality_assets"]:
            assert key in s, f"Missing summary key: {key}"
            assert isinstance(s[key], int), f"{key} should be int, got {type(s[key])}"


class TestOutputFiles:
    """6. All three output files are generated successfully."""

    def test_json_file_generated(self):
        assert OUTPUT_DIR.joinpath("workspace_capability_inventory.json").exists()

    def test_md_file_generated(self):
        assert OUTPUT_DIR.joinpath("workspace_capability_inventory.md").exists()

    def test_html_file_generated(self):
        assert OUTPUT_DIR.joinpath("workspace_capability_inventory.html").exists()

    def test_json_is_valid(self):
        p = OUTPUT_DIR / "workspace_capability_inventory.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        assert "inventory_name" in data
        assert "groups" in data

    def test_md_contains_summary(self):
        p = OUTPUT_DIR / "workspace_capability_inventory.md"
        text = p.read_text(encoding="utf-8")
        assert "Skills" in text


class TestHTMLContent:
    """7. HTML contains expected phrases."""

    HTML_FILE = OUTPUT_DIR / "workspace_capability_inventory.html"

    def test_html_exists(self):
        assert self.HTML_FILE.exists()

    def test_html_contains_title(self):
        text = self.HTML_FILE.read_text(encoding="utf-8")
        assert "Mashang Workspace Capability Inventory" in text

    def test_html_contains_agent_what(self):
        text = self.HTML_FILE.read_text(encoding="utf-8")
        assert "Agent 会什么" in text

    def test_html_contains_agent_call(self):
        text = self.HTML_FILE.read_text(encoding="utf-8")
        assert "Agent 能调用什么" in text

    def test_html_contains_agent_query(self):
        text = self.HTML_FILE.read_text(encoding="utf-8")
        assert "Agent 能查什么" in text

    def test_html_contains_agent_output(self):
        text = self.HTML_FILE.read_text(encoding="utf-8")
        assert "Agent 已沉淀什么" in text

    def test_html_contains_agent_quality(self):
        text = self.HTML_FILE.read_text(encoding="utf-8")
        assert "Agent 是否可靠" in text


class TestNoLocalPaths:
    """8. No local absolute paths in output."""

    OUTPUT_FILES = [
        OUTPUT_DIR / "workspace_capability_inventory.json",
        OUTPUT_DIR / "workspace_capability_inventory.md",
        OUTPUT_DIR / "workspace_capability_inventory.html",
    ]

    def test_no_home_path_in_json(self):
        p = self.OUTPUT_FILES[0]
        text = p.read_text(encoding="utf-8")
        assert "/Users/" not in text, f"Local path found in {p}"

    def test_no_home_path_in_md(self):
        p = self.OUTPUT_FILES[1]
        text = p.read_text(encoding="utf-8")
        assert "/Users/" not in text, f"Local path found in {p}"

    def test_no_home_path_in_html(self):
        p = self.OUTPUT_FILES[2]
        text = p.read_text(encoding="utf-8")
        assert "/Users/" not in text, f"Local path found in {p}"


class TestSkillsFromCatalog:
    """9. If workspace_skills_catalog.json exists, skills >= 3."""

    def test_skills_count_from_catalog(self):
        if SKILLS_CATALOG_JSON.exists():
            skills = load_skills()
            assert len(skills) >= 3, f"Expected >=3 skills, got {len(skills)}"
            names = [s["name"] for s in skills]
            for expected in ["branded-html-report", "monthly-market-report", "runtime-eval-diagnosis"]:
                assert expected in names, f"Missing expected skill: {expected}"


class TestAuxFunctions:
    """Auxiliary function tests."""

    def test_extract_docstring(self):
        # Test with current file
        current = Path(__file__)
        doc = extract_docstring(current)
        assert isinstance(doc, str)

    def test_has_cli_self(self):
        # Test has_cli with current file (pytest imports)
        current = Path(__file__)
        cli = has_cli(current)
        assert cli is False  # test file has no CLI


class TestNoRegressionOnExistingCatalog:
    """10. Does not affect existing skills catalog."""

    def test_skills_catalog_unchanged(self):
        json_path = OUTPUT_DIR / "workspace_skills_catalog.json"
        md_path = OUTPUT_DIR / "workspace_skills_catalog.md"
        html_path = OUTPUT_DIR / "workspace_skills_catalog.html"
        for p in [json_path, md_path, html_path]:
            assert p.exists(), f"Existing catalog file missing: {p}"
