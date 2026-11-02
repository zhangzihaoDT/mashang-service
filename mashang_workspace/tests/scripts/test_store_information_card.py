"""分位数并列、直方图长尾和全国门店分母的回归验证。"""
import numpy as np
import pandas as pd
import pytest
from mashang_workspace.business_scripts.store_information_card import (
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


def test_population_merges_function_codes_preserves_zeros_and_excludes_overseas():
    master = pd.DataFrame([
        ['A1', '甲店', '甲', '在建', '授权经销商门店', '华南'],
        ['A2', '甲店', '甲', '开业', '交付/售后中心', '华南'],
        ['B1', '乙店', '乙', '开业', '体验店', '华东'],
        ['C1', '丙店', '丙', '暂停', '体验店', '华东'],
        ['O1', '海外店', '海外', '开业', '海外网点', '海外区'],
    ], columns=['Dealer Code', 'Dealer Name Fc', 'Bloc Name', 'Store Create Status Desc', 'store_format', 'Region Name'])
    leads = pd.DataFrame([
        ['甲简称', '2026-11-01', 12, 'A1', '甲'],
        ['未知店', '2026-11-01', 7, 'X1', '未知'],
        ['甲简称', '2026-10-25', 99, 'A1', '甲'],
    ], columns=['门店', '日期', '下发线索数', '门店代码', '经销商主体'])
    orders = pd.DataFrame([
        ['1', '甲简称', '2026-11-01', '用户车'],
        ['1', '甲简称', '2026-11-01', '用户车'],
        ['2', '甲简称', '2026-11-01', '员工'],
        ['3', '海外简称', '2026-11-01', '用户车'],
        ['4', '甲简称', '2026-11-02', '用户车'],
    ], columns=['order_number', 'store_name', 'lock_time', 'order_type'])

    def resolver(name, dealer_code=None, **kwargs):
        code = dealer_code or {'甲简称': 'A1', '海外简称': 'O1'}.get(name)
        hit = master[master['Dealer Code'] == code]
        return None if hit.empty else {'dealer_code': code, 'dealer_name_fc': hit.iloc[0]['Dealer Name Fc']}

    pop, audit = build_population(master, leads, orders, '2026-11-01', 7, resolver)
    assert list(pop.index) == ['甲店', '乙店']
    assert list(pop['leads']) == [12, 0]
    assert list(pop['locks']) == [1, 0]
    assert audit['raw_user_locks'] == 2
    assert audit['included_user_locks'] == 1
    assert audit['leads']['excluded'][0]['reason'] == '主数据未登记编码'
    assert len(audit['locks']['excluded']) == 1
    duplicate_leads = pd.concat([leads, leads.iloc[[0]]])
    with pytest.raises(ValueError, match='重复'):
        build_population(master, duplicate_leads, orders, '2026-11-01', 7, resolver)
