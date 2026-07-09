"""v1.0.2 Smoke Hardening 测试"""
import sys, json
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


# ── 1. Brief date from input ──────────────────────────────────────

def test_brief_date_from_input():
    """generate_brief 使用传入的 brief_date 而非 datetime.today()"""
    from auto_launch.src.brief_renderer import generate_brief
    facts = [
        {"brand": "极氪", "model": "9X", "event_type": "预售", "event_date": "2026-07-08",
         "title": "test", "source_tier": "tier_1_official", "seen_count": 1,
         "first_seen": "2026-07-08", "last_seen": "2026-07-08"},
    ]
    brief = generate_brief(facts, brief_date="2026-07-08")
    assert "2026-07-08" in brief.split("\n")[0]
    assert "2026-07-09" not in brief.split("\n")[0]


def test_brief_date_from_event_date():
    """无 brief_date 时从事实 event_date 推导"""
    from auto_launch.src.brief_renderer import generate_brief
    facts = [
        {"brand": "A", "event_type": "权益调整", "event_date": "2026-07-07",
         "title": "t1", "source_tier": "tier_1_official", "seen_count": 1,
         "first_seen": "2026-07-07", "last_seen": "2026-07-07"},
        {"brand": "B", "event_type": "交付", "event_date": "2026-07-07",
         "title": "t2", "source_tier": "tier_1_official", "seen_count": 1,
         "first_seen": "2026-07-07", "last_seen": "2026-07-07"},
    ]
    brief = generate_brief(facts)
    assert "2026-07-07" in brief.split("\n")[0]


# ── 2. Top brand observation ──────────────────────────────────────

def test_observation_omits_top_brand_when_all_one():
    """所有品牌都是 1 条时，不输出最活跃品牌"""
    from auto_launch.src.brief_renderer import generate_brief
    facts = [
        {"brand": "极氪", "event_type": "预售", "event_date": "2026-07-08",
         "title": "t1", "source_tier": "tier_1_official", "seen_count": 1,
         "first_seen": "2026-07-08", "last_seen": "2026-07-08"},
        {"brand": "蔚来", "event_type": "发布会", "event_date": "2026-07-08",
         "title": "t2", "source_tier": "tier_3_industry_media", "seen_count": 1,
         "first_seen": "2026-07-08", "last_seen": "2026-07-08"},
    ]
    brief = generate_brief(facts, brief_date="2026-07-08")
    assert "品牌分布较分散" in brief
    assert "最活跃品牌" not in brief


def test_observation_shows_top_brand_when_count_ge_2():
    """同一品牌有 2+ 条时，显示最活跃品牌"""
    from auto_launch.src.brief_renderer import generate_brief
    facts = [
        {"brand": "智己", "event_type": "权益调整", "event_date": "2026-07-08",
         "title": "t1", "source_tier": "tier_1_official", "seen_count": 1,
         "first_seen": "2026-07-08", "last_seen": "2026-07-08"},
        {"brand": "智己", "event_type": "交付数据", "event_date": "2026-07-08",
         "title": "t2", "source_tier": "tier_1_official", "seen_count": 1,
         "first_seen": "2026-07-08", "last_seen": "2026-07-08"},
        {"brand": "蔚来", "event_type": "发布会", "event_date": "2026-07-08",
         "title": "t3", "source_tier": "tier_3_industry_media", "seen_count": 1,
         "first_seen": "2026-07-08", "last_seen": "2026-07-08"},
    ]
    brief = generate_brief(facts, brief_date="2026-07-08")
    assert "最活跃品牌" in brief
    assert "智己" in brief.split("最活跃品牌")[1]


# ── 3. Launcher run package ───────────────────────────────────────

def _make_inputs(seq):
    it = iter(seq)
    def mock(prompt=""):
        return next(it)
    return mock


def test_launcher_daily_run_writes_run_package(monkeypatch):
    """选项 1 处理后 outputs/runs/{date}/daily_brief.md 存在"""
    from auto_launch.src.launcher import run_launcher, _run_dir
    daily = "## Test\n- 品牌: A\n- 车型: X\n- 事件类型: 上市\n- 时间: 2026-07-10\n- 来源: src\n- 信源等级: tier_1_official\n"
    monkeypatch.setattr("builtins.input", _make_inputs([
        "1", "2026-07-10", daily, "/done", "y", "6",
    ]))
    run_launcher()
    run_dir = _run_dir("2026-07-10")
    assert (run_dir / "daily_brief.md").exists()
    assert "2026-07-10" in (run_dir / "daily_brief.md").read_text(encoding="utf-8").split("\n")[0]


def test_launcher_daily_run_manifest_contains_counts(monkeypatch):
    """run_manifest.json 包含 raw/keep/discard/inserted/updated"""
    from auto_launch.src.launcher import run_launcher, _run_dir
    daily = "## Test\n- 品牌: B\n- 车型: Y\n- 事件类型: 预售\n- 时间: 2026-07-10\n- 来源: src\n- 信源等级: tier_1_official\n"
    monkeypatch.setattr("builtins.input", _make_inputs([
        "1", "2026-07-10", daily, "/done", "y", "6",
    ]))
    run_launcher()
    mf = _run_dir("2026-07-10") / "run_manifest.json"
    assert mf.exists()
    data = json.loads(mf.read_text(encoding="utf-8"))
    assert "raw" in data
    assert "kept" in data
    assert "discarded" in data
    assert "inserted" in data
    assert "updated" in data
    assert data["command"] == "launcher_daily_run"


def test_launcher_daily_run_summary_contains_keep_discard(monkeypatch):
    """run_summary.md 包含 keep/discard 信息"""
    from auto_launch.src.launcher import run_launcher, _run_dir
    daily = "## Test\n- 品牌: C\n- 车型: Z\n- 事件类型: 交付\n- 时间: 2026-07-10\n- 来源: src\n- 信源等级: tier_3_industry_media\n"
    monkeypatch.setattr("builtins.input", _make_inputs([
        "1", "2026-07-10", daily, "/done", "y", "6",
    ]))
    run_launcher()
    md = _run_dir("2026-07-10") / "run_summary.md"
    assert md.exists()
    content = md.read_text(encoding="utf-8")
    assert "Kept" in content
    assert "Discarded" in content
    assert "Raw items" in content


def test_outputs_inspect_recognizes_launcher_run(monkeypatch):
    """outputs inspect 能看到 launcher 产出的 runs"""
    from auto_launch.src.launcher import run_launcher, _run_dir
    from auto_launch.src.output_manager import inspect
    daily = "## Test\n- 品牌: D\n- 车型: W\n- 事件类型: 权益调整\n- 时间: 2026-07-10\n- 来源: src\n- 信源等级: tier_1_official\n"
    monkeypatch.setattr("builtins.input", _make_inputs([
        "1", "2026-07-10", daily, "/done", "y", "6",
    ]))
    run_launcher()
    report = inspect()
    dates = [r["date"] for r in report["runs"]["list"]]
    assert "2026-07-10" in dates


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
