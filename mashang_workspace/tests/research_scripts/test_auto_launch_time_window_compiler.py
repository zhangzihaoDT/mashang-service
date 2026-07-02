"""时间窗口转译测试"""
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[2]))
from research_scripts.auto_launch.search_intent_compiler import infer_time_window
from research_scripts.auto_launch.normalize_search_results import _check_time_window


def test_recent_7_days():
    tw = infer_time_window("看看极氪最近 7 天都有什么动作", "2026-07-02")
    assert tw["days"] == 7
    assert tw["start_date"] == "2026-06-25"
    assert tw["end_date"] == "2026-07-02"
    assert tw["timezone"] == "Asia/Shanghai"
    assert tw["start_datetime"] == "2026-06-25T00:00:00+08:00"
    assert tw["end_datetime"] == "2026-07-02T23:59:59+08:00"
    print("[PASS] test_recent_7_days")


def test_jin_yi_zhou():
    tw = infer_time_window("看看极氪近一周有什么动作", "2026-07-02")
    assert tw["days"] == 7
    print("[PASS] test_jin_yi_zhou")


def test_today():
    tw = infer_time_window("看看极氪今天有没有动作", "2026-07-02")
    assert tw["window_type"] == "today"
    assert tw["start_date"] == "2026-07-02"
    assert tw["end_date"] == "2026-07-02"
    print("[PASS] test_today")


def test_yesterday():
    tw = infer_time_window("看看极氪昨天有什么动作", "2026-07-02")
    assert tw["days"] == 1
    assert tw["start_date"] == "2026-07-01"
    assert tw["end_date"] == "2026-07-02"
    print("[PASS] test_yesterday")


def test_recent_48_hours():
    tw = infer_time_window("看看极氪最近 48 小时有什么动作", "2026-07-02")
    assert tw["days"] == 2
    print("[PASS] test_recent_48_hours")


def test_past_month():
    tw = infer_time_window("看看极氪过去一个月有什么动作", "2026-07-02")
    assert tw["days"] == 30
    print("[PASS] test_past_month")


def test_in_window():
    result = _check_time_window("2026-06-30T10:00:00+08:00",
                                {"start_date": "2026-06-25", "end_date": "2026-07-02"})
    assert result["time_window_status"] == "in_window"
    assert result["is_out_of_window"] is False
    print("[PASS] test_in_window")


def test_out_of_window_early():
    result = _check_time_window("2025-03-18T10:00:00+08:00",
                                {"start_date": "2026-06-25", "end_date": "2026-07-02"})
    assert result["time_window_status"] == "out_of_window"
    assert result["is_out_of_window"] is True
    print("[PASS] test_out_of_window_early")


def test_unknown_publish_time():
    result = _check_time_window("", {"start_date": "2026-06-25", "end_date": "2026-07-02"})
    assert "unknown" in result["time_window_status"]
    assert result["is_out_of_window"] is None
    print("[PASS] test_unknown_publish_time")
