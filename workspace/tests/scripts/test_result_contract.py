"""
Tests for utils/result_contract.py
"""

import sys, json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from utils.result_contract import (
    build_success_contract, build_partial_contract, build_error_contract,
    save_contract_json, contract_to_terminal,
)


def test_success_contract_structure():
    c = build_success_contract(
        script="test.py", command="python test.py",
        scope={"data_source": "test.csv", "metric_definition": "count"},
        result={"summary": "test ok", "metrics": {"count": 42}},
    )
    assert c["status"] == "success"
    assert c["script"] == "test.py"
    assert c["result"]["metrics"]["count"] == 42
    assert "generated_at" in c
    assert c["errors"] == []
    assert c["warnings"] == []


def test_partial_contract():
    c = build_partial_contract(
        script="partial.py", command="python partial.py",
        scope={}, result={"summary": "partial"},
        warnings=["能力未完全实现"],
    )
    assert c["status"] == "partial_success"
    assert len(c["warnings"]) == 1


def test_error_contract():
    c = build_error_contract(
        script="error.py", command="python error.py",
        error_message="something broke",
    )
    assert c["status"] == "error"
    assert len(c["errors"]) == 1
    assert c["errors"][0]["message"] == "something broke"


def test_save_contract(tmp_path):
    c = build_success_contract(script="s.py", command="cmd", scope={}, result={})
    out = save_contract_json(c, tmp_path / "contract.json", print_info=False)
    assert out.exists()
    loaded = json.loads(out.read_text())
    assert loaded["status"] == "success"


def test_contract_to_terminal():
    c = build_success_contract(
        script="t.py", command="cmd",
        scope={"data_source": "ds.csv"},
        result={"summary": "hello", "metrics": {"x": 1}},
    )
    text = contract_to_terminal(c)
    assert "[Summary]" in text
    assert "[Scope]" in text
    assert "ds.csv" in text
    assert "x: 1" in text


def test_followup_context_inheritance():
    """contract->followup_context 包含 top_entities 供下一轮追问。"""
    from utils.result_contract import make_followup_context
    ctx = make_followup_context(
        metric="lock_count", date="2026-06-10", series="LS8",
        available_dimensions=["series", "city"],
        top_entities=[{"field": "series", "value": "LS8", "metrics": {"lock_count": 75}}],
    )
    assert ctx["metric"] == "lock_count"
    assert ctx["date"] == "2026-06-10"
    assert len(ctx["top_entities"]) == 1
    assert ctx["top_entities"][0]["value"] == "LS8"
