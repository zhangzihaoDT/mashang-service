"""
series_group_logic 显式优先级 + DM2 归类回归测试

背景：l6_m2_presale_metrics_to_feishu.py 曾因 first-match + 顺序隐含优先级，
把 L6 M2 / Jimmy Choo 订单错分到 DM0/DM1（DM2 全 0）。根因是共享分组机制
依赖规则书写顺序，且两套执行器语义不一致（shared 为 last-match-wins，
workspace 为 first-match-wins）。

修复：shared/schema/business_definition.json 的 series_group_logic 改为
{priority, condition} 对象，priority 是纯优先级（precedence，3/2/1 档），
族内越具体/越新代际优先命中；执行器按 priority 降序 + 书写顺序平局，
取首个命中（first-match-wins）。DM2 规则已收紧（M2 分支需含 L6 锚点）。
本测试断言两套执行器（shared/operators 与 l6_m2 脚本）结果一致，
且 M2 / Jimmy Choo 一律归 DM2，旧 L6 / LS6 代际分类不回退。
"""

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

_WS_DIR = Path(__file__).resolve().parents[1]
_PRJ_DIR = _WS_DIR.parent
_BUSINESS_DEF = _PRJ_DIR / "shared" / "schema" / "business_definition.json"


def _load_module(name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(name, _PRJ_DIR / rel_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载模块: {rel_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module", autouse=True)
def _executors():
    return {
        "shared": _load_module("shared_sgl", "shared/operators/series_group_logic.py"),
        "l6m2": _load_module("l6m2", "mashang_workspace/research_scripts/l6_m2_presale_metrics_to_feishu.py"),
    }


def _bdef() -> dict:
    return json.loads(_BUSINESS_DEF.read_text(encoding="utf-8"))


# (product_name, 期望分组)
CASES = [
    # —— L6 M2 / Jimmy Choo → 必须归 DM2 ——
    ("L6 M2 Pro Max", "DM2"),
    ("L6 M2 Max", "DM2"),
    ("L6 M2 Ultra", "DM2"),
    ("智己L6 M2", "DM2"),
    ("全新一代 智己  L6 Prof. JimmyChoo 高定限量版（93kWh）", "DM2"),
    ("全新一代 智己  L6 Prof. JimmyChoo 高定限量版（76kWh）", "DM2"),
    ("全新一代智己L6 Prof.Jimmy Choo 高定限量版 超长续航版", "DM2"),
    ("Prof.Jimmy Choo 高定限量版 标准续航版", "DM2"),
    # —— 旧 L6 代际不回退 ——
    ("全新智己L6 Ultra", "DM1"),
    ("智己L6 Max", "DM0"),
    # —— LS6 代际 ——
    ("全新智己LS6 Max", "CM1"),
    ("智己LS6 Max", "CM0"),
    ("新一代智己LS6 Max", "CM2"),
    ("上汽一亿台限定版智己LS6", "CM2"),
    # —— 独立车系 ——
    ("智己LS9", "LS9"),
    ("智己LS8", "LS8"),
    ("智己LS7", "LS7"),
    ("智己L7", "L7"),
    # —— 兜底 ——
    ("智己LS6 M2", "CM0"),  # 收紧验证：M2 但非 L6 家族 → 不进 DM2
    ("比亚迪海豹", "其他"),
]


def test_dm2_precedence_higher_than_broad_rules():
    """priority 是纯 precedence：族内 DM2>DM1>DM0、CM2>CM1>CM0，跨车系不要求大小。"""
    sgl = _bdef()["series_group_logic"]

    def prio(g: str) -> int:
        rule = sgl[g]
        assert isinstance(rule, dict), f"{g} 应为 {{priority, condition}} 对象格式"
        return int(rule["priority"])

    assert prio("DM2") > prio("DM1") > prio("DM0")
    assert prio("CM2") > prio("CM1") > prio("CM0")
    assert prio("DM0") == prio("CM0") == prio("LS8") > 0
    assert prio("其他") == 0


def test_shared_operator_classification(_executors):
    df = pd.DataFrame({"product_name": [c for c, _ in CASES]})
    out = _executors["shared"].apply_series_group_logic(df, _bdef())
    assert out["series_group_logic"].tolist() == [g for _, g in CASES]


def test_workspace_l6m2_classification_consistent_with_shared(_executors):
    bdef = _bdef()
    l6m2 = _executors["l6m2"]
    df = pd.DataFrame({"product_name": [c for c, _ in CASES]})
    asts = {g: l6m2._parse_logic(l6m2._rule_condition(c)) for g, c in bdef["series_group_logic"].items()}
    out = l6m2._apply_series_group_logic(df, bdef, asts)
    assert out["series_group_logic"].tolist() == [g for _, g in CASES]

    shared_df = pd.DataFrame({"product_name": [c for c, _ in CASES]})
    shared_out = _executors["shared"].apply_series_group_logic(shared_df, bdef)
    assert out["series_group_logic"].equals(shared_out["series_group_logic"])


def test_m2_orders_never_fall_into_dm0_dm1(_executors):
    """真实数据断言：含 M2/Jimmy 的 product_name 在共享执行器下全部归 DM2。"""
    dataset = _PRJ_DIR / "dataset" / "order_data.parquet"
    if not dataset.exists():
        pytest.skip("dataset/order_data.parquet 不存在（CI 跳过真实数据断言）")
    df = pd.read_parquet(dataset, columns=["product_name"])
    out = _executors["shared"].apply_series_group_logic(df, _bdef())
    m2_mask = df["product_name"].fillna("").astype(str).str.contains("M2|Jimmy", case=False, regex=True)
    assert m2_mask.any(), "数据集中应存在 M2/Jimmy 订单"
    groups = out.loc[m2_mask, "series_group_logic"].unique().tolist()
    assert groups == ["DM2"], f"M2/Jimmy 订单被错分到 {groups}"
