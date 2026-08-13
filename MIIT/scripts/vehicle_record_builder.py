#!/usr/bin/env python3
"""
MIIT 车型记录构建器（公共领域逻辑层）

把「原始资料 → 标准字段」的领域逻辑从消费脚本（04 宽表 / 07 统一Dataset）中抽出来：
canonical 构建器不再反向依赖消费脚本，双方共同 import 本模块。

数据源：
  P1 scan（search_results/scan_batch_XXX.md）      → 车型身份行
  P2 详情页（vehicle_details/{batch}_{型号}-{产品名}.md）→ 尺寸/电池/电机/供应商/座位
  P3 车船税（vehicle_tax/车型清单_第XX批车船税.json）   → 容量/续航/整备/通用名称
  workflow/model_name_map.json                        → 通用名称补充

公共入口：
  parse_detail(model, batch)  读取并解析详情页 .md
  merge_tax(model_id, batch)  按型号合并车船税记录
  resolve_name(model, tax)    通用名称解析
  build_record(model, md, tax) 一行标准记录（原始字段 + 衍生中间量）
  derive_metrics(record)      就地计算衍生指标（首值口径）
  explode_variants(records)   多配置展开（宽表用）
"""

import json
import re
from pathlib import Path

from miit_paths import (  # noqa: E402
    DEFAULT_BATCH,
    VEHICLE_DETAILS_DIR,
    tax_json_path,
    load_batches,
)

# ── Battery chemistry normalization ──

_BATT_CHEM_MAP = [
    (r'磷酸铁锂', 'LFP', '磷酸铁锂'),
    (r'镍钴锰', 'NCM', '三元锂'),
    (r'三元', 'NCM', '三元锂'),
]


def normalize_battery_chemistry(raw: str) -> tuple[str, str, bool]:
    """Return (chemistry_code, chemistry_cn, ncm_explicit_flag)."""
    if not raw:
        return '', '', False
    for pat, code, cn in _BATT_CHEM_MAP:
        if re.search(pat, raw):
            return code, cn, bool(re.search(r'镍钴锰', raw))
    return 'OTHER', '其他', False


# ── Motor power parsing ──

def parse_motor_power(raw: str) -> tuple[int, list[float], float]:
    """Return (motor_count, power_list, total_peak_kw)."""
    if not raw:
        return 0, [], 0.0
    cleaned = raw.replace('kW', '').strip()
    nums = re.findall(r'(\d+(?:\.\d+)?)', cleaned)
    powers = [float(n) for n in nums if float(n) > 1]
    if not powers:
        return 0, [], 0.0
    return len(powers), powers, round(sum(powers), 1)


# ── Vehicle type classification（两层派生维度，Gov/EIDC 共用） ──
# source_vehicle_type = source fact（保留原始产品名称语义）
# vehicle_category / vehicle_subcategory = deterministic derived dimensions
# 分类只做 analysis projection，绝不参与 canonical identity。

# subcategory 关键词 → (category, subcategory)
_VC_SUBCAT_RULES = [
    # ── motorcycle ──
    (r'摩托|轻便摩托|正三轮摩托|两轮摩托|边三轮摩托', 'motorcycle', 'motorcycle'),
    # ── trailer（挂车优先于货车，避免「半挂货车」误分） ──
    (r'挂车|半挂|中置轴', 'trailer', 'trailer'),
    # ── passenger_vehicle ──
    (r'轿车', 'passenger_vehicle', 'sedan'),
    (r'乘用车|多用途|MPV|越野车|SUV|旅居车', 'passenger_vehicle', 'suv_mpv'),
    # ── commercial_vehicle: bus ──
    (r'客车|公交|校车|低地板|低入口', 'commercial_vehicle', 'bus'),
    # ── commercial_vehicle: tractor（牵引车，独立于 truck） ──
    (r'牵引', 'commercial_vehicle', 'tractor'),
    # ── commercial_vehicle: sanitation & fire（环卫/消防优先于 generic truck） ──
    (r'垃圾|洒水|洗扫|清扫|清洗|吸污|吸粪|扫路|抑尘|护栏抢修|除雪|消防|救援|举高喷射|泡沫|水罐|压缩空气泡沫|泵浦|干粉|登高平台|涡喷|机场消防|洗消|自装卸消防',
     'commercial_vehicle', 'sanitation_fire'),
    # ── commercial_vehicle: truck（货车/底盘/运输车/载货/自卸/厢式/仓栅/栏板/翼开启/冷藏/罐式/搅拌/混凝土/邮政/囚车/救护/检测/巡逻/指挥/通信/清障/起重/医疗/维修/工程/油田/吊装/客车专用等） ──
    (r'货车|载货|底盘|运输|自卸|厢式|仓栅|栏板|翼开启|冷藏|罐式|搅拌|混凝土|邮政|囚车|救护|检测|巡逻|指挥|通信|清障|起重|医疗|维修|工程车|油田|吊装|泵|修井|固井|压裂|钻机|道路|桥检|照明|电源车|发电|运钞|宣传|售货|旅居运输|牵引杆挂车',
     'commercial_vehicle', 'truck'),
    # ── commercial_vehicle: special_vehicle（专用作业车：非货运底盘/箱式，且无消防/环卫归属） ──
    (r'高空作业|宿营|文化生活服务|排水抢险|后勤保障|商务车|路面冲洗|冲洗|防撞缓冲|救险|车厢可卸|炊事|配电|监测|路面养护|养护|洗井|公共服务|警犬|福祉|教练|净水|殡仪|银行|园林绿化|绿化|运材|采油|防暴|污水处理|净水车|背罐|吸引压送|巡检|巡检车|工程抢险|抢险|旅居车营地|应急|保障|巡视|倒装|加油车|加气|燃料加注|售油|售气|碎石封层|沙漠车|运兵车|混配车|电视车|洒布车|行动不便|同步碎石|封层|测井车|物料处置|清淤|工具车|疏通|押运|舞台车|连续油管|伸缩式皮带|输送车',
     'commercial_vehicle', 'special_vehicle'),
    # ── commercial_vehicle: special_vehicle（其余商用车） ──
    (r'汽车起重机|全地面起重机|汽车吊|装载|挖掘|压路|推土|消防车专用|特种作业',
     'commercial_vehicle', 'special_vehicle'),
]

# 兜底规则：仅根据大类关键词分类，不细分 subcategory
_VC_CATEGORY_RULES = [
    (r'摩托', 'motorcycle'),
    (r'挂车|半挂|中置轴', 'trailer'),
    (r'轿车|乘用车|多用途|越野车|SUV|旅居车', 'passenger_vehicle'),
    (r'客车|公交|校车', 'commercial_vehicle'),
    (r'货车|载货|底盘|牵引|运输|消防|垃圾|洒水|洗扫|清洗|扫路|除雪|救护|巡逻|清障|起重|自卸|厢式|仓栅|栏板|冷藏|罐式|邮政|混凝土',
     'commercial_vehicle'),
]

# 其他所有 → ('other', 'other')，空输入 → ('other', 'other')

# 目录序号格式（官方企业类别信号）：
#   （X）数字 = 带地区前缀（民用改装车/专用车企业，目录序号如 "(一)03"）
#   纯数字   = 整车企业（汽车/摩托车/起重机）
RE_CATALOG_REGION_PREFIX = re.compile(r'^[（(][一二三四五六七八九十]+[）)]\d+')


def classify_vehicle_type(source_vehicle_type: str,
                          catalog_no: str = "") -> tuple[str, str]:
    """Return (vehicle_category, vehicle_subcategory) from a source vehicle type string.

    分类信号优先级（官方优先 + 产品名正则兜底）：
      1. 产品名强规则（_VC_SUBCAT_RULES，含摩托车/挂车/乘用车/客车/牵引/消防环卫/货车/专用车）
         → 以产品名为准（第一部分官方标题稀疏，摩托车混排无独立标题，必须靠产品名）
      2. 产品名未命中任何强规则 + 目录序号带地区前缀（（X）数字）
         → 官方信号：该企业为专用车/改装车企业 → commercial_vehicle/special_vehicle
      3. 产品名 category 规则兜底（_VC_CATEGORY_RULES）
      4. 其余 → ('other', 'other')

    空字符串 → ('other', 'other')，保持可解释（无法稳定归类的母体）。
    """
    raw = (source_vehicle_type or "").strip()
    if not raw:
        return ('other', 'other')
    cat, sub = 'other', 'other'
    matched = False
    for pat, c, s in _VC_SUBCAT_RULES:
        if re.search(pat, raw):
            cat, sub = c, s
            matched = True
            break
    if not matched:
        # 官方目录序号信号：专用车/改装车企业（（X）数字），产品名无强规则时归入
        if RE_CATALOG_REGION_PREFIX.match((catalog_no or "").strip()):
            cat, sub = 'commercial_vehicle', 'special_vehicle'
        else:
            for pat, c in _VC_CATEGORY_RULES:
                if re.search(pat, raw):
                    cat, sub = c, c
                    break
    # passenger_vehicle 兜底子类
    if cat == 'passenger_vehicle' and sub not in ('sedan', 'suv_mpv'):
        sub = 'other_passenger'
    return (cat, sub)


# ── Analysis scope（业务分析默认母体） ──
# MIIT 是全量监管数据仓（摩托车/专用车/挂车均为公告事实，Source/Canonical 完整保留）。
# 业务分析层（mashang-service）默认只消费乘用车 → analysis_scope = in_scope。
# 本字段是派生维度，不参与 identity，也绝不删除任何 canonical 记录。

ANALYSIS_SCOPE_IN = {"passenger_vehicle"}


def resolve_analysis_scope(vehicle_category: str) -> str:
    """Return 'in_scope' | 'out_of_scope'（默认业务分析母体 = 乘用车）。"""
    return "in_scope" if (vehicle_category or "") in ANALYSIS_SCOPE_IN else "out_of_scope"


# ── Canonical scope gate（乘用车业务事实层） ──
# Source / Parser 层保留全量道路机动车辆；canonical（data/vehicle_parameters/）只保留乘用车。
# gate 的最终事实判断基于 vehicle_category（而非 analysis_scope），
# 避免未来 analysis_scope 业务配置变化反过来改变历史事实定义。
#
# ⚠ 架构约束（passenger eligibility 是 source-record 级 existential）：
#   gate 必须在聚合（by model_code）之前、逐 source record 执行。
#   同一 batch:model_code 只要存在至少一条合法 passenger_vehicle source record，
#   该 vehicle record 即进入 passenger canonical；非乘用变体仍留在 source evidence。
#   禁止把 gate 移到聚合之后按"首条记录分类"判定——会漏掉同 chassis 多车型的乘用变体。

CANONICAL_VEHICLE_CATEGORY = "passenger_vehicle"


def is_canonical_in_scope(record: dict) -> bool:
    """Return True if record 应进入 canonical（vehicle_category == passenger_vehicle）。

    统一 scope gate：Gov / EIDC 两条 source branch 共用一个规则。
    """
    return (record or {}).get("vehicle_category") == CANONICAL_VEHICLE_CATEGORY


def classify_source_record(source_record: dict) -> tuple[str, str]:
    """thin wrapper：对 EIDC source record 直接做分类（在 build/enrichment 之前）。

    仅读取 source record 的原始字段，分类规则唯一实现仍是 classify_vehicle_type。
    返回 (vehicle_category, vehicle_subcategory)。
    """
    src_type = (source_record.get("vehicle_type_raw")
                or source_record.get("product_name_raw")
                or source_record.get("product_name") or "")
    catalog_no = source_record.get("catalog_no_raw") or source_record.get("catalog_no") or ""
    return classify_vehicle_type(src_type, catalog_no)


# ── Supplier grouping ──

_SUPPLIER_GROUP = [
    (r'绍兴弗迪|西安弗迪|无为弗迪|温州弗迪|广西东盟弗迪|汕尾弗迪|青海弗迪|重庆弗迪', 'BYD', '弗迪系'),
    (r'合肥比亚迪|深圳比亚迪|西咸新区比亚迪', 'BYD', '比亚迪汽车'),
    (r'宁德时代|江苏时代|四川时代|宜宾三江时代|中州时代|广东瑞庆时代|川渝时代|时代[一汽广汽长安]', 'CATL', '宁德时代系'),
    (r'科新动力', 'CATL', '宁德时代系（合资）'),
    (r'中创新航', 'CALB', '中创新航'),
    (r'蜂巢能源', 'SVOLT', '蜂巢能源'),
    (r'国轩高科', 'GOTION', '国轩高科'),
    (r'欣旺达', 'SUNWODA', '欣旺达'),
    (r'爱尔集新能源', 'LG', 'LG新能源'),
    (r'南昌欣旺达', 'SUNWODA', '欣旺达'),
    (r'浙江理想汽车电池', 'LIXIANG', '理想汽车电池'),
]


def resolve_supplier_group(name: str) -> tuple[str, str]:
    """Return (group_code, group_name)."""
    if not name:
        return ('', '')
    for pat, code, gname in _SUPPLIER_GROUP:
        if re.search(pat, name):
            return (code, gname)
    return ('OTHER', '其他')


def vertical_integration(cell_supplier: str, pack_supplier: str) -> str:
    """Classify: same_company / same_group / cross_group"""
    cell_code, _ = resolve_supplier_group(cell_supplier)
    pack_code, _ = resolve_supplier_group(pack_supplier)
    if not cell_code or not pack_code:
        return ''
    if cell_supplier == pack_supplier:
        return 'same_company'
    if cell_code == pack_code:
        return 'same_group'
    return 'cross_group'


# ── P1 scan / P3 tax 读取 ──

def parse_scan_md(path: Path) -> list[dict]:
    """Extract model info list from scan_batch_XXX.md's embedded JSON."""
    text = path.read_text()
    m = re.search(r'```json\n(.+?)\n```', text, re.DOTALL)
    if not m:
        raise ValueError("No JSON block found in scan file")
    data = json.loads(m.group(1))
    models = []
    for brand_entry in data["brands"]:
        brand = brand_entry["catalog"]
        for row in brand_entry["all_rows"]:
            models.append({
                "brand": brand,
                "enterprise_name": row["qymc"],
                "brand_sign": row["cpsb"],
                "product_name": row["cpmc"],
                "model_id": row["cpxh"],
                "detail_url": row.get("detail_url", ""),
            })
    return models


def load_tax_index(path: Path) -> dict:
    """Build {产品型号: record} index from 车船税 JSON sections."""
    data = json.loads(path.read_text())
    index = {}
    for sec_name, sec in data.get("sections", {}).items():
        for rec in sec.get("records", []):
            mid = rec.get("产品型号", "") or rec.get("车辆型号", "")
            if mid:
                if mid not in index:
                    index[mid] = {}
                index[mid].update(rec)
                index[mid]["_tax_section"] = sec_name
    return index


# ── P2 详情页 .md 解析 ──

def read_brand_md(brand: str, model_id: str, batch: str = DEFAULT_BATCH) -> dict | None:
    """Read the .md detail file for a model from data/vehicle_details/.

    文件名按 `{batch}_{model_id}-{产品名}.md`（身份 = batch:model_code），型号不假设全局唯一。
    """
    matches = list(VEHICLE_DETAILS_DIR.glob(f"{batch}_{model_id}-*.md"))
    if not matches:
        return None
    return _parse_md_file(matches[0])


def _parse_md_file(path: Path) -> dict:
    """Parse a brand .md file into a flat key-value dict."""
    text = path.read_text()
    data = {}

    for m in re.finditer(r'^\| ([^|]+) \| ([^|]+) \|', text, re.MULTILINE):
        key = m.group(1).strip()
        val = m.group(2).strip()
        if key and val and key not in ("字段", "内容", "字段", "数值", "视角", "链接", "------"):
            data[key] = val

    dim_key = "外形尺寸(mm)"
    if dim_key not in data:
        for k in data:
            if "外形尺寸" in k:
                dim_key = k
                break
    dim_raw = data.get(dim_key, "")
    if dim_raw:
        dims = {}
        for label in ["长", "宽", "高"]:
            m2 = re.search(rf'{label}[：:]\s*(\d+)', dim_raw)
            if m2:
                dims[label] = m2.group(1)
        if dims:
            data["外形尺寸(mm)_parsed"] = json.dumps(dims, ensure_ascii=False)

    other = data.get("其它", "")
    if other:
        _VAL = r'[^，,;。；.\n]+'

        m_batt = re.search(r'储能装置种类[：:](%s)' % _VAL, other)
        if not m_batt:
            m_batt = re.search(r'储能装置种类为(%s)' % _VAL, other)
        if m_batt:
            data.setdefault("储能装置种类", m_batt.group(1).strip())

        m_combo = re.search(r'储能装置种类/单体生产企业/总成生产企业[：:](%s)' % _VAL, other)
        if m_combo:
            parts = [p.strip() for p in m_combo.group(1).split("/")]
            if len(parts) >= 1:
                data.setdefault("储能装置种类", parts[0])
            if len(parts) >= 2:
                data.setdefault("电池单体企业", parts[1])
            if len(parts) >= 3:
                data.setdefault("电池总成企业", parts[2])

        if not data.get("电池单体企业"):
            for pat in [
                r'储能装置单体的生产企业[：:](%s)' % _VAL,
                r'储能装置单体生产企业[：:](%s)' % _VAL,
                r'储能装置单体厂家为(%s)' % _VAL,
                r'单体生产企业[：:](%s)' % _VAL,
            ]:
                m_c = re.search(pat, other)
                if m_c:
                    data.setdefault("电池单体企业", m_c.group(1).strip())
                    break
        if not data.get("电池总成企业"):
            for pat in [
                r'储能装置总成的生产企业[：:](%s)' % _VAL,
                r'储能装置总成生产企业[：:](%s)' % _VAL,
                r'储能装置总成厂家为(%s)' % _VAL,
                r'总成生产企业[：:](%s)' % _VAL,
            ]:
                m_p = re.search(pat, other)
                if m_p:
                    data.setdefault("电池总成企业", m_p.group(1).strip())
                    break

        if not data.get("电池单体企业") and not data.get("电池总成企业"):
            m_cell_a = re.search(r'生产企业[：:](%s)' % _VAL, other)
            if m_cell_a:
                raw = m_cell_a.group(1)
                if "(单体)" in raw or "(总成)" in raw:
                    for part in raw.split("/"):
                        part = part.strip()
                        m_c = re.match(r'([^，,;。]+?)\(单体\)', part)
                        if m_c:
                            data.setdefault("电池单体企业", m_c.group(1).strip())
                        m_p = re.match(r'([^，,;。]+?)\(总成\)', part)
                        if m_p:
                            data.setdefault("电池总成企业", m_p.group(1).strip())
                else:
                    data.setdefault("电池总成企业", raw.strip())

    data["_md_file"] = path.name
    return data


# ── 数值解析 ──

def parse_num(s: str) -> float | None:
    """Extract the nominal (first) number from a string."""
    s = s.strip()
    s = s.split("/")[0].split("±")[0].split("（")[0].split("(")[0].strip()
    if not s:
        return None
    s = s.split("（")[0].split("(")[0].strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_tolerance(s: str) -> tuple[float | None, float | None, float | None]:
    """Parse a string like '400±12' → (nominal, low, high)."""
    s = s.strip()
    s = s.split("/")[0].split("（")[0].split("(")[0].strip()
    m = re.match(r'([\d.]+)\s*[±]\s*([\d.]+)', s)
    if m:
        nominal = float(m.group(1))
        tol = float(m.group(2))
        return nominal, nominal - tol, nominal + tol
    try:
        v = float(s)
        return v, v, v
    except ValueError:
        return None, None, None


def parse_dims(text: str) -> dict:
    """Parse 外形尺寸(mm) -> {长, 宽, 高}."""
    result = {}
    for label in ["长", "宽", "高"]:
        m = re.search(rf'{label}[：:]\s*(\d+)', text)
        if m:
            result[label] = m.group(1)
    return result


# ── 标准字段构建 ──

def build_record(model: dict, md: dict | None, tax: dict) -> dict:
    """Merge one model into a wide record with all fields + derived metrics."""
    r = {}

    # ── Identity ──
    r["品牌"] = model["brand"]
    r["企业名称"] = model["enterprise_name"]
    r["产品型号"] = model["model_id"]
    r["产品名称"] = model["product_name"]

    # ── Vehicle type classification（derived dimension, not identity） ──
    src_type = model.get("product_name", "")
    if not src_type and md:
        src_type = md.get("产品名称", "")
    r["source_vehicle_type"] = src_type
    vcat, vsub = classify_vehicle_type(src_type)
    r["vehicle_category"] = vcat
    r["vehicle_subcategory"] = vsub
    r["analysis_scope"] = resolve_analysis_scope(vcat)
    r["catalog_no"] = ""

    # ── Tax/battery metrics availability flag ──
    mid = model["model_id"]
    tax_available = bool(tax and tax.get("动力蓄电池总能量_kWh", "") or tax.get("动力蓄电池组总能量_kWh", ""))
    r["tax_catalog_match_flag"] = "1" if tax_available else "0"
    r["battery_metrics_available_flag"] = "1" if tax_available else "0"

    # ── 动力形式 (from md) ──
    power = ""
    if md:
        power = md.get("新能源类型", "") or ""
        if not power:
            fuel = md.get("燃料种类", "")
            name = md.get("产品名称", "")
            if "纯电动" in fuel or ("纯电动" in name and "混合" not in name):
                power = "纯电动"
            elif "增程" in name:
                power = "插电式增程混合动力"
            elif "混合" in fuel or "混合" in name:
                power = "插电式混合动力"
            elif "燃料电池" in name:
                power = "燃料电池"
    mid = model["model_id"]
    pname = model["product_name"]
    if "REEV" in mid.upper() or "增程" in pname:
        power = "插电式增程混合动力"
    r["动力形式"] = power

    # ── 电池类型 (from md) ──
    batt_type = ""
    if md:
        batt_type = md.get("储能装置种类", "")
    r["电池类型"] = batt_type
    chem_code, chem_cn, ncm_flag = normalize_battery_chemistry(batt_type)
    r["battery_chemistry"] = chem_code
    r["battery_chemistry_cn"] = chem_cn
    r["battery_ncm_explicit_flag"] = "1" if ncm_flag else "0"

    # ── Motor power (must be after power type determination) ──
    _is_bev_power = ("纯电动" in power) and ("混合" not in power)
    motor = ""
    if md:
        motor_raw = ""
        for mk in ["驱动电机峰值功率(kW)", "驱动电机峰值功率_kW"]:
            motor_raw = md.get(mk, "")
            if motor_raw:
                break
        if not motor_raw and _is_bev_power:
            for mk in ["功率(kw)", "功率_kw", "功率", "功率(kW)"]:
                motor_raw = md.get(mk, "")
                if motor_raw:
                    break
        if motor_raw:
            nums = re.findall(r'(\d+)\s*kW', motor_raw)
            if not nums:
                nums = re.findall(r'(?<![\d.])(\d+)(?![\d.])', motor_raw.replace("kW", "").replace("kw", ""))
            if nums:
                motor = "/".join(nums) + "kW"
            else:
                motor = motor_raw.replace("\n", " ")[:60]
        if not motor:
            other = md.get("其它", "")
            if other:
                m_pk = re.search(r'峰值功率[（(][^）)]*[）)]\s*[：:]\s*(\d+)\s*kW', other)
                if not m_pk:
                    m_pk = re.search(r'峰值功率[：:]\s*(\d+)\s*kW', other)
                if m_pk:
                    motor = m_pk.group(1) + "kW"
    r["电机功率(kW)"] = motor
    m_count, m_list, m_total = parse_motor_power(motor)
    r["motor_count"] = m_count
    r["motor_power_list"] = " / ".join(str(p) for p in m_list) if m_list else ""
    r["motor_total_peak_kw"] = m_total
    r["single_multi_motor"] = "单电机" if m_count == 1 else f"{m_count}电机" if m_count > 1 else ""

    # ── 电芯/总成供应商 (from md) ──
    supplier = ""
    cell_sup = ""
    pack_sup = ""
    if md:
        supplier = md.get("电池单体_总成企业", "") or md.get("电池单体/总成企业", "") or ""
        if not supplier:
            cell_sup = md.get("电池单体企业", "")
            pack_sup = md.get("电池总成企业", "")
            parts = [x for x in [cell_sup, pack_sup] if x]
            if parts:
                supplier = " / ".join(parts)
        else:
            if " / " in supplier:
                sp = supplier.split(" / ", 1)
                cell_sup = sp[0].strip()
                pack_sup = sp[1].strip() if len(sp) > 1 else ""
            else:
                cell_sup = supplier
                pack_sup = supplier
    r["电芯/总成供应商"] = supplier
    r["cell_supplier"] = cell_sup
    r["pack_supplier"] = pack_sup
    cell_grp_code, cell_grp_name = resolve_supplier_group(cell_sup)
    pack_grp_code, pack_grp_name = resolve_supplier_group(pack_sup)
    r["cell_supplier_group"] = cell_grp_name
    r["pack_supplier_group"] = pack_grp_name
    r["vertical_integration_flag"] = vertical_integration(cell_sup, pack_sup)

    # ── 附件2 fields (from tax) ──
    bat_energy_str = tax.get("动力蓄电池总能量_kWh", "") or tax.get("动力蓄电池组总能量_kWh", "")
    bat_mass_str = tax.get("动力蓄电池总质量_kg", "") or tax.get("动力蓄电池组总质量_kg", "")
    range_str = tax.get("纯电动续驶里程_km", "")
    curb_str = tax.get("整车整备质量_kg", "")

    bat_energy = parse_num(bat_energy_str)
    bat_mass = parse_num(bat_mass_str)
    elec_range = parse_num(range_str)
    curb_weight = parse_num(curb_str)

    if curb_weight is None and md:
        cw = md.get("整备质量(kg)", "")
        if not cw:
            cw = md.get("整备质量", "")
        if cw:
            curb_weight = parse_num(cw)

    r["电池容量(kWh)"] = bat_energy_str
    r["电池容量_num"] = bat_energy
    r["电池质量(kg)"] = bat_mass_str
    r["电池质量_num"] = bat_mass
    r["纯电续航(km)"] = range_str
    r["纯电续航_num"] = elec_range
    r["整备质量(kg)"] = curb_str
    r["整备质量_num"] = curb_weight

    # ── 外形尺寸 (from md) ──
    length = width = height = ""
    if md:
        for dk in ["外形尺寸(mm)", "外形尺寸"]:
            dv = md.get(dk, "")
            if dv:
                dims = parse_dims(dv)
                length = dims.get("长", "")
                width = dims.get("宽", "")
                height = dims.get("高", "")
                break
    r["长(mm)"] = length
    r["宽(mm)"] = width
    r["高(mm)"] = height

    # ── 增程器 (from md, only for non-BEV / PHEV/EREV) ──
    engine_parts = []
    if md and ("混合" in power or "增程" in power or "燃料电池" in power):
        eng_model = md.get("发动机型号", "")
        eng_disp = md.get("排量(ml)", "")
        eng_power = md.get("发动机最大净功率(kW)", "") or md.get("发动机最大净功率_kW", "")
        eng_co = md.get("发动机企业", "")
        if eng_model:
            engine_parts.append(eng_model)
        if eng_disp:
            engine_parts.append(f"{eng_disp}ml")
        if eng_power:
            engine_parts.append(f"{eng_power}kW")
        if eng_co:
            engine_parts.append(eng_co)
    r["增程器"] = " / ".join(engine_parts)

    r["_bat_energy_num"] = bat_energy
    r["_bat_mass_num"] = bat_mass
    _bm_nom, _bm_lo, _bm_hi = parse_tolerance(bat_mass_str)
    r["_bat_mass_lo"] = _bm_lo
    r["_bat_mass_hi"] = _bm_hi
    r["_range_num"] = elec_range
    r["_curb_num"] = curb_weight
    if not tax_available:
        r["missing_reason"] = "来源未覆盖（附件2车船税未收录该车型）"
    else:
        r["missing_reason"] = ""
    power_type = r.get("动力形式", "")
    if tax_available:
        r["metric_scope"] = "全数据"
    elif "纯电动" in power_type and "混合" not in power_type:
        r["metric_scope"] = "仅增程/插混（纯电车型附件2未覆盖）"
    else:
        r["metric_scope"] = "数据缺失"

    return r


# ── 通用名称解析 ──

def resolve_name(tax_rec: dict, model_code: str, name_map: dict | None = None) -> str:
    """通用名称：优先车船税 `通用名称`（多名称取第一个），其次 model_name_map 补充。"""
    name_map = name_map or {}
    raw = (tax_rec or {}).get("通用名称", "")
    common = raw.split(",")[0].strip() if raw else ""
    return common or name_map.get(model_code, "")


# ── EIDC source record → 领域 contract ──

RE_MODEL_CODE = re.compile(r'^[A-Z]{2,4}\d{2,}[A-Z0-9]{0,6}$')


def normalize_model_code(raw: str) -> tuple[str, bool]:
    """型号规范化 + 合法性校验。

    EIDC road source 的 model_code_raw 已是拆分后的单型号（如 CA6471）。
    校验规则与 Gov 型号一致（[A-Z]{2,4}数字+[A-Z0-9]{0,6}）。
    返回 (model_code, valid)。
    """
    code = (raw or "").strip().upper()
    valid = bool(code and RE_MODEL_CODE.match(code))
    return (code, valid) if valid else (raw or "", False)


def match_eidc_enrichment(model_code: str, tax_index: dict, purchase_index: dict) -> tuple[dict, dict]:
    """road 短型号码 → 车船税/购置税 full 型号码匹配（前缀/精确双向）。

    road 型号码如 'CA6471' 是 车船税 full code 'CA6471B6PHEVD' 的前缀。
    优先精确 → 然后 full.startswith(road) → road.startswith(full)。
    返回 (tax_rec, purchase_rec)，未命中为空 dict。
    """
    tax_rec, pur_rec = {}, {}
    if model_code in tax_index:
        tax_rec = tax_index[model_code]
    else:
        for k, v in tax_index.items():
            if k.startswith(model_code) or model_code.startswith(k):
                tax_rec = v
                break
    if model_code in purchase_index:
        pur_rec = purchase_index[model_code]
    else:
        for k, v in purchase_index.items():
            if k.startswith(model_code) or model_code.startswith(k):
                pur_rec = v
                break
    return tax_rec, pur_rec


def build_eidc_record(source_record: dict, tax_rec: dict | None = None,
                      purchase_rec: dict | None = None) -> dict:
    """把 EIDC source record 构建为与 build_record 同构的标准记录。

    EIDC source contract（eidc_parser 产出）：
      manufacturer_raw/brand_raw/product_name_raw/model_code_raw（fresh）
    只做领域字段解释；model_code 非法 → model_code_valid=false，不生成主键。

    tax_rec / purchase_rec 提供深度参数合并（来自车船税/购置税 regulatory 附件）：
      - common_name / energy_type（由 § 节名推断）
      - ev_range / curb_weight / battery_capacity / battery_mass
    dimensions/wheelbase/motor_power/电池供应商 不在 tax/purchase 附件中，保持空
    （这些字段未来可由 Gov 详情页 EIDC detail 富集，本批 source 层无法提供）。
    """
    raw_model = source_record.get("model_code_raw") or source_record.get("model_code") or ""
    model_code, model_valid = normalize_model_code(raw_model)
    brand = (source_record.get("brand_raw") or source_record.get("brand") or "").replace("牌", "").strip()
    manufacturer = source_record.get("manufacturer_raw") or source_record.get("enterprise_name") or ""
    product_name = source_record.get("product_name_raw") or source_record.get("product_name") or ""

    r = {
        "品牌": brand,
        "企业名称": manufacturer,
        "产品型号": model_code,
        "产品名称": product_name,
        "model_code_valid": model_valid,
        "record_quality": "high" if model_valid else "invalid",
    }

    # ── Vehicle type classification（derived dimension, not identity） ──
    src_type = source_record.get("vehicle_type_raw") or source_record.get("product_name_raw") or product_name or ""
    catalog_no = source_record.get("catalog_no_raw") or ""
    r["source_vehicle_type"] = src_type
    r["catalog_no"] = catalog_no
    vcat, vsub = classify_vehicle_type(src_type, catalog_no)
    r["vehicle_category"] = vcat
    r["vehicle_subcategory"] = vsub
    r["analysis_scope"] = resolve_analysis_scope(vcat)

    tax_rec = tax_rec or {}
    purchase_rec = purchase_rec or {}

    # 通用名称：车船税通用名称 > 购置税通用名称 > 产品名兜底
    common_name = ""
    if tax_rec.get("通用名称"):
        common_name = tax_rec["通用名称"].split(",")[0].strip()
    elif purchase_rec.get("通用名称"):
        common_name = purchase_rec["通用名称"].split(",")[0].strip()
    r["common_name"] = common_name

    # 动力形式：由 tax/purchase section 名推断
    tax_sec = tax_rec.get("_tax_section", "")
    pur_sec = purchase_rec.get("_purchase_section", "")
    energy_type = ""
    if "纯电动" in (tax_sec + pur_sec):
        energy_type = "纯电动"
    elif "燃料电池" in (tax_sec + pur_sec):
        energy_type = "燃料电池"
    elif "插电式混合动力" in (tax_sec + pur_sec):
        energy_type = "插电式混合动力"
    elif product_name:
        # road 附件 Product Name 也可推断
        if "纯电动" in product_name and "混合" not in product_name:
            energy_type = "纯电动"
        elif "增程" in product_name:
            energy_type = "插电式增程混合动力"
        elif "混合" in product_name:
            energy_type = "插电式混合动力"
        elif "燃料电池" in product_name:
            energy_type = "燃料电池"
    r["energy_type"] = energy_type

    # 续航 / 整备 / 电池容量 / 电池质量（tax 优先，purchase 兜底）
    range_val = (tax_rec.get("纯电动续驶里程_km") or purchase_rec.get("纯电动续驶里程_km") or "")
    curb_val = (tax_rec.get("整车整备质量_kg") or purchase_rec.get("整车整备质量_kg") or "")
    cap_val = (tax_rec.get("动力蓄电池总能量_kWh") or tax_rec.get("动力蓄电池组总能量_kWh")
               or purchase_rec.get("动力蓄电池组总能量_kWh") or "")
    mass_val = (tax_rec.get("动力蓄电池总质量_kg") or tax_rec.get("动力蓄电池组总质量_kg")
                or purchase_rec.get("动力蓄电池组总质量_kg") or "")
    r["ev_range_km"] = range_val
    r["ev_range_num"] = parse_num(range_val)
    r["curb_weight_kg"] = curb_val
    r["curb_weight_num"] = parse_num(curb_val)
    r["battery_capacity_kwh"] = cap_val
    r["battery_capacity_num"] = parse_num(cap_val)
    r["battery_mass_kg"] = mass_val
    r["battery_mass_num"] = parse_num(mass_val)

    # match flag：只判 join 是否命中,与字段填充解耦
    # vehicle_tax_match_flag / purchase_tax_match_flag 独立标记 regulatory 附件 join 结果
    r["vehicle_tax_match_flag"] = "1" if tax_rec else "0"
    r["purchase_tax_match_flag"] = "1" if purchase_rec else "0"

    # metric_scope：基于是否有任何参数合并（不依赖 match flag 单独判）
    has_params = bool(range_val or curb_val or cap_val or mass_val)
    if has_params:
        # compute derived metrics (single-configuration first-value)
        bat_energy = r["battery_capacity_num"]
        bat_mass = r["battery_mass_num"]
        elec_range = r["ev_range_num"]
        curb_weight = r["curb_weight_num"]
        _bat_mass_lo = bat_mass
        _bat_mass_hi = bat_mass
        r["_bat_mass_lo"] = _bat_mass_lo
        r["_bat_mass_hi"] = _bat_mass_hi
        _compute_derived(r, bat_energy, bat_mass, elec_range, curb_weight)
        r["metric_scope"] = "全数据"
    else:
        if energy_type == "纯电动":
            r["metric_scope"] = "数据缺失"
        elif energy_type:
            r["metric_scope"] = (f"非纯电车型"
                                 f"（tax hit={r['vehicle_tax_match_flag']} pur hit={r['purchase_tax_match_flag']}）")
        else:
            r["metric_scope"] = "数据缺失"
    return r


# ── 衍生指标（就地计算，首值口径）──

def derive_metrics(record: dict) -> None:
    """Compute and set derived metrics on a built record（就地修改）。

    从 record 自身的 `_*_num` 中间量读取首值计算，多配置车型只反映首配置。
    """
    _compute_derived(
        record,
        record.get("_bat_energy_num"),
        record.get("_bat_mass_num"),
        record.get("_range_num"),
        record.get("_curb_num"),
    )


def _fmt_range(lo: float, hi: float, decimals: int = 1) -> str:
    """Format a range like '163.0~173.1'. If lo == hi, return single value."""
    if abs(hi - lo) < 0.01:
        return str(round(lo, decimals))
    return f"{round(lo, decimals)}~{round(hi, decimals)}"


def _compute_derived(r: dict, bat_energy: float | None, bat_mass: float | None,
                     elec_range: float | None, curb_weight: float | None):
    """Compute and set derived metrics on record r."""
    bat_mass_lo = r.get("_bat_mass_lo") or bat_mass
    bat_mass_hi = r.get("_bat_mass_hi") or bat_mass
    has_tolerance = bat_mass_lo is not None and bat_mass_hi is not None and abs(bat_mass_hi - bat_mass_lo) > 0.01

    ed = None
    if bat_energy and elec_range and elec_range > 0:
        ed = round(bat_energy / elec_range * 100, 1)
    r["总电量口径近似电耗(kWh/100km)"] = ed if ed is not None else ""

    if bat_energy and bat_mass_lo and bat_mass_hi and bat_mass_lo > 0:
        ed_lo = round(bat_energy / bat_mass_hi * 1000, 1)
        ed_hi = round(bat_energy / bat_mass_lo * 1000, 1)
        r["电池包能量密度(Wh/kg)"] = _fmt_range(ed_lo, ed_hi)
    else:
        r["电池包能量密度(Wh/kg)"] = ""

    km_per_kwh = None
    if bat_energy and elec_range and bat_energy > 0:
        km_per_kwh = round(elec_range / bat_energy, 2)
    r["单位电量续航(km/kWh)"] = km_per_kwh if km_per_kwh is not None else ""

    if bat_mass_lo and bat_mass_hi and curb_weight and curb_weight > 0:
        mr_lo = round(bat_mass_lo / curb_weight * 100, 1)
        mr_hi = round(bat_mass_hi / curb_weight * 100, 1)
        r["电池质量占整备质量比(%)"] = _fmt_range(mr_lo, mr_hi)
    else:
        r["电池质量占整备质量比(%)"] = ""


# ── 多配置展开（宽表用）──

def _split_variant_values(values: list[str]) -> list[list[float | None]]:
    """Parse multi-value fields (e.g. '380/375') and align variants."""
    parsed = []
    max_parts = 1
    for v in values:
        if not v or not v.strip():
            parsed.append([None])
            continue
        v = v.strip()
        parts = [p.strip() for p in v.split("/")]
        nums = []
        for p in parts:
            p = p.split("±")[0].split("（")[0].split("(")[0].strip()
            try:
                nums.append(float(p))
            except ValueError:
                nums.append(None)
        if not nums:
            nums = [None]
        parsed.append(nums)
        max_parts = max(max_parts, len(nums))

    variants = []
    for i in range(max_parts):
        variant = []
        for nums in parsed:
            if i < len(nums):
                variant.append(nums[i])
            else:
                variant.append(nums[0] if nums else None)
        variants.append(variant)
    return variants


def explode_variants(records: list[dict]) -> tuple[list[dict], set[str]]:
    """Expand records with multi-value fields (range/curb weight) into variants.

    Returns (expanded_records, original_model_ids).
    Fields split: 电池容量(kWh), 电池质量(kg), 纯电续航(km), 整备质量(kg)
    Derived metrics re-computed per variant.
    """
    original_ids: set[str] = set()
    expanded = []
    for r in records:
        original_ids.add(r.get("产品型号", ""))
        raw_range = r.get("电池容量(kWh)", "")
        raw_mass = r.get("电池质量(kg)", "")
        raw_elec = r.get("纯电续航(km)", "")
        raw_curb = r.get("整备质量(kg)", "")

        has_multi = any("/" in v for v in [raw_range, raw_mass, raw_elec, raw_curb] if v)

        if not has_multi:
            be = r.get("_bat_energy_num")
            bm = r.get("_bat_mass_num")
            er = r.get("_range_num")
            cw = r.get("_curb_num")
            _compute_derived(r, be, bm, er, cw)
            expanded.append(r)
        else:
            variants = _split_variant_values([raw_range, raw_mass, raw_elec, raw_curb])
            for i, (be_val, bm_val, er_val, cw_val) in enumerate(variants):
                vr = dict(r)
                tag = f"#{i+1}" if len(variants) > 1 else ""
                if tag:
                    vr["产品型号"] = r["产品型号"] + tag
                vr["电池容量(kWh)"] = str(be_val) if be_val is not None else r.get("电池容量(kWh)", "")
                vr["电池质量(kg)"] = str(bm_val) if bm_val is not None else r.get("电池质量(kg)", "")
                vr["纯电续航(km)"] = str(er_val) if er_val is not None else r.get("纯电续航(km)", "")
                vr["整备质量(kg)"] = str(cw_val) if cw_val is not None else r.get("整备质量(kg)", "")
                _compute_derived(vr, be_val, bm_val, er_val, cw_val)
                expanded.append(vr)
    return expanded, original_ids


def _dedup_by_model(records: list[dict]) -> list[dict]:
    """Deduplicate expanded records: keep first row per original model_id (strip #1/#2)."""
    seen: set[str] = set()
    deduped = []
    for r in records:
        mid = r.get("产品型号", "").split("#")[0]
        if mid not in seen:
            seen.add(mid)
            deduped.append(r)
    return deduped


def supplier_summary(records: list[dict], by_model: bool = True, by_group: bool = False) -> str:
    """Generate supplier installation structure summary."""
    from collections import Counter
    if by_model:
        recs = _dedup_by_model(records)
        label = "车型"
    else:
        recs = records
        label = "配置"
    suppliers = Counter()
    for r in recs:
        if by_group:
            s = r.get("cell_supplier_group", "")
        else:
            s = r.get("电芯/总成供应商", "")
        if s:
            suppliers[s] += 1
    if not suppliers:
        return "无数据"
    lines = [f"(统计口径: {len(recs)} 个原始{label})"]
    for s, cnt in suppliers.most_common():
        lines.append(f"  - {s}: {cnt}款")
    return "\n".join(lines)
