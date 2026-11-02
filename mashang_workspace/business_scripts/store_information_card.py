#!/usr/bin/env python3
"""门店信息手卡：code 关联、全国频数直方图与并列中点分位数。"""
from __future__ import annotations

import argparse
import io
import json
import math
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
WS = ROOT / 'mashang_workspace'
for path in (ROOT, WS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
from shared.loaders import store_info_loader as sl
from business_scripts import store_dealer_profile as profile
from utils.result_contract import build_success_contract, build_error_contract

SCRIPT = 'mashang_workspace/business_scripts/store_information_card.py'
LEADS = ROOT / 'dataset/store_daily_leads.csv'
ORDERS = ROOT / 'dataset/order_data.parquet'


def percentile_summary(values, target: int) -> dict:
    values = np.asarray(values)
    if len(values) == 0 or np.any(values < 0) or target < 0:
        raise ValueError('分位数需要非空、非负的门店样本')
    lower, equal, higher = (int((values < target).sum()), int((values == target).sum()),
                            int((values > target).sum()))
    return {'value': int(target), 'n': len(values), 'lower': lower, 'equal': equal,
            'higher': higher, 'percentile': round(100 * (lower + equal / 2) / len(values), 2),
            'tie_percentile_low': round(100 * lower / len(values), 2),
            'tie_percentile_high': round(100 * (lower + equal) / len(values), 2),
            'rank': higher + 1, 'median': float(np.median(values))}


def histogram_data(values, max_bins=20) -> dict:
    """等宽整数分箱，含零和完整长尾，不裁剪/合并溢出桶。"""
    values = np.asarray(values, dtype=int)
    if not len(values) or np.any(values < 0):
        raise ValueError('直方图需要非空非负样本')
    width = max(1, math.ceil((int(values.max()) + 1) / max_bins))
    edges = np.arange(-.5, int(values.max()) + width + .5, width)
    if len(edges) < 2:
        edges = np.array([-.5, .5])
    counts, edges = np.histogram(values, edges)
    assert int(counts.sum()) == len(values)
    return {'edges': edges.tolist(), 'counts': counts.tolist(), 'bin_width': width}


def build_population(master, leads, orders, as_of: str, window_days: int, resolver=sl.resolve_dealer_info):
    """国内同名职能编码并为一家；任一职能开业即纳入该店。"""
    end = pd.Timestamp(as_of).normalize() + pd.Timedelta(days=1)
    start = end - pd.Timedelta(days=window_days)
    eligible = master[(master['Store Create Status Desc'] == '开业')
                      & ~master['store_format'].eq('海外网点')
                      & ~master['Region Name'].eq('海外区')].copy()
    eligible = eligible[~eligible['Dealer Name Fc'].str.strip().isin(['', '无', '全部'])]
    population = (eligible.drop_duplicates('Dealer Name Fc')
                  [['Dealer Name Fc', 'Bloc Name']].rename(columns={'Dealer Name Fc': 'store', 'Bloc Name': 'bloc'})
                  .set_index('store'))
    if population.empty:
        raise ValueError('没有可用的国内开业门店主数据')
    code_to_name = master[master['Dealer Name Fc'].isin(population.index)].set_index('Dealer Code')['Dealer Name Fc'].to_dict()
    all_master_codes = set(master['Dealer Code'])
    audit = {'leads': {'unmatched': [], 'excluded': []}, 'locks': {'unmatched': [], 'excluded': []}}

    def classify(name, info, metric, amount):
        if info is None:
            audit[metric]['unmatched'].append({'store': str(name), 'value': int(amount)})
            return None
        store = code_to_name.get(info['dealer_code'])
        if store is None:
            audit[metric]['excluded'].append({'store': str(name), 'code': info['dealer_code'], 'value': int(amount)})
        return store

    leads = leads.copy()
    leads['日期'] = pd.to_datetime(leads['日期'], errors='coerce')
    leads['下发线索数'] = pd.to_numeric(leads['下发线索数'], errors='raise')
    if (leads['下发线索数'] < 0).any():
        raise ValueError('线索存在负值')
    lw = leads[(leads['日期'] >= start) & (leads['日期'] < end)]
    if lw.duplicated(['门店', '日期']).any():
        raise ValueError('线索库存在重复门店×日期')
    totals = {}
    grouping = ['门店'] + [c for c in ('门店代码', '经销商主体') if c in lw.columns]
    for key, group in lw.groupby(grouping, dropna=False):
        keys = dict(zip(grouping, key if isinstance(key, tuple) else (key,)))
        name = keys['门店']
        code = str(keys.get('门店代码', '') or '').strip()
        bloc = str(keys.get('经销商主体', '') or '').strip()
        info = resolver(name, dealer_code=code or None, bloc_name=bloc or None, as_of=as_of)
        amount = int(group['下发线索数'].sum())
        if info is None and code and code not in all_master_codes:
            audit['leads']['excluded'].append({'store': str(name), 'code': code, 'value': amount, 'reason': '主数据未登记编码'})
            continue
        store = classify(name, info, 'leads', amount)
        if store is not None:
            totals[store] = totals.get(store, 0) + amount
    population['leads'] = population.index.map(totals).fillna(0).astype(int)

    orders = orders.copy()
    lock_time = pd.to_datetime(orders['lock_time'], errors='coerce')
    ow = orders[(lock_time >= start) & (lock_time < end) & orders['order_type'].eq('用户车')].copy()
    lock_names = {}
    for name, group in ow.groupby('store_name'):
        info = resolver(name, as_of=as_of)
        lock_names[name] = classify(name, info, 'locks', group['order_number'].nunique())
    ow['_store'] = ow['store_name'].map(lock_names)
    lock_counts = ow.dropna(subset=['_store']).groupby('_store')['order_number'].nunique()
    population['locks'] = population.index.map(lock_counts).fillna(0).astype(int)
    audit['raw_user_locks'] = int(ow['order_number'].nunique())
    audit['included_user_locks'] = int(population['locks'].sum())
    return population, audit


def cjk_font() -> str:
    from matplotlib import font_manager
    candidates = ['/System/Library/Fonts/STHeiti Light.ttc',
                  '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc']
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    for font in font_manager.fontManager.ttflist:
        if any(key in font.name for key in ('Noto Sans CJK', 'Microsoft YaHei', 'PingFang', 'SimHei')):
            return font.fname
    raise RuntimeError('缺少中文字体，无法生成手卡')


def chart_image(hist, summary, unit, font_path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    from matplotlib.ticker import MaxNLocator
    from PIL import Image
    font = FontProperties(fname=font_path, size=10)
    fig, ax = plt.subplots(figsize=(5.2, 2.65), dpi=100)
    fig.patch.set_facecolor('#FFFFFF')
    edges = np.asarray(hist['edges'])
    ax.bar(edges[:-1], hist['counts'], width=np.diff(edges), align='edge',
           color='#6BB6E8', edgecolor='#FFFFFF', linewidth=.65)
    ax.axvline(summary['value'], color='#E96A27', linewidth=2, linestyle='--', zorder=4)
    ax.set_xlim(edges[0], edges[-1]); ax.set_ylim(bottom=0)
    ax.xaxis.set_major_locator(MaxNLocator(nbins=5, integer=True))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=3, integer=True))
    ax.set_xlabel('每店下发线索数（条）' if unit == '条' else '每店锁单数（单）', fontproperties=font, color='#526675')
    ax.set_ylabel('门店数', fontproperties=font, color='#526675')
    for tick in ax.get_xticklabels() + ax.get_yticklabels():
        tick.set_fontproperties(font)
        tick.set_color('#526675')
    ax.grid(axis='y', color='#E6EDF3', linewidth=.6); ax.set_axisbelow(True)
    for side in ('top', 'right'):
        ax.spines[side].set_visible(False)
    for side in ('bottom', 'left'):
        ax.spines[side].set_color('#B8C7D3')
    fig.subplots_adjust(left=.12, right=.98, bottom=.25, top=.96)
    stream = io.BytesIO(); fig.savefig(stream, format='png', dpi=100); plt.close(fig)
    stream.seek(0)
    return Image.open(stream).convert('RGB')


def render_card(path, info, master_row, profile_row, stats, histograms, start, end, roster_date):
    from PIL import Image, ImageDraw, ImageFont
    font_path = cjk_font()
    image = Image.new('RGB', (1200, 1860), '#F8FAFC')
    draw = ImageDraw.Draw(image)
    colors = {'ink': '#233746', 'muted': '#526675', 'orange': '#B34C16'}

    def text(x, y, value, size=27, color='ink'):
        font = ImageFont.truetype(font_path, size)
        value = str(value)
        if draw.textbbox((x, y), value, font=font)[2] > 1145:
            raise ValueError(f'手卡文字超宽: {value}')
        draw.text((x, y), value, font=font, fill=colors.get(color, color))

    def field(x, y, label, value):
        text(x, y, label, 23, 'muted'); text(x, y + 37, value, 29)

    draw.rectangle((0, 0, 1200, 12), fill='#6BB6E8')
    text(64, 46, '门店信息手卡', 25, 'muted')
    text(910, 47, datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y.%m.%d'), 24, 'muted')
    title = info['dealer_name_fc'].removesuffix('体验中心')
    title = re.sub('kkmall', 'KK MALL', title, flags=re.I)
    text(64, 105, title, 60); text(64, 190, info['dealer_name_fc'], 29, 'muted')
    text(64, 243, f"开业  /  {info['store_format']}  /  {info['dealer_code']}", 26, 'muted')
    draw.line((64, 299, 1136, 299), fill='#DCE5EC', width=2)
    field(64, 329, '经营主体（Bloc）', info['bloc_name'])
    field(650, 329, '所属大区', info['region_name'])
    field(64, 427, '城市', info['city_name'])
    created = str(master_row.get('store_create_time', '')).replace('/', '.')
    field(650, 427, '系统建店日', created or '无数据')
    text(64, 535, f"主体在营网络：{profile_row['该主体门店数(在营)']} 家 · {profile_row['城市分布']}", 26, 'muted')
    text(64, 599, f'{start} — {end}  ·  完整统计窗口', 26)
    n = stats['leads']['n']
    text(64, 644, f'全国已登记开业门店 {n} 家 · 无记录计 0 · 含交付/售后网点', 23, 'muted')
    for metric, title, unit, x in [('leads', '下发线索', '条', 64), ('locks', '用户车锁单', '单', 608)]:
        y = 706
        summary = stats[metric]
        draw.rounded_rectangle((x, y, x + 520, y + 530), radius=18, fill='white')
        text(x + 24, y + 20, title, 28)
        text(x + 24, y + 64, f"{summary['value']:,} {unit}", 52)
        text(x + 24, y + 130, f"全国分位 P{summary['percentile']:.1f}", 30, 'orange')
        text(x + 24, y + 177, f"中位数 {summary['median']:g} {unit} · 零值 {summary['zero_count']} 家", 22, 'muted')
        image.paste(chart_image(histograms[metric], summary, unit, font_path), (x, y + 211))
        text(x + 24, y + 477, f"低于 {summary['lower']} 家 · 相同 {summary['equal']} 家", 22, 'muted')
        text(x + 24, y + 507, f"高于本店 {summary['higher']} 家", 22, 'muted')
    text(64, 1270, f"主体内：线索 {profile_row['线索主体内排名']}  /  锁单 {profile_row['锁单主体内排名']}", 27)
    text(64, 1316, f"锁单车系：{profile_row['车系分布']}", 26, 'muted')
    draw.rounded_rectangle((64, 1383, 1136, 1492), radius=18, fill='white')
    text(88, 1401, f"主理配置：{profile_row['近期主理数量']} 人", 28)
    text(88, 1446, f"名册文件快照 {roster_date} · 当前人数需以最新名册为准", 23, 'orange')
    notes = [
        '口径：国内已登记门店按全名合并职能编码，有开业记录即纳入。',
        '线索按日求和；用户车锁单按 lock_time 窗口去重订单号。',
        '分位数 =（低于本店的门店数 + 同值门店数 × 0.5）÷ 全部门店数。',
        '同值门店数包含本店。P 值越高，表示该指标在样本中的相对位置越高。',
        '直方图纵轴为门店频数；横轴为每店指标值，保留零值与完整长尾。',
        '来源：门店主数据、store_daily_leads.csv、order_data.parquet、主理名册。',
        '主数据为当前快照；海外、空占位及未登记编码不纳入；无记录计 0。',
    ]
    draw.line((64, 1527, 1136, 1527), fill='#DCE5EC', width=2)
    for i, note in enumerate(notes):
        text(64, 1554 + i * 33, note, 22, 'muted')
    text(64, 1810, 'RACCOON RESEARCH', 20, 'muted')
    text(950, 1810, '内部业务资料', 21, 'muted')
    image.save(path, dpi=(180, 180))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stores', nargs='*', help='门店名称/简称')
    parser.add_argument('--store', action='append', default=[], help='门店，可重复')
    parser.add_argument('--as-of', help='截止日，默认上海时区昨天')
    parser.add_argument('--window-days', type=int, default=7)
    parser.add_argument('--output', default=str(WS / 'outputs/reports/store_information_cards'))
    parser.add_argument('--format', choices=['png', 'json'], default='png', help='json 仅分析；png 同时保存审计 JSON')
    args = parser.parse_args(argv)
    scope = {}
    try:
        names = args.stores + args.store
        if not names or args.window_days < 1:
            raise ValueError('请提供门店名称，window-days 必须为正数')
        yesterday = datetime.now(ZoneInfo('Asia/Shanghai')).date() - timedelta(days=1)
        as_of = pd.Timestamp(args.as_of or yesterday).date()
        if as_of > yesterday:
            raise ValueError('手卡只支持截至昨天的完整日窗口')
        as_of = str(as_of)
        start = str((pd.Timestamp(as_of) - pd.Timedelta(days=args.window_days - 1)).date())
        master = sl.load_store_info()
        if master is None:
            raise ValueError('缺少门店主数据')
        leads = pd.read_csv(LEADS, dtype=str, keep_default_na=False)
        orders = pd.read_parquet(ORDERS, columns=['order_number', 'store_name', 'series', 'lock_time', 'order_type'])
        for label, values in [('线索', pd.to_datetime(leads['日期'])), ('锁单', pd.to_datetime(orders['lock_time']))]:
            if values.max() < pd.Timestamp(as_of):
                raise ValueError(f'{label}数据未覆盖截止日 {as_of}')
            if values.min() > pd.Timestamp(start):
                raise ValueError(f'{label}数据未覆盖起始日 {start}')
        population, audit = build_population(master, leads, orders, as_of, args.window_days)
        if any(audit[k]['unmatched'] for k in ('leads', 'locks')):
            raise ValueError('全国窗口存在未匹配门店，暂不输出完整全国分位数：' + json.dumps(audit, ensure_ascii=False))
        # 复用原画像的档案、主理及主体内经营说明。
        _, network = profile.build_dealer_network(['开业'])
        zhuli = profile.load_zhuli()
        om = profile.load_order_metrics(as_of, args.window_days)
        lm = profile.load_leads_metrics(as_of, args.window_days)
        cards, artifacts = [], {}
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        roster_date = datetime.fromtimestamp(profile.ZHULI_ROSTER_CSV.stat().st_mtime, ZoneInfo('Asia/Shanghai')).strftime('%Y.%m.%d') if profile.ZHULI_ROSTER_CSV.exists() else '缺失'
        for name in names:
            info = sl.resolve_dealer_info(name, as_of=as_of)
            if not info or info['dealer_name_fc'] not in population.index:
                raise ValueError(f'{name} 未匹配全国国内开业门店')
            row = population.loc[info['dealer_name_fc']]
            stats, histograms = {}, {}
            for key in ('leads', 'locks'):
                stats[key] = percentile_summary(population[key], int(row[key]))
                stats[key]['zero_count'] = int(population[key].eq(0).sum())
                histograms[key] = histogram_data(population[key])
            details = profile.build_rows([name], network, zhuli, om, lm)[0]
            # 档案与总体指标使用同一 code 解析，避免简称回退到旧档案。
            details['近7日下发线索'] = stats['leads']['value']
            details['近7日锁单'] = stats['locks']['value']
            bloc_population = population[population['bloc'] == info['bloc_name']]
            for metric, label in [('leads', '线索主体内排名'), ('locks', '锁单主体内排名')]:
                rank = 1 + int((bloc_population[metric] > stats[metric]['value']).sum())
                details[label] = f'第{rank}/{len(bloc_population)}'
            details['该主体门店数(在营)'] = len(bloc_population)
            source_names = []
            for order_name in orders['store_name'].dropna().unique():
                resolved = sl.resolve_dealer_info(order_name, as_of=as_of)
                if resolved and resolved['dealer_name_fc'] == info['dealer_name_fc']:
                    source_names.append(order_name)
            times = pd.to_datetime(orders['lock_time'], errors='coerce')
            target_orders = orders[orders['store_name'].isin(source_names)
                                   & orders['order_type'].eq('用户车')
                                   & (times >= pd.Timestamp(start))
                                   & (times < pd.Timestamp(as_of) + pd.Timedelta(days=1))]
            series_counts = target_orders.groupby('series')['order_number'].nunique().sort_values(ascending=False)
            details['车系分布'] = ' / '.join(f'{series} {count}' for series, count in series_counts.items()) or '无锁单'
            card = {'store': name, 'info': info, 'statistics': stats, 'histograms': histograms}
            cards.append(card)
            if args.format == 'png':
                filename = re.sub(r'[^\w\u4e00-\u9fff.-]', '_', info['dealer_name_fc']) + '_门店信息手卡.png'
                path = out / filename
                mr = master[master['Dealer Code'] == info['dealer_code']].iloc[0]
                render_card(path, info, mr, details, stats, histograms, start, as_of, roster_date)
                artifacts[name] = str(path.resolve())
        scope = {'data_source': [str(sl.get_store_info_csv_path()), str(LEADS), str(ORDERS)],
                 'time_window': {'start': start, 'end': as_of, 'timezone': 'Asia/Shanghai'},
                 'filters': {'stores': names, 'status': '开业', 'exclude_overseas': True, 'order_type': '用户车'},
                 'metric_definition': '国内开业全门店，按全名合并职能编码，无记录计0；线索按日求和，锁单订单号去重；分位数=(低于+0.5同值)/N*100'}
        population.to_csv(out / 'national_store_population.csv', encoding='utf-8-sig')
        artifacts['population_csv'] = str((out / 'national_store_population.csv').resolve())
        contract = build_success_contract(SCRIPT, ' '.join(sys.argv), scope,
            {'summary': f'{len(cards)} 家门店手卡，全国样本 {len(population)} 家',
             'metrics': {'population_count': len(population)}, 'cards': cards, 'audit': audit}, artifacts,
            {'stores': names, 'as_of': as_of, 'window_days': args.window_days},
            warnings=['无记录按0计入；国内样本含交付/售后网点，主数据状态为当前快照。'])
        (out / 'store_information_card.json').write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(contract, ensure_ascii=False, indent=2) if args.format == 'json'
              else f"[Summary]\n{contract['result']['summary']}\n[Output]\n" + '\n'.join(artifacts.values()))
        return 0
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        print(json.dumps(build_error_contract(SCRIPT, ' '.join(sys.argv), str(exc), scope), ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
