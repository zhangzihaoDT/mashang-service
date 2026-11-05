"""门店级线索身份字段的导出、合并契约。"""
import pandas as pd
import pytest
from dataset.updater import store_daily_leads_to_csv as updater


def source(tmp_path, **overrides):
    row = {'lc_dealer_name': '某店-换铺', 'lc_dealer_code': 'imh373',
           'lc_bloc_name': '深圳车易', '日(lc_assign_time_min)': '2026年11月1日', '下发线索数': '36'}
    row.update(overrides)
    path = tmp_path / 'export.csv'
    pd.DataFrame([row]).to_csv(path, index=False, encoding='utf-8-sig')
    return path


def test_export_preserves_code_and_bloc_and_migrates_history(tmp_path):
    fresh = updater.normalize(source(tmp_path))
    assert fresh.iloc[0]['门店代码'] == 'IMH373'
    assert fresh.iloc[0]['经销商主体'] == '深圳车易'
    old = pd.DataFrame({'门店': ['某店-换铺', '某店-换铺'],
                        '日期': ['2026-10-01', '2026-11-01'], '下发线索数': [10, 20]})
    merged = updater.merge_history(old, fresh)
    assert len(merged) == 2
    assert merged.iloc[0]['门店代码'] == ''
    assert merged.iloc[1]['下发线索数'] == 36
    assert merged.iloc[1]['门店代码'] == 'IMH373'
    # 下一轮刷新仍保留窗口外已有身份。
    next_day = fresh.copy()
    next_day['日期'] = pd.Timestamp('2026-11-02')
    assert updater.merge_history(merged, next_day).iloc[1]['门店代码'] == 'IMH373'


@pytest.mark.parametrize('column', ['lc_dealer_code', 'lc_bloc_name'])
def test_missing_or_empty_identity_rejected(tmp_path, column):
    path = source(tmp_path, **{column: ''})
    with pytest.raises(RuntimeError, match='为空'):
        updater.normalize(path)
    df = pd.read_csv(path).drop(columns=[column])
    df.to_csv(path, index=False)
    with pytest.raises(RuntimeError, match='缺少必需列'):
        updater.normalize(path)


def test_conflicting_same_day_rows_rejected(tmp_path):
    path = source(tmp_path)
    df = pd.read_csv(path)
    other = df.copy()
    other['lc_dealer_code'] = 'IMH999'
    pd.concat([df, other]).to_csv(path, index=False)
    with pytest.raises(RuntimeError, match='冲突'):
        updater.normalize(path)
