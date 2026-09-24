"""drive_type_logic 驱动形式分类回归测试。

背景：CM2（新一代智己LS6）产品分类只到版型（Max / Max+ / Pro Max / Ultra），
业务确认「驱动形式」可区分四驱 / 后驱。依据官方配置表：CM2/CM3 仅 Ultra 为
双电机四驱，其余（含 Max+/Pro Max 与全部增程）均为后驱；CM0/CM1 老款四驱为
「超强性能」版型。规则沉淀到 `shared/schema/business_definition.json:
drive_type_logic`，当前覆盖 LS6 家族。
"""

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

_WS_DIR = Path(__file__).resolve().parents[1]
_PRJ_DIR = _WS_DIR.parent
_BUSINESS_DEF = _PRJ_DIR / "shared" / "schema" / "business_definition.json"
for _p in (str(_PRJ_DIR), str(_WS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils.monitors.drive_type import DEFAULT_DRIVE_TYPE, apply_drive_type_logic


def _bdef() -> dict:
    return json.loads(_BUSINESS_DEF.read_text(encoding="utf-8"))


# (product_name, 期望驱动形式)
CASES = [
    # —— CM2 / CM3：仅 Ultra 为四驱 ——
    ("新一代智己LS6 Ultra", "四驱"),
    ("全新一代智己LS6 Ultra", "四驱"),
    ("新一代智己LS6 Max", "后驱"),
    ("新一代智己LS6 Max+", "后驱"),
    ("新一代智己LS6 Pro Max", "后驱"),
    ("新一代智己LS6 52 Max", "后驱"),
    ("新一代智己LS6 52 Max+", "后驱"),
    ("新一代智己LS6 66 Max+", "后驱"),
    ("LS6 76 Max 上汽一亿台限定版", "后驱"),
    ("LS6 103 Max 上汽一亿台限定版", "后驱"),
    ("LS6 M3 92 RWD", "后驱"),
    ("LS6 M3 76RWD", "后驱"),
    # —— CM0 / CM1 老款：四驱为「超强性能」，工程命名含 AWD ——
    ("LS6 Max 超强性能版", "四驱"),
    ("全新LS6 超强性能灵蜥智享版", "四驱"),
    ("LS6 M1 100AWD Max", "四驱"),
    ("LS6 Max 标准版", "后驱"),
    ("LS6 Max 长续航版", "后驱"),
    ("全新LS6 灵蜥智驾版", "后驱"),
    ("LS6 M1 83RWD+ Max", "后驱"),
    # —— 非 LS6 车系：当前不分类 ——
    ("智己LS9 66 Ultra", DEFAULT_DRIVE_TYPE),
    ("智己LS8 52 Max+", DEFAULT_DRIVE_TYPE),
    ("全新智己L6 Ultra", DEFAULT_DRIVE_TYPE),
    ("比亚迪海豹", DEFAULT_DRIVE_TYPE),
]


def test_drive_type_classification():
    df = pd.DataFrame({"product_name": [c for c, _ in CASES]})
    out = apply_drive_type_logic(df, _bdef())
    assert out["drive_type"].tolist() == [g for _, g in CASES], out.to_dict("records")


def test_drive_type_masks_mutually_exclusive():
    bdef = _bdef()
    logic = bdef["drive_type_logic"]
    assert set(logic) == {"四驱", "后驱"}

    from utils.monitors.series_group import eval_series_group_logic_expr

    df = pd.DataFrame({"product_name": [c for c, _ in CASES]})
    awd = eval_series_group_logic_expr(df["product_name"], logic["四驱"])
    rwd = eval_series_group_logic_expr(df["product_name"], logic["后驱"])
    assert not (awd & rwd).any(), "四驱/后驱 不应同时命中"


def test_drive_type_real_data_covers_all_ls6():
    dataset = _PRJ_DIR / "dataset" / "order_data.parquet"
    if not dataset.exists():
        pytest.skip("dataset/order_data.parquet 不存在（CI 跳过真实数据断言）")
    df = pd.read_parquet(dataset, columns=["product_name"])
    out = apply_drive_type_logic(df, _bdef())
    ls6 = df["product_name"].fillna("").astype(str).str.contains("LS6")
    assert (out.loc[ls6, "drive_type"] != DEFAULT_DRIVE_TYPE).all(), "LS6 应全部可判驱动形式"
    assert set(out.loc[ls6, "drive_type"].unique()) == {"四驱", "后驱"}
    non_ls6 = ~ls6
    assert (out.loc[non_ls6, "drive_type"] == DEFAULT_DRIVE_TYPE).all()
