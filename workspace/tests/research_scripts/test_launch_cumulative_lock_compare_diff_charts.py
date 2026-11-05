"""launch_cumulative_lock_compare — 占比差（pp）行内发散条（模块 5 年龄分层 / 分大区）smoke test。

可视化直接落在表格「占比差」列内（diffcell，同模块 7 barcell 风格），不再单开 Plotly 图。
"""

import sys
from pathlib import Path

_WS_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_WS_DIR))

from research_scripts.launch_cumulative_lock_compare import (  # noqa: E402
    _age_repurchase_table,
    _diff_barcell,
    _region_table,
)


def test_diff_barcell_color_and_scale():
    # 宽度 ∝ |差| / 最大 |差|；颜色由正负决定；文案带正负号
    assert "<div class='bar positive' style='width:50.0%;'></div>" in _diff_barcell(5.0, 10.0)
    assert "<div class='bar negative' style='width:50.0%;'></div>" in _diff_barcell(-5.0, 10.0)
    assert ">+5.0 pp<" in _diff_barcell(5.0, 10.0)
    assert ">-5.0 pp<" in _diff_barcell(-5.0, 10.0)
    # 满轴：最大 |差| 占满整条
    assert "width:100.0%;" in _diff_barcell(10.0, 10.0)
    # 零值：无 bar，文案 0.0
    zero = _diff_barcell(0.0, 10.0)
    assert "<div class='bar positive'" not in zero
    assert "<div class='bar negative'" not in zero
    assert ">0.0 pp<" in zero
    # None → 占位
    assert "—" in _diff_barcell(None, 10.0)


def _region_c():
    return {
        "n_days": 10,
        "region": {
            "gen_a": "DM1",
            "gen_b": "DM2",
            "n_days": 10,
            "total_a": 100,
            "total_b": 120,
            "regions": [
                {"region": "东区", "a": 40, "a_share": 0.40, "b": 60, "b_share": 0.50, "diff_pp": 10.0},
                {"region": "西区", "a": 60, "a_share": 0.60, "b": 60, "b_share": 0.50, "diff_pp": -10.0},
            ],
            "total_stores_a": 50,
            "total_stores_b": 55,
            "max_stores_a": 52,
            "max_stores_b": 57,
        },
    }


def test_region_table_inlines_diff_bars_and_keeps_table():
    html = _region_table(_region_c())
    # 行内数据条，而非独立图表
    assert "barcell" in html
    assert "bar positive" in html and "bar negative" in html
    assert "chart-region-diff" not in html
    assert "Plotly.newPlot" not in html
    # 保留原明细表（含合计行）
    assert "<strong>合计</strong>" in html
    assert "+10.0 pp" in html and "-10.0 pp" in html


def _age_c():
    rep = {"repeat": 10, "first": 80, "suspended": 5, "unknown": 5, "known_pct": 95.0}
    return {
        "n_days": 10,
        "age_repurchase": {
            "gens": ["DM1", "DM2"],
            "n_days": 10,
            "rows": [
                {"band": "18-25岁", "a": 5, "a_share_known": 0.05, "b": 8, "b_share_known": 0.08, "diff_pp": 3.0},
                {"band": "25-30岁", "a": 20, "a_share_known": 0.20, "b": 15, "b_share_known": 0.15, "diff_pp": -5.0},
            ],
            "repurchase": {"a": dict(rep), "b": dict(rep)},
        },
    }


def test_age_table_inlines_diff_bars_and_keeps_repurchase_table():
    html = _age_repurchase_table(_age_c())
    assert "barcell" in html
    assert "bar positive" in html and "bar negative" in html
    assert "chart-age-diff" not in html
    assert "Plotly.newPlot" not in html
    # 保留复购拆分表
    assert "老车主复购（历史已兑现购车）" in html
    assert "+3.0 pp" in html and "-5.0 pp" in html
