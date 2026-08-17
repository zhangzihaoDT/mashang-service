"""
Historical Backlog Point-in-Time Leakage 回归测试

验证 compute_history 的历史悬置池按 as-of 状态重建：
- 观察点之后才开票/退订的订单，在历史观察点当时仍计入悬置池；
- PIT ELOE 对已知最终结局用确定值（已开票→1，已退订→0），仅仍悬置用模型概率；
- 观察点之前已开票/退订的订单被正确排除。
"""

import sys
from pathlib import Path

import pytest

_WS_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_WS_DIR))


def _purge_operators():
    """避免跨文件测试已把 mashang_runtime 的 operators 载入 sys.modules。"""
    for k in [k for k in list(sys.modules) if k == "operators" or k.startswith("operators.")]:
        del sys.modules[k]


def test_compute_history_pit_pool_and_eloe():
    import pandas as pd
    _purge_operators()
    from mashang_workspace.research_scripts.backlog_rate_trend_report import compute_history

    obs = pd.Timestamp("2024-08-01")

    # 训练订单：全部最终开票（+200 天），确保历史曲线 P(最终开票 | age) = 1
    train = pd.DataFrame({
        "order_number": [f"T{i}" for i in range(600)],
        "series": ["LS6"] * 600,
        "lock_time": [pd.Timestamp("2023-09-01") + pd.Timedelta(days=i % 60) for i in range(600)],
        "invoice_upload_time": [pd.Timestamp("2023-09-01") + pd.Timedelta(days=i % 60)
                                + pd.Timedelta(days=200) for i in range(600)],
        "apply_refund_time": [pd.NaT] * 600,
        "actual_refund_time": [pd.NaT] * 600,
    })

    lock_d = pd.Timestamp("2024-06-01")  # 在训练窗口（< obs-120d）之外，仅构成观察池

    def mk(prefix, n, invoiced=None, refunded=None):
        return pd.DataFrame({
            "order_number": [f"{prefix}{i}" for i in range(n)],
            "series": ["LS6"] * n,
            "lock_time": [lock_d] * n,
            "invoice_upload_time": [pd.Timestamp(invoiced) if invoiced else pd.NaT] * n,
            "apply_refund_time": [pd.Timestamp(refunded) if refunded else pd.NaT] * n,
            "actual_refund_time": [pd.NaT] * n,
        })

    later_inv = mk("INV_", 50, invoiced="2024-09-01")  # obs 后才开票 → 当时仍悬置，PIT 贡献 1.0
    later_ref = mk("REF_", 50, refunded="2024-09-01")  # obs 后退订 → 当时仍悬置，PIT 贡献 0.0
    open_now = mk("OPN_", 50)                            # 至今仍悬置 → 模型概率（历史 P=1）
    before_inv = mk("PRE_", 30, invoiced="2024-07-01")   # obs 前已开票 → 正确排除

    df = pd.concat([train, later_inv, later_ref, open_now, before_inv], ignore_index=True)

    rdf = compute_history(as_of=obs, frequency="monthly", df=df)
    row = rdf[rdf["as_of"] == "2024-08-01"].iloc[0]

    # obs 后才开票/退订的订单必须计入当时池子（buggy 代码会错误排除）
    assert row["n_orders"] == 150
    # ELOE = 50×1.0 + 50×0.0 + 50×模型P(=1.0) = 100.0
    assert row["eloe"] == pytest.approx(100.0)
    assert row["rate"] == pytest.approx(round(100.0 / 150, 4))
