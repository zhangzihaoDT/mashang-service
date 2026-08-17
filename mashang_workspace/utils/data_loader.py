"""workspace 数据加载工具 — 共享 order_data 加载入口。

三个 ELOE 相关脚本（stalled_order_forecast / backlog_rate_trend_report /
launch_risk_snapshot）统一从这里加载 order_data，避免各自维护 load_data，
并把「报告/研究层 → 生产算子」的依赖方向拉直（均直接消费 shared 算子）。
"""

import pandas as pd

from utils.paths import DATASET_DIR

ORDER_DATA_PARQUET = DATASET_DIR / "order_data.parquet"


def load_order_data() -> pd.DataFrame:
    """加载 order_data.parquet，并解析核心时间字段为 datetime。

    返回的 DataFrame 可直接用于 shared/operators/effective_locked_orders.py
    的纯函数（build_outcome_frame / score_current_pool 等）。
    """
    df = pd.read_parquet(ORDER_DATA_PARQUET)
    for c in ["lock_time", "invoice_upload_time", "apply_refund_time", "actual_refund_time"]:
        df[c] = pd.to_datetime(df[c], errors="coerce")
    return df
