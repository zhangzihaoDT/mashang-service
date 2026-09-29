"""launch_cumulative_lock_compare — 模块 4 锁单用户画像 指标列口径 smoke test。

口径：女性占比仅取 owner_gender；年龄仅取 owner_age 且只保留均值（无中位数）。
"""

import sys
from pathlib import Path

_WS_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_WS_DIR))

from research_scripts.launch_cumulative_lock_compare import (  # noqa: E402
    _user_profile_table,
)


def _profile(n=100, female=40, mean_age=36.5, median_age=36.0):
    return {
        "n": n,
        "gender": {"男": 70, "女": 30},
        "owner_gender": {"男": 100 - female, "女": female},
        "age_owner": {"median": median_age, "mean": mean_age, "missing_pct": 6.0},
        "age_buyer": {"median": 33.0, "mean": 33.5, "missing_pct": 12.0},
        "cohorts": [{"cohort": "95后", "count": 20}, {"cohort": "90后", "count": 30}],
        "cohorts_known": 80,
        "tier": {"新一线": 36, "一线": 23, "三线及以下": 21},
        "province": [{"province": "上海", "count": 30}],
    }


def _c():
    return {
        "n_days": 5,
        "user_profile": {
            "gens": ["CM1", "CM2", "CM3"],
            "n_days": 5,
            "profiles": {
                "CM1": _profile(n=100, female=40, mean_age=36.5),
                "CM2": _profile(n=100, female=45, mean_age=38.1),
                "CM3": _profile(n=100, female=55, mean_age=35.9),
            },
            "insights": [],
        },
    }


def test_user_profile_table_uses_owner_gender_female_share():
    html = _user_profile_table(_c())
    assert "女性占比（owner_gender）" in html
    # 只用 owner_gender：CM1 女 40% / CM2 45% / CM3 55%
    assert ">40%<" in html and ">45%<" in html and ">55%<" in html
    # 旧口径列已移除
    assert "男性占比" not in html
    assert "order_gender" not in html


def test_user_profile_table_age_only_owner_age_mean():
    html = _user_profile_table(_c())
    assert "车主年龄均值（owner_age）" in html
    assert ">36.5<" in html and ">38.1<" in html and ">35.9<" in html
    # 中位数与购车人年龄口径已移除
    assert "车主年龄中位" not in html
    assert "购车人年龄中位" not in html
    assert "buyer_age" not in html
