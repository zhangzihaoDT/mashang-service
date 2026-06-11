"""
Tests for result_reference resolution in context_parser.py
"""

import sys
from pathlib import Path

_WS_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_WS_DIR))

from eval.context_parser import parse_context

TOP_LS6_LS8 = [
    {"field": "series", "value": "LS6", "metrics": {"lock_count": 75}},
    {"field": "series", "value": "LS8", "metrics": {"lock_count": 75}},
]


def test_unique_value_resolved():
    """唯一数值匹配：top_entities 中只有一个 75。"""
    ctx = {"top_entities": [{"field": "series", "value": "LS8", "metrics": {"lock_count": 75}}]}
    r = parse_context("这 75 个锁单城市分布", previous_result_context=ctx)
    ref = r.get("result_reference")
    assert ref is not None, "result_reference should exist"
    assert ref["status"] == "resolved", f"expected resolved, got {ref['status']}"
    assert r["resolved_context"].get("series") == "LS8"


def test_prev_context_disambiguates():
    """多候选 + previous_context.series 消歧。"""
    prev_ctx = {"series": "LS8"}
    r = parse_context("这 75 个锁单城市分布", previous_context=prev_ctx,
                      previous_result_context={"top_entities": TOP_LS6_LS8})
    ref = r.get("result_reference")
    assert ref["status"] == "resolved", f"expected resolved, got {ref['status']}"
    assert ref.get("disambiguation") == "previous_context_series"
    assert r["resolved_context"].get("series") == "LS8"


def test_explicit_series_disambiguates():
    """多候选 + 文本中显式提到 LS6。"""
    r = parse_context("这 75 个 LS6 锁单城市分布",
                      previous_result_context={"top_entities": TOP_LS6_LS8})
    ref = r.get("result_reference")
    assert ref["status"] == "resolved"
    assert ref.get("disambiguation") == "explicit_series_in_text"
    assert r["resolved_context"].get("series") == "LS6"


def test_ambiguous_no_disambiguation():
    """多候选无法消歧 → ambiguous。"""
    r = parse_context("这 75 个锁单城市分布",
                      previous_result_context={"top_entities": TOP_LS6_LS8})
    ref = r.get("result_reference")
    assert ref is not None, "result_reference should exist"
    assert ref["status"] == "ambiguous", f"expected ambiguous, got {ref['status']}"
    assert ref.get("need_clarification") is True
    assert "你指的是" in str(ref.get("clarification_question", ""))
    assert "LS6" in str(ref.get("candidates", []))
    assert "LS8" in str(ref.get("candidates", []))


def test_rank_first_reference():
    """排名第一 → 取 top_entities[0]。"""
    ctx = {"top_entities": [
        {"field": "series", "value": "LS8", "metrics": {"lock_count": 75}},
        {"field": "series", "value": "LS6", "metrics": {"lock_count": 62}},
    ]}
    r = parse_context("排名第一的车型城市分布", previous_result_context=ctx)
    ref = r.get("result_reference")
    assert ref["status"] == "resolved", f"expected resolved, got {ref['status']}"
    assert ref["type"] == "rank_reference"
    assert r["resolved_context"].get("series") == "LS8"


def test_entity_reference():
    """刚才那个车型 → 取 top_entities[0]。"""
    ctx = {"top_entities": [
        {"field": "series", "value": "LS8", "metrics": {"lock_count": 75}},
    ]}
    r = parse_context("刚才那个车型的城市分布", previous_result_context=ctx)
    ref = r.get("result_reference")
    assert ref["status"] == "resolved"
    assert r["resolved_context"].get("series") == "LS8"


def test_reference_no_match():
    """数值不匹配任何 top_entities 时应有反馈。"""
    ctx = {"top_entities": [
        {"field": "series", "value": "LS8", "metrics": {"lock_count": 75}},
    ]}
    r = parse_context("这 999 个锁单城市分布", previous_result_context=ctx)
    ref = r.get("result_reference")
    assert ref is not None
    assert ref["status"] == "no_match"
