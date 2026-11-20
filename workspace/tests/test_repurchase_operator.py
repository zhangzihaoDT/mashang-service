"""
Tests for shared/operators/repurchase — 复购 / 老车主拆分算子（v2 · B 方案）

v2 口径要点：
  - 身份用手机号哈希（lead_phone_md5），为「同号复购」，非车主身份
  - 仅计窗口前**已完成购车**（交付或开票早于 window_start）为复购
  - 共享号码（窗口前已兑现历史中关联 ≥2 个 owner_identity_no）整号剔除
  - 四桶互斥且穷尽：prior_fulfilled / no_prior_history /
    shared_phone_excluded / unknown_identity
  - 不保留 prior_locker 宽松模式
"""

import json
import sys
from pathlib import Path

import pandas as pd

_WS_DIR = Path(__file__).resolve().parents[1]
_PRJ_DIR = _WS_DIR.parent
sys.path.insert(0, str(_WS_DIR))


def _ensure_shared_operators():
    """确保导入的是 shared/operators canonical 实现。"""
    for _k in [k for k in list(sys.modules) if k == "operators" or k.startswith("operators.")]:
        del sys.modules[_k]
    from utils.paths import ensure_shared_on_path
    ensure_shared_on_path()


COLS = ["order_number", "series_group_logic", "lock_time",
        "delivery_date", "invoice_upload_time", "lead_phone_md5", "owner_identity_no"]

P_A = "a" * 32   # 历史已兑现 → 复购
P_B = "b" * 32   # 历史仅锁单未兑现 → 首购（悬置不计）
P_C = "c" * 32   # 无历史 → 首购
P_D = "d" * 32   # 历史锁单、窗口后才兑现 → 该窗口下首购（PIT）
P_E = None       # 身份缺失 → unknown
P_F = "e" * 32   # 历史仅交付（无开票）→ 复购
P_S = "f" * 32   # 共享号码：历史中关联 2 个身份证 → 剔除
P_G = "0123456789abcdef0123456789abcdef"  # 完全无历史


def _window_df():
    """构造 v2 测试数据（窗口 2026-08-28 ~ 2026-09-06，series=DM2）。

    历史（窗口前）：
      H1 P_A 2024-05 锁, 2024-06 交付/开票         → P_A 已完成购车
      H2 P_B 2025-05 锁, 未交付未开票               → P_B 未完成
      H3 P_D 2025-05 锁, 2026-09-15 交付            → 晚于窗口，不算
      H4 P_F 2024-06 锁, 2024-07 交付（无开票）      → P_F 已完成购车
      H5 P_S 2024-03 锁, 2024-04 交付, 身份证 X      ┐ 共享号码
      H6 P_S 2024-03 锁, 2024-04 交付, 身份证 Y      ┘ 两个不同身份证
    """
    start = pd.Timestamp("2026-08-28")
    end = pd.Timestamp("2026-09-06")
    X = "310101199001010001"
    Y = "310101199001010002"
    hist = pd.DataFrame([
        ("H1", "DM0", pd.Timestamp("2024-05-01"), pd.Timestamp("2024-06-01"), pd.Timestamp("2024-06-01"), P_A, "310101199001011234"),
        ("H2", "DM1", pd.Timestamp("2025-05-20"), pd.NaT, pd.NaT, P_B, "310101199201011235"),
        ("H3", "DM1", pd.Timestamp("2025-05-21"), pd.Timestamp("2026-09-15"), pd.Timestamp("2026-09-15"), P_D, "310101199301011237"),
        ("H4", "DM0", pd.Timestamp("2024-06-01"), pd.Timestamp("2024-07-01"), pd.NaT, P_F, "310101199401011238"),
        ("H5", "DM0", pd.Timestamp("2024-03-01"), pd.Timestamp("2024-04-01"), pd.Timestamp("2024-04-01"), P_S, X),
        ("H6", "DM0", pd.Timestamp("2024-03-02"), pd.Timestamp("2024-04-02"), pd.Timestamp("2024-04-02"), P_S, Y),
    ], columns=COLS)
    window = pd.DataFrame([
        ("W1", "DM2", pd.Timestamp("2026-08-29"), pd.NaT, pd.NaT, P_A, "310101199001011234"),
        ("W2", "DM2", pd.Timestamp("2026-08-30"), pd.NaT, pd.NaT, P_B, "310101199201011235"),
        ("W3", "DM2", pd.Timestamp("2026-08-31"), pd.NaT, pd.NaT, P_C, "310101199501011236"),
        ("W4", "DM2", pd.Timestamp("2026-09-01"), pd.NaT, pd.NaT, P_D, "310101199301011237"),
        ("W5", "DM2", pd.Timestamp("2026-09-02"), pd.NaT, pd.NaT, P_E, "310101199501011239"),
        ("W6", "DM2", pd.Timestamp("2026-09-03"), pd.NaT, pd.NaT, P_F, "310101199401011238"),
        ("W7", "DM2", pd.Timestamp("2026-09-04"), pd.NaT, pd.NaT, P_S, "310101199601011240"),
        ("W8", "DM2", pd.Timestamp("2026-09-05"), pd.NaT, pd.NaT, P_G, "310101199701011241"),
    ], columns=COLS)
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


def test_v2_four_buckets_mutually_exclusive_and_exhaustive():
    """v2：四桶互斥且穷尽，且和等于 target_orders。"""
    _ensure_shared_operators()
    from operators.repurchase import split_repurchase

    df, start, end = _window_df()
    r = split_repurchase(df, start, end, series="DM2")
    assert "error" not in r, r

    b = r["buckets"]
    assert b == {
        "prior_fulfilled": 2,        # W1(P_A), W6(P_F 仅交付)
        "no_prior_history": 4,       # W2(悬置), W3(无历史), W4(PIT 未来兑现), W8(无历史)
        "shared_phone_excluded": 1,  # W7(P_S 共享号码)
        "unknown_identity": 1,       # W5(无手机号)
    }, b

    assert sum(b.values()) == r["report"]["target_orders"] == 8
    assert r["checks"]["buckets_sum_equals_target"] is True
    assert r["checks"]["valid_base_identity"] is True


def test_v2_report_fields_and_identities():
    """必披露 6 项 + 恒等式 target - excluded == valid_base。"""
    _ensure_shared_operators()
    from operators.repurchase import split_repurchase

    df, start, end = _window_df()
    r = split_repurchase(df, start, end, series="DM2")
    rep = r["report"]
    assert set(rep) == {
        "target_orders", "excluded_shared_phone_orders", "valid_base",
        "repeat_orders", "phone_missing_orders", "repeat_rate",
    }
    assert rep["target_orders"] == 8
    assert rep["excluded_shared_phone_orders"] == 1
    assert rep["valid_base"] == 7
    assert rep["repeat_orders"] == 2
    assert rep["phone_missing_orders"] == 1
    assert rep["valid_base"] == rep["target_orders"] - rep["excluded_shared_phone_orders"]
    assert rep["repeat_rate"] == round(2 / 7, 4)
    assert r["version"] == "v2_phone_shared_excluded"


def test_v2_prior_locker_removed():
    """旧宽松 mode=prior_locker 已移除，调用应返回错误。"""
    _ensure_shared_operators()
    from operators.repurchase import split_repurchase

    df, start, end = _window_df()
    r = split_repurchase(df, start, end, series="DM2", mode="prior_locker")
    assert r.get("error") == "invalid_mode"


def test_v2_shared_phone_pit_no_lookahead():
    """共享号码判定严格 PIT：窗口后才出现的第二个身份证不得导致剔除。"""
    _ensure_shared_operators()
    from operators.repurchase import split_repurchase

    df, start, end = _window_df()
    # 给 P_G 增加一条「窗口前锁单但窗口后才兑现」的历史：不应影响共享判定
    future = pd.DataFrame([
        ("F1", "DM0", pd.Timestamp("2026-08-01"), pd.Timestamp("2026-09-01"),
         pd.Timestamp("2026-09-01"), P_G, "310101199901019999"),
    ], columns=COLS)
    df2 = pd.concat([df, future], ignore_index=True)
    r = split_repurchase(df2, start, end, series="DM2")
    assert r["buckets"]["shared_phone_excluded"] == 1  # 仍只有 P_S
    assert r["buckets"]["no_prior_history"] == 4


def test_v2_fulfilled_by_delivery_or_invoice():
    """交付或开票任一发生且早于窗口，即算已完成购车。"""
    _ensure_shared_operators()
    from operators.repurchase import split_repurchase

    df, start, end = _window_df()
    r = split_repurchase(df, start, end, series="DM2")
    # W1 靠开票+交付；W6 的历史只有交付（无开票）→ 仍计复购
    assert r["buckets"]["prior_fulfilled"] == 2


def test_v2_pit_no_lookahead_into_window():
    """PIT：窗口前锁单、窗口后才兑现 → 该窗口下不算复购；更晚窗口再评估才算。"""
    _ensure_shared_operators()
    from operators.repurchase import split_repurchase

    df, start, _ = _window_df()
    r1 = split_repurchase(df, start, pd.Timestamp("2026-09-06"), series="DM2")
    assert r1["buckets"]["prior_fulfilled"] == 2

    late = pd.DataFrame([
        ("W9", "DM2", pd.Timestamp("2026-09-17"), pd.NaT, pd.NaT, P_D,
         "310101199301011237"),
    ], columns=COLS)
    df2 = pd.concat([df, late], ignore_index=True)
    r2 = split_repurchase(df2, pd.Timestamp("2026-09-16"), pd.Timestamp("2026-09-26"),
                          series="DM2")
    assert r2["buckets"]["prior_fulfilled"] == 1  # W9
    assert r2["summary"]["repeat"] == 1


def test_v2_invalid_phone_treated_as_unknown():
    """非 32 位十六进制的手机号值按无效处理 → unknown_identity。"""
    _ensure_shared_operators()
    from operators.repurchase import split_repurchase

    df, start, end = _window_df()
    df.loc[df["order_number"] == "W3", "lead_phone_md5"] = "not-a-hash"
    r = split_repurchase(df, start, end, series="DM2")
    assert r["buckets"]["unknown_identity"] == 2
    assert r["buckets"]["no_prior_history"] == 3


def test_v2_missing_identity_column_errors():
    """缺少手机号列时明确报错（JOIN 应在调用方完成）。"""
    _ensure_shared_operators()
    from operators.repurchase import split_repurchase

    df, start, end = _window_df()
    r = split_repurchase(df.drop(columns=["lead_phone_md5"]), start, end, series="DM2")
    assert r.get("error") == "missing_columns"


def test_run_operator_entrypoint():
    """run_repurchase_operator 通过 ISO 字符串调用，等价 split。"""
    _ensure_shared_operators()
    from operators.repurchase import run_repurchase_operator

    df, start, end = _window_df()
    r = run_repurchase_operator(df, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"),
                                series="DM2")
    assert r["summary"]["repeat"] == 2
    assert r["mode"] == "fulfilled_repurchase"
    assert r["report"]["valid_base"] == 7
