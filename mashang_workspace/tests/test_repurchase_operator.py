"""
Tests for shared/operators/repurchase — 复购 / 老车主拆分算子
"""

import json
import sys
from pathlib import Path

import pandas as pd

_WS_DIR = Path(__file__).resolve().parents[1]
_PRJ_DIR = _WS_DIR.parent
sys.path.insert(0, str(_WS_DIR))


def _ensure_shared_operators():
    """确保导入的是 shared/operators 而非 mashang_runtime/operators。"""
    for _k in [k for k in list(sys.modules) if k == "operators" or k.startswith("operators.")]:
        del sys.modules[_k]
    from utils.paths import ensure_shared_on_path
    ensure_shared_on_path()


def _window_df() -> pd.DataFrame:
    """窗口（2026-08-28 ~ 2026-09-06）零售锁单 + 窗口前历史。

    场景构造（owner_identity_no 末三位用于记忆）：
      A..234  历史 2024 已兑现（交付/开票 2024-06）→ prior_fulfilled
      B..235  历史 2025 锁单但从未交付/开票 → prior_unfulfilled（悬置）
      C..236  无历史 → no_prior_history
      D..237  历史 2025 锁单、窗口后才兑现（2026-09-15）→ PIT：该窗口下仍 prior_unfulfilled
      E..000  窗口内订单身份无效 → unknown_identity
      F..238  历史 2024 已兑现（有交付）→ prior_fulfilled（仅交付路径）
    """
    start = pd.Timestamp("2026-08-28")
    end = pd.Timestamp("2026-09-06")
    hist = pd.DataFrame([
        # order, series_group, lock, delivery, invoice, owner_identity_no
        ("H1", "DM0", pd.Timestamp("2024-05-01"), pd.Timestamp("2024-06-01"), pd.Timestamp("2024-06-01"), "310101199001011234"),
        ("H2", "DM1", pd.Timestamp("2025-05-20"), pd.NaT, pd.NaT, "310101199201011235"),
        ("H3", "DM1", pd.Timestamp("2025-05-21"), pd.Timestamp("2026-09-15"), pd.Timestamp("2026-09-15"), "310101199301011237"),
        ("H4", "DM0", pd.Timestamp("2024-06-01"), pd.Timestamp("2024-07-01"), pd.NaT, "310101199401011238"),
    ])
    window = pd.DataFrame([
        ("W1", "DM2", pd.Timestamp("2026-08-29"), pd.NaT, pd.NaT, "310101199001011234"),
        ("W2", "DM2", pd.Timestamp("2026-08-30"), pd.NaT, pd.NaT, "310101199201011235"),
        ("W3", "DM2", pd.Timestamp("2026-08-31"), pd.NaT, pd.NaT, "310101199501011236"),
        ("W4", "DM2", pd.Timestamp("2026-09-01"), pd.NaT, pd.NaT, "310101199301011237"),
        ("W5", "DM2", pd.Timestamp("2026-09-02"), pd.NaT, pd.NaT, "00000"),
        ("W6", "DM2", pd.Timestamp("2026-09-03"), pd.NaT, pd.NaT, "310101199401011238"),
    ])
    cols = ["order_number", "series_group_logic", "lock_time",
            "delivery_date", "invoice_upload_time", "owner_identity_no"]
    hist.columns = cols
    window.columns = cols
    df = pd.concat([hist, window], ignore_index=True)
    return df, start, end


def test_registry_entries():
    reg = json.loads((_PRJ_DIR / "shared" / "operators" / "registry.json").read_text())
    assert "repurchase" in reg["operators"]
    assert "repurchase" in reg["intent_map"]
    assert reg["intent_map"]["repurchase"]["operator"] == "repurchase"


def test_catalog_entry():
    catalog = json.loads((_PRJ_DIR / "shared" / "operators" / "operator_catalog.json").read_text())
    titles = [e.get("title") for e in catalog]
    assert any("复购" in (t or "") for t in titles)


def test_importable():
    _ensure_shared_operators()
    from operators.repurchase import split_repurchase, run_repurchase_operator
    assert callable(split_repurchase)
    assert callable(run_repurchase_operator)


def test_fulfilled_repurchase_canonical_buckets():
    """canonical 模式：互斥四桶；悬置/未来兑现不计复购。"""
    _ensure_shared_operators()
    from operators.repurchase import split_repurchase

    df, start, end = _window_df()
    r = split_repurchase(df, start, end, series="DM2")
    assert "error" not in r, r
    b = r["buckets"]
    # 6 个窗口订单：W1(已兑现历史) / W2(悬置) / W3(无历史) / W4(PIT 未来兑现) / W5(无效) / W6(仅交付兑现)
    assert b == {
        "prior_fulfilled": 2,      # W1, W6
        "prior_unfulfilled": 2,    # W2(悬置), W4(PIT: 窗口后才兑现)
        "no_prior_history": 1,     # W3
        "unknown_identity": 1,     # W5
    }, b
    s = r["summary"]
    assert s["repeat"] == 2        # prior_fulfilled only
    assert s["suspended"] == 2     # prior_unfulfilled 单列
    assert s["first"] == 1
    assert s["unknown"] == 1
    assert s["n"] == 6


def test_prior_locker_mode_overlaps_into_repeat():
    """prior_locker 宽松模式：prior_unfulfilled 并入 repeat，不悬置；桶仍互斥。"""
    _ensure_shared_operators()
    from operators.repurchase import split_repurchase, MODE_PRIOR_LOCKER

    df, start, end = _window_df()
    r = split_repurchase(df, start, end, series="DM2", mode=MODE_PRIOR_LOCKER)
    s = r["summary"]
    assert s["repeat"] == 4        # W1 + W6 + W2(悬置) + W4(PIT 未来兑现)
    assert s["suspended"] == 0
    assert s["first"] == 1
    assert s["unknown"] == 1
    assert s["known"] == 5
    # 桶计数（底层）不受 mode 影响
    b = r["buckets"]
    assert b["prior_fulfilled"] == 2 and b["prior_unfulfilled"] == 2


def test_pit_no_lookahead_into_window():
    """PIT 不穿越：窗口前锁单、窗口后才兑现 → 该窗口下为 prior_unfulfilled，
    换到更晚窗口（兑现已发生）再评估 → prior_fulfilled。"""
    _ensure_shared_operators()
    from operators.repurchase import split_repurchase

    df, start, _ = _window_df()
    # 窗口1: 2026-08-28 ~ 09-06（兑现 09-15 尚未发生）→ W4 该身份为悬置
    r1 = split_repurchase(df, start, pd.Timestamp("2026-09-06"), series="DM2")
    assert r1["buckets"]["prior_fulfilled"] == 2
    assert r1["buckets"]["prior_unfulfilled"] == 2
    # 更晚窗口: 2026-09-16 ~ 09-26（09-15 兑现已发生）→ 该身份转 prior_fulfilled
    late = pd.DataFrame([
        ("W7", "DM2", pd.Timestamp("2026-09-17"), pd.NaT, pd.NaT, "310101199301011237"),
    ], columns=df.columns.tolist())
    df2 = pd.concat([df, late], ignore_index=True)
    r2 = split_repurchase(df2, pd.Timestamp("2026-09-16"), pd.Timestamp("2026-09-26"),
                          series="DM2")
    assert r2["buckets"]["prior_fulfilled"] == 1  # W7
    assert r2["buckets"]["prior_unfulfilled"] == 0
    assert r2["summary"]["repeat"] == 1


def test_run_operator_entrypoint():
    """run_repurchase_operator 通过 ISO 字符串调用，等价 split。"""
    _ensure_shared_operators()
    from operators.repurchase import run_repurchase_operator

    df, start, end = _window_df()
    r = run_repurchase_operator(df, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"),
                                series="DM2")
    assert r["summary"]["repeat"] == 2
    assert r["mode"] == "fulfilled_repurchase"
