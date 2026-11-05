"""分位数并列、直方图长尾和全国门店分母的回归验证。"""
import numpy as np
import pandas as pd
import pytest
from workspace.business_scripts.store_information_card import (
    percentile_summary, histogram_data, build_population,
)


def test_percentile_ties_are_midrank_not_competition_rank():
    result = percentile_summary([0, 2, 2, 10], 2)
    assert result['percentile'] == 50
    assert (result['lower'], result['equal'], result['higher']) == (1, 2, 1)
    assert result['tie_percentile_low'] == 25
    assert result['tie_percentile_high'] == 75
    assert percentile_summary([0, 0, 0], 0)['percentile'] == 50


@pytest.mark.parametrize('values', [[0], [0, 0, 1, 2, 30], [0, 324, 242, 9001]])
def test_histogram_keeps_zero_and_entire_tail(values):
    hist = histogram_data(values)
    assert sum(hist['counts']) == len(values)
    assert hist['edges'][0] < min(values)
    assert hist['edges'][-1] > max(values)
    assert len(hist['counts']) <= 20
    assert np.allclose(np.diff(hist['edges']), hist['bin_width'])


def test_population_uses_fixed_activity_window_and_keeps_zero_metrics():
    from operators.active_store import get_active_store_names, _calc_active_store_count
    master = pd.DataFrame([
        ['A1', '甲店', '甲', '在建'], ['B1', '乙店', '乙', '暂停'],
        ['C1', '丙店', '丙', '开业'], ['O1', '海外店', '海外', '开业'],
    ], columns=['Dealer Code', 'Dealer Name Fc', 'Bloc Name', 'Store Create Status Desc'])
    leads = pd.DataFrame([
        ['甲简称', '2026-11-01', 12, 'A1', '甲'],
        ['未知店', '2026-11-01', 7, 'X1', '未知'],
        ['甲简称', '2026-10-25', 99, 'A1', '甲'],
    ], columns=['门店', '日期', '下发线索数', '门店代码', '经销商主体'])
    orders = pd.DataFrame([
        ['1', '甲简称', '2026-11-01', '用户车', '2026-10-01', '2020-01-01'],
        ['1', '甲简称', '2026-11-01', '用户车', '2026-10-01', '2020-01-01'],
        ['2', '甲简称', None, '员工', '2026-11-01', '2020-01-01'],
        ['3', '海外简称', '2026-11-01', '用户车', '2026-10-03', '2020-01-01'],
        ['4', '甲简称', '2026-11-02', '用户车', '2026-11-02', '2020-01-01'],
        ['5', '乙简称', None, '用户车', '2026-10-03', '2020-01-01'],
        ['6', '丙简称', None, '用户车', '2026-10-02', '2020-01-01'],
        ['7', '未开业', None, '用户车', '2026-11-01', '2026-11-02'],
        ['8', '无建店日', None, '用户车', '2026-11-01', None],
    ], columns=['order_number', 'store_name', 'lock_time', 'order_type', 'order_create_date', 'store_create_date'])

    def resolver(name, dealer_code=None, **kwargs):
        code = dealer_code or {'甲简称': 'A1', '乙简称': 'B1', '丙简称': 'C1', '海外简称': 'O1'}.get(name)
        hit = master[master['Dealer Code'] == code]
        return None if hit.empty else {'dealer_code': code, 'dealer_name_fc': hit.iloc[0]['Dealer Name Fc'],
                                      'bloc_name': hit.iloc[0]['Bloc Name']}

    pop, audit = build_population(master, leads, orders, '2026-11-01', 7, resolver)
    # 保留算子原名；主数据状态、海外属性不额外改变名单。
    assert list(pop.index) == ['甲简称', '海外简称', '乙简称']
    assert len(pop) == _calc_active_store_count(orders, pd.Timestamp('2026-11-01'))
    assert list(get_active_store_names(orders, pd.Timestamp('2026-11-01'))) == list(pop.index)
    assert list(pop['leads']) == [12, 0, 0]
    assert list(pop['locks']) == [1, 1, 0]
    assert audit['raw_user_locks'] == audit['included_user_locks'] == 2
    assert audit['active_store']['window_start'] == '2026-10-03'
    duplicate_leads = pd.concat([leads, leads.iloc[[0]]])
    with pytest.raises(ValueError, match='重复'):
        build_population(master, duplicate_leads, orders, '2026-11-01', 7, resolver)


def test_active_store_list_preserves_aliases_and_uses_creation_time_fallback():
    from operators.active_store import get_active_store_names, _calc_active_store_count
    data = pd.DataFrame({
        'store_name': ['同店旧档期', '同店新档期', '空时间'],
        'order_create_date': [None, '2026-11-01', None],
        'order_create_time': ['2026-10-03 23:59:59', None, None],
        'store_create_date': ['2020-01-01'] * 3,
    })
    names = get_active_store_names(data, pd.Timestamp('2026-11-01'))
    assert list(names) == ['同店旧档期', '同店新档期']
    assert _calc_active_store_count(data, pd.Timestamp('2026-11-01')) == 2
    assert get_active_store_names(data.iloc[:0], pd.Timestamp('2026-11-01')).empty
