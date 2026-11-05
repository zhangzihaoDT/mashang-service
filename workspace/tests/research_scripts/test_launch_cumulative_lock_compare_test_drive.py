"""launch_cumulative_lock_compare — 模块 8 试驾对比 smoke test（不依赖真实 dataset）。"""

import sys
from pathlib import Path

import pandas as pd

_WS_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_WS_DIR))

import research_scripts.launch_cumulative_lock_compare as mod  # noqa: E402
from research_scripts.launch_cumulative_lock_compare import (  # noqa: E402
    _gen_to_testdrive_series,
    _test_drive_compare,
    _test_drive_table,
)

_BD = {"model_series_mapping": {"L6": ["DM0", "DM1", "DM2"], "LS6": ["CM0", "CM1", "CM2", "CM3"]}}


def test_gen_to_testdrive_series_mapping():
    assert _gen_to_testdrive_series(_BD, "CM3") == "LS6"
    assert _gen_to_testdrive_series(_BD, "DM1") == "L6"
    assert _gen_to_testdrive_series(_BD, "LS9") == "LS9"
    assert _gen_to_testdrive_series(_BD, "LS9Hyper") == "LS9"  # 前缀兜底
    assert _gen_to_testdrive_series(_BD, "LS8") is None


def _fake_daily():
    rows = []
    for launch, base in [(pd.Timestamp("2025-09-10"), 200), (pd.Timestamp("2026-09-23"), 100)]:
        for off in range(-14, 5):
            rows.append({"d": launch + pd.Timedelta(days=off), "LS6": base + off, "L6": 0, "LS9": 0})
    return pd.DataFrame(rows).drop_duplicates("d").sort_values("d")


def test_test_drive_compare_aligns_and_computes(monkeypatch):
    monkeypatch.setattr(mod, "_load_test_drive_daily", _fake_daily)
    ends = {"CM2": pd.Timestamp("2025-09-10"), "CM3": pd.Timestamp("2026-09-23")}
    td = _test_drive_compare(_BD, ["CM2", "CM3"], ends, pd.Timestamp("2026-09-27"))
    assert td is not None
    assert td["gens"] == ["CM2", "CM3"]
    assert td["start_off"] == -14 and td["end_off"] == 4
    assert len(td["rows"]) == 19
    cm3 = td["per"]["CM3"]
    assert cm3["series"] == "LS6"
    assert cm3["pre7_avg"] == 96.0      # offsets -7..-1 → 93..99
    assert cm3["launch"] == 100         # offset 0
    assert cm3["post_avg"] == 102.5     # offsets 1..4 → 101..104
    assert cm3["post_sum"] == 410
    assert td["per"]["CM2"]["pre7_avg"] == 196.0


def _c_from(td):
    return {"test_drive": td, "last_date": "2026-09-27"}


def test_test_drive_table_renders(monkeypatch):
    monkeypatch.setattr(mod, "_load_test_drive_daily", _fake_daily)
    ends = {"CM2": pd.Timestamp("2025-09-10"), "CM3": pd.Timestamp("2026-09-23")}
    td = _test_drive_compare(_BD, ["CM2", "CM3"], ends, pd.Timestamp("2026-09-27"))
    assert td is not None
    html = _test_drive_table(_c_from(td))
    assert "模块 8" in html
    assert "上市前 14 天" in html and "★ 上市日" in html and "上市后 4 天" in html
    assert "上市前 7 日试驾日均" in html and "上市后 4 日合计" in html
    assert "CM2→LS6" in html and "CM3→LS6" in html
    # 上市日行有高亮
    assert "var(--zh-gold-100)" in html


def test_test_drive_table_empty_returns_empty():
    assert _test_drive_table({}) == ""
    assert _test_drive_table({"test_drive": None}) == ""
