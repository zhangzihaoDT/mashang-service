#!/usr/bin/env python3
"""
MIIT 品牌产品线公告汇总报告

用法:
    python research_scripts/miit_new_car/brand_product_line_report.py --brand 智己
    python research_scripts/miit_new_car/brand_product_line_report.py --brand 小鹏
    python research_scripts/miit_new_car/brand_product_line_report.py --brand 理想
    python research_scripts/miit_new_car/brand_product_line_report.py --brand 理想 --output outputs/reports/理想_product_line.md

使用限制:
    这是一个临时品牌快速查询工具，非产品化脚本。
    解析层脆弱：依赖 DOC 文本抽取格式，MIIT 的 DOC 模板一换解析就要重写。
    发现价值集中在人不在脚本：脚本只做复制粘贴式的汇总，不产生新洞察。
    已有更好的基础设施：MIIT 流水线有 product_list 结构化解析和 watchlist diff。
    本脚本可作为快速浏览工具，但不值得花精力打磨为正式产品。
    如需产品化追踪，应在 MIIT 流水线侧加能力（解析减免税目录参数、按品牌聚合等）。
"""

import sys, re, json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
_WS_ROOT = REPO_ROOT / "mashang_workspace"
if str(_WS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WS_ROOT))

EXTRACTED_DIR = _WS_ROOT / "outputs" / "miit_new_car" / "extracted" / "text"
BATCH_DATES_PATH = REPO_ROOT / "shared" / "schema" / "miit_batch_dates.json"


def load_batch_dates() -> dict:
    """Load batch → publish_date mapping if available."""
    if BATCH_DATES_PATH.exists():
        raw = json.loads(BATCH_DATES_PATH.read_text(encoding='utf-8'))
        return {int(k): v.get('publish_date', '') for k, v in raw.items()}
    return {}


def fmt_batch(batch_no: int, batch_dates: dict) -> str:
    """Format batch reference with date if available."""
    if batch_no in batch_dates and batch_dates[batch_no]:
        d = batch_dates[batch_no][:10]  # date only, drop time
        return f"第{batch_no}批 ({d})"
    return f"第{batch_no}批"


def detect_attachment_type(text: str) -> str:
    first = text[:500].replace('\x07', ' ').replace('\t', ' ')
    if '道路机动车辆生产企业及产品' in first:
        return 'new_product'
    if '减免车辆购置税' in first or '车船税减免' in first or '享受车船税' in first:
        return 'tax_exemption'
    return 'other'


def collect_batches():
    if not EXTRACTED_DIR.exists():
        print(f"错误: 未找到 {EXTRACTED_DIR}", file=sys.stderr)
        return []
    batches = []
    for d in sorted(EXTRACTED_DIR.iterdir(), key=lambda x: x.name):
        m = re.match(r'batch_(\d+)', d.name)
        if m and d.is_dir():
            txt_files = sorted(d.glob('*.txt'))
            if txt_files:
                batches.append((int(m.group(1)), txt_files))
    return batches


def get_cells(line: str) -> list[str]:
    return [c.strip() for c in line.replace('\x07', '\t').split('\t') if c.strip()]


def is_model(c: str) -> bool:
    return bool(re.match(r'^[A-Z]{2,}', c)) and len(c) >= 5


def is_enterprise(c: str) -> bool:
    return any(k in c for k in ('公司', '集团', '厂', '有限公司'))


def is_numeric(c: str) -> bool:
    cl = c.replace(',', '').replace('±', '').replace('/', '').replace('~', '')
    return bool(re.match(r'^\d+\.?\d*$', cl))


def get_enterprise_prefix(model: str) -> str:
    """Get the enterprise prefix from a model code to check brand consistency."""
    m = re.match(r'^([A-Z]{2,4})', model)
    return m.group(1) if m else ''


def extract_brand_block(cells: list[str], bp: int) -> list[dict]:
    results = []
    
    cur_ent = ''
    for j in range(bp - 1, max(0, bp - 20) - 1, -1):
        if is_enterprise(cells[j]):
            cur_ent = cells[j]
            break

    cell = cells[bp]
    is_brand_cell = '牌' in cell

    if is_brand_cell:
        next_cell = cells[bp+1] if bp + 1 < len(cells) else ''
        
        if is_model(next_cell):
            # 车船税/购置税减免 format
            brand_prefix = get_enterprise_prefix(next_cell)
            i = bp + 1
            while i + 6 < len(cells):
                if not is_model(cells[i]):
                    i += 1
                    continue
                cur_prefix = get_enterprise_prefix(cells[i])
                if cur_prefix and cur_prefix != brand_prefix:
                    break
                for k in range(i, min(len(cells), i + 3)):
                    if is_enterprise(cells[k]):
                        return results
                
                # Detect BEV vs PHEV format by checking cell at i+4
                # BEV: 整车整备质量(kg) → value > 500
                # PHEV: 燃料消耗量(L/100km) → value < 100
                val_4 = cells[i+4] if i+4 < len(cells) else ''
                is_bev = is_numeric(val_4) and float(val_4.replace(',','').replace('±','').split('/')[0]) > 200
                
                if is_bev:
                    # BEV format: model, name, type, range, weight, bat_weight, bat_energy
                    r = {
                        'enterprise': cur_ent, 'brand': cell,
                        'product_model': cells[i],
                        'common_name': cells[i+1],
                        'product_name': cells[i+2],
                        'ev_range': cells[i+3],
                        'fuel_consumption': '',
                        'displacement': '',
                        'curb_weight': cells[i+4] if i+4 < len(cells) else '',
                        'battery_weight': cells[i+5] if i+5 < len(cells) else '',
                        'battery_energy': cells[i+6] if i+6 < len(cells) else '',
                    }
                    has_num = any(is_numeric(r.get(k, '')) for k in ('ev_range', 'battery_energy', 'curb_weight'))
                    if has_num:
                        results.append(r)
                    i += 7
                else:
                    # PHEV format: model, name, type, range, fuel, disp, weight, bat_weight, bat_energy
                    r = {
                        'enterprise': cur_ent, 'brand': cell,
                        'product_model': cells[i],
                        'common_name': cells[i+1],
                        'product_name': cells[i+2],
                        'ev_range': cells[i+3],
                        'fuel_consumption': cells[i+4] if i+4 < len(cells) else '',
                        'displacement': cells[i+5] if i+5 < len(cells) else '',
                        'curb_weight': cells[i+6] if i+6 < len(cells) else '',
                        'battery_weight': cells[i+7] if i+7 < len(cells) else '',
                        'battery_energy': cells[i+8] if i+8 < len(cells) else '',
                    }
                    has_num = any(is_numeric(r.get(k, '')) for k in ('ev_range', 'battery_energy', 'curb_weight'))
                    if has_num:
                        results.append(r)
                    i += 9
        else:
            # 新产品公告
            if bp + 3 < len(cells):
                r = {'enterprise': cur_ent, 'brand': cell,
                     'product_name': cells[bp+1], 'product_model': cells[bp+2]}
                results.append(r)
        return results

    # Brand in content cell
    model_pos = -1
    for j in range(max(0, bp - 3), min(len(cells), bp + 5)):
        if is_model(cells[j]):
            model_pos = j
            break
    if model_pos < 0:
        return results

    brand_prefix = get_enterprise_prefix(cells[model_pos])
    i = model_pos
    while i + 8 < len(cells):
        if not is_model(cells[i]):
            i += 1
            continue
        cur_prefix = get_enterprise_prefix(cells[i])
        if cur_prefix and cur_prefix != brand_prefix:
            break
        for k in range(i, min(len(cells), i + 3)):
            if is_enterprise(cells[k]):
                return results
        
        val_4 = cells[i+4] if i+4 < len(cells) else ''
        is_bev = is_numeric(val_4) and float(val_4.replace(',','').replace('±','').split('/')[0]) > 200
        
        if is_bev:
            r = {
                'enterprise': cur_ent,
                'product_model': cells[i],
                'common_name': cells[i+1],
                'product_name': cells[i+2],
                'ev_range': cells[i+3],
                'fuel_consumption': '',
                'displacement': '',
                'curb_weight': cells[i+4] if i+4 < len(cells) else '',
                'battery_weight': cells[i+5] if i+5 < len(cells) else '',
                'battery_energy': cells[i+6] if i+6 < len(cells) else '',
            }
            has_num = any(is_numeric(r.get(k, '')) for k in ('ev_range', 'battery_energy', 'curb_weight'))
            if has_num:
                results.append(r)
            i += 7
        else:
            r = {
                'enterprise': cur_ent,
                'product_model': cells[i],
                'common_name': cells[i+1],
                'product_name': cells[i+2],
                'ev_range': cells[i+3],
                'fuel_consumption': cells[i+4] if i+4 < len(cells) else '',
                'displacement': cells[i+5] if i+5 < len(cells) else '',
                'curb_weight': cells[i+6] if i+6 < len(cells) else '',
                'battery_weight': cells[i+7] if i+7 < len(cells) else '',
                'battery_energy': cells[i+8] if i+8 < len(cells) else '',
            }
            if not is_model(r['product_model']):
                i += 1
                continue
            has_num = any(is_numeric(r.get(k, '')) for k in ('ev_range', 'battery_energy', 'curb_weight'))
            if not has_num:
                i += 1
                continue
            results.append(r)
            i += 9

    return results


def extract_records(text: str, brand: str) -> list[dict]:
    records = []
    seen = set()
    for line in text.split('\n'):
        if brand not in line:
            continue
        cells = get_cells(line)
        if len(cells) < 5:
            continue
        brand_positions = [i for i, c in enumerate(cells) if brand in c]
        for bp in brand_positions:
            results = extract_brand_block(cells, bp)
            for r in results:
                # Deduplicate by product_model
                pm = r.get('product_model', '')
                if pm and pm not in seen:
                    seen.add(pm)
                    records.append(r)
    return records


def classify(records: list[dict], att_type: str) -> tuple[list, list]:
    """Split records into new_products and tax_exemption."""
    np = []
    te = []
    for r in records:
        pn = r.get('product_name', '')
        ev = r.get('ev_range', '')
        if ev and (is_numeric(ev) or 'km' in ev):
            te.append(r)
        elif any(k in pn for k in ('纯电动', '插电式', '换电式')):
            if r.get('battery_energy') or r.get('curb_weight'):
                te.append(r)
            else:
                np.append(r)
        else:
            np.append(r)
    return np, te


def format_summary(brand, batch_data, batch_dates=None):
    lines = []
    lines.append(f"# {brand}品牌 MIIT 公告产品线汇总")
    lines.append("")

    def is_brand_record(e, brand):
        return brand in str(e.get('brand', '')) or brand in str(e.get('product_name', '')) or brand in str(e.get('common_name', ''))

    grouped = defaultdict(list)
    for bno in sorted(batch_data):
        info = batch_data[bno]
        for e in info.get('tax_exemption', []):
            if not is_brand_record(e, brand):
                continue
            pm = e.get('product_model', '')
            base = re.sub(r'[A-Z]+$', '', pm)[:8]
            grouped[base].append(('te', bno, e))
        for e in info.get('new_products', []):
            if not is_brand_record(e, brand):
                continue
            pm = e.get('product_model', '')
            base = pm[:8] if pm else 'unknown'
            grouped[base].append(('np', bno, e))

    lines.append(f"| 车型 | 名称 | 动力 | 批次 | 纯电续航 | 电池能量 | 整备质量 | 备注 |")
    lines.append(f"|:----:|:----:|:----:|:----:|:-------:|:--------:|:-------:|:----|")

    for base in sorted(grouped):
        entries = grouped[base]
        te_list = [(b, e) for t, b, e in entries if t == 'te']
        np_list = [(b, e) for t, b, e in entries if t == 'np']
        last = te_list[-1][1] if te_list else (np_list[-1][1] if np_list else {})
        all_batches = sorted(set(b for b, _ in te_list) | set(b for b, _ in np_list))
        has_new = any(t == 'np' for t, _, _ in entries)

        cn = last.get('common_name', '') or ''
        ev = last.get('ev_range', '') or ''
        bat = last.get('battery_energy', '') or ''
        wt = last.get('curb_weight', '') or ''
        pn = last.get('product_name', '') or ''
        note = '🆕 新申报' if has_new else '目录更新'

        if '纯电动' in pn:
            energy = '纯电 BEV'
        elif '增程' in pn:
            energy = '增程 EREV'
        elif '插电式混合' in pn:
            energy = '插混 PHEV'
        elif '换电式' in pn:
            energy = '换电 BEV'
        else:
            energy = pn[:12]

        batch_str = '、'.join(fmt_batch(b, batch_dates) for b in all_batches)
        lines.append(f"| {base} | {cn} | {energy} | {batch_str} | {ev} | {bat} | {wt} | {note} |")

        # Variants
        vars_set = set()
        for _, e in te_list:
            pm = e.get('product_model', '')
            vr = e.get('ev_range', '')
            be = e.get('battery_energy', '')
            sfx = pm.replace(base, '') if pm != base else ''
            vars_set.add(f"{sfx}: {be}kWh/{vr}km")
        if vars_set:
            lines.append(f"| _变体_ | {'; '.join(sorted(vars_set))} | | | | | | |")

    lines.append("")
    lines.append("---")
    lines.append("### 各批次明细")
    lines.append("")

    for bno in sorted(batch_data):
        info = batch_data[bno]
        lines.append(f"#### {fmt_batch(bno, batch_dates)}")
        lines.append("")

        def is_brand_rec(e):
            return brand in str(e.get('brand', '')) or brand in str(e.get('product_name', '')) or brand in str(e.get('common_name', ''))

        np_list = [e for e in info.get('new_products', []) if is_brand_rec(e)]
        te_list = [e for e in info.get('tax_exemption', []) if is_brand_rec(e)]

        if np_list:
            lines.append("**新产品公告：**")
            lines.append("")
            lines.append("| 企业 | 产品名称 | 产品型号 |")
            lines.append("|------|:-------:|:--------:|")
            for e in np_list:
                lines.append(f"| {e.get('enterprise','')} | {e.get('product_name','')} | {e.get('product_model','')} |")
            lines.append("")

        if te_list:
            lines.append("**减免目录：**")
            lines.append("")
            lines.append("| 企业 | 型号 | 名称 | 产品类型 | 续航 | 油耗 | 排量 | 质量 | 电池重 | 电池 |")
            lines.append("|------|:----:|:----:|:-------:|:----:|:----:|:----:|:----:|:------:|:----:|")
            for e in te_list:
                lines.append(f"| {e.get('enterprise','')} | {e.get('product_model','')} | {e.get('common_name','')} | {e.get('product_name','')} | {e.get('ev_range','')} | {e.get('fuel_consumption','')} | {e.get('displacement','')} | {e.get('curb_weight','')} | {e.get('battery_weight','')} | {e.get('battery_energy','')} |")
            lines.append("")

    lines.append("")
    lines.append("---")
    lines.append(f"生成: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    batch_str = '、'.join(fmt_batch(b, batch_dates) for b in sorted(batch_data))
    lines.append(f"来源: MIIT {batch_str}")
    return '\n'.join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='MIIT 品牌产品线公告汇总')
    parser.add_argument('--brand', '-b', required=True, help='品牌名称')
    parser.add_argument('--output', '-o', help='输出 Markdown 文件')
    args = parser.parse_args()

    brand = args.brand
    batches = collect_batches()
    if not batches:
        sys.exit(1)

    batch_data = {}

    for bno, txt_files in batches:
        store = {'new_products': [], 'tax_exemption': []}
        found = False
        for f in txt_files:
            text = f.read_text(encoding='utf-8', errors='ignore')
            if brand not in text:
                continue
            atype = detect_attachment_type(text)
            records = extract_records(text, brand)
            if records:
                np_list, te_list = classify(records, atype)
                if np_list:
                    store['new_products'].extend(np_list)
                    found = True
                if te_list:
                    store['tax_exemption'].extend(te_list)
                    found = True
        if found:
            batch_data[bno] = store

    if not batch_data:
        print(f"未找到品牌「{brand}」。")
        sys.exit(0)

    batch_dates = load_batch_dates()
    out = format_summary(brand, batch_data, batch_dates)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(out, encoding='utf-8')
        print(f"  {args.output}")
    else:
        print(out)


if __name__ == '__main__':
    main()
