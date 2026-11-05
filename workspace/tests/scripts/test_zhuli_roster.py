"""主理全表导入：先筛在职，再去重账号，保留同名不同人。"""
import pandas as pd
import pytest
from dataset.updater import store_daily_zhuli_to_csv as updater
from workspace.business_scripts.store_dealer_profile import _zhuli_count


def test_filter_before_dedupe_and_preserve_namesakes(tmp_path):
    df = pd.DataFrame([
        ['同名', 'a', '旧店', 'A', '离职', ''],
        ['同名', 'a', '新店', 'B', '在职', ''],
        ['同名', 'a', '新店', 'B', '在职', ''],
        ['同名', 'b', '新店', 'B', '在职', ''],
        ['待入职', 'c', '新店', 'B', '待入职', ''],
    ], columns=['主理', '域账号', '门店', '门店编码', '在职状态', 'Unnamed: 20'])
    path = tmp_path / 'full.csv'
    df.to_csv(path, encoding='utf-16', sep='\t', index=False)
    active = updater.normalize_roster(path)
    assert active['域账号'].tolist() == ['a', 'b']
    assert active['门店'].tolist() == ['新店', '新店']
    assert 'Unnamed: 20' not in active.columns
    assert _zhuli_count(active) == 2
    assert len(pd.read_csv(path, encoding='utf-16', sep='\t')) == 5


def test_local_import_is_atomic_and_dry_run_preserves_old_file(tmp_path, monkeypatch):
    df = pd.DataFrame({'主理': ['同名'] * 500, '域账号': [str(i) for i in range(500)],
                       '门店': ['某店'] * 500, '门店编码': ['IMH001'] * 500,
                       '在职状态': ['在职'] * 500, 'Unnamed: 20': [''] * 500})
    source = tmp_path / 'full.csv'; df.to_csv(source, index=False, encoding='utf-8-sig')
    target = tmp_path / 'active.csv'; target.write_text('original')
    monkeypatch.setattr(updater, 'OUTPUT_ROSTER', target)
    assert updater.main(['--roster-input', str(source), '--dry-run']) == 0
    assert target.read_text() == 'original'
    assert updater.main(['--roster-input', str(source)]) == 0
    active = pd.read_csv(target, encoding='utf-8-sig', dtype=str)
    assert len(active) == 500
    assert 'Unnamed: 20' not in active.columns
    # 空账号和错视图都不能覆盖已存在的活动名册。
    previous = target.read_bytes()
    df.loc[0, '域账号'] = ''
    df.to_csv(source, index=False)
    assert updater.main(['--roster-input', str(source)]) == 1
    assert target.read_bytes() == previous
    df.drop(columns=['域账号']).to_csv(source, index=False)
    with pytest.raises(RuntimeError, match='缺少必需列'):
        updater.normalize_roster(source)
