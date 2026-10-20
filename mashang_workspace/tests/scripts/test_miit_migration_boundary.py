"""MIIT 迁出后的 Service 品牌分析不再依赖已删除的路径。"""
import sys
from pathlib import Path

_WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_WS))

from utils.watchlist_brand_common import WATCHLIST_PATH, load_watchlist
from research_scripts import watchlist_brand_monthly_report as monthly
from utility_scripts.build_workspace_skills_catalog import PROMPTBUILDER_CAPABILITIES


def test_brand_analytics_uses_service_owned_watchlist():
    assert WATCHLIST_PATH == _WS / 'configs' / 'brand_watchlist.yaml'
    groups = load_watchlist()
    assert len(groups) == 4
    assert sum(map(len, groups.values())) == 26
    assert 'AITO' in groups['华为五界三境']
    assert 'iCAR' in groups['硬派方盒子']
    assert monthly.load_watchlist is load_watchlist


def test_catalog_cannot_regenerate_retired_miit_entry():
    assert 'miit_new_car' not in PROMPTBUILDER_CAPABILITIES
