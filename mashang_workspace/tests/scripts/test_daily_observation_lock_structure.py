"""日报锁单的产品分类闭合及零售口径回归。"""
from datetime import date

import pandas as pd

from mashang_workspace.utility_scripts import skills_order_observation_daily as daily


def test_versions_preserve_seats_unknowns_and_deduplicate():
    frame = pd.DataFrame([
        ('a', '智己LS8 52 Max+ 科技旗舰大五座'),
        ('a', '智己LS8 52 Max+ 科技旗舰大五座'),
        ('b', 'LS8 52Max+ 奢享大六座'),
        ('c', 'LS8 93 RWD 5座'),
        ('d', 'LS8 93 RWD 6座'),
        ('e', None),
    ], columns=['order_number', 'product_name'])
    result = daily._lock_product_versions(frame, 'LS8')
    assert result == {
        '52 Max+': {'五座': 1, '六座': 1},
        '93 RWD': {'五座': 1, '六座': 1},
        '未分类': {'未标座位': 1},
    }
    assert sum(sum(seats.values()) for seats in result.values()) == 5
    ls9 = frame.iloc[:3].copy()
    ls9['product_name'] = ['智己LS9 52 Ultra 线控版', '智己LS9 52 Ultra 线控版', '智己LS9 Hyper']
    assert daily._lock_product_versions(ls9, 'LS9') == {
        '52 Ultra 线控版': {'未标座位': 1}, 'Hyper': {'未标座位': 1},
    }


def test_retail_count_uses_same_date_and_test_exclusion(monkeypatch):
    monkeypatch.setattr(daily, 'flag_test_orders', lambda df, _: df.order_number.eq('test'))
    frame = pd.DataFrame([
        ('retail', '用户车', '2026-10-19'),
        ('retail', '用户车', '2026-10-19'),
        ('demo', '试驾车', '2026-10-19'),
        ('test', '用户车', '2026-10-19'),
        ('outside', '用户车', '2026-10-20'),
    ], columns=['order_number', 'order_type', 'lock_time'])
    frame['series'] = 'LS8'
    frame['series_group_logic'] = 'LS8'
    frame['product_name'] = 'LS8 93 RWD 5座'
    stats = daily.analyze_daily_lock_orders(frame, date(2026, 10, 19), date(2026, 10, 19))
    assert (stats['total'], stats['total_user_car']) == (2, 1)
    assert stats['models']['LS8']['product_versions'] == {'93 RWD': {'五座': 2}}


def test_shared_definition_controls_new_versions_and_unknowns():
    from utils.business import classify_product_names
    frame = pd.DataFrame({'product_name': ['智己 LS8 新版 5座', 'LS8 未定义版本 6座', None]})
    definitions = {
        'product_version_logic': {'LS8': {
            '新增版本': {'priority': 2, 'condition': "product_name LIKE '%新版%'"},
            '通用版本': {'priority': 1, 'condition': "product_name LIKE '%LS8%' AND product_name LIKE '%新版%'"},
        }},
        'seat_count_logic': {'五座': "product_name LIKE '%5座%'", '六座': "product_name LIKE '%6座%'"},
    }
    result = classify_product_names(frame, 'LS8', definitions)
    assert result['product_version'].tolist() == ['新增版本', '未分类', '未分类']
    assert result['seat_count'].tolist() == ['五座', '六座', '未标座位']


def test_ls9_formats_versions_on_one_line_without_seats():
    text = daily._format_lock_model_detail({
        'show_seats': False,
        'product_versions': {'52 Ultra': {'未标座位': 4}, 'Hyper': {'未标座位': 1}},
    })
    assert text == '｜52 Ultra：4，Hyper：1'
