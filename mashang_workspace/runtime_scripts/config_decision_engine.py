#!/usr/bin/env python
"""
config_decision_engine.py — 通用配置判定引擎

把"判定哪些订单付费选装了某配置"抽象为可复用的四步流水线：

    Step 1  聚合订单级配置事实（去重、合并同一订单的多行配置记录）
    Step 2  根据车型权益规则判定该配置在该车型/时间下属于标配/免费可选/付费选装
    Step 3  结合价格证据输出订单状态（6 类状态 + 选择/付费双确定性 + 不确定原因）
    Step 4  产出批次业务指标（选装率/付费率）与数据质量指标（价格记录完整率/缺失率）

用法:
    python runtime_scripts/config_decision_engine.py --series LS9 --option suede_interior --format json
    python runtime_scripts/config_decision_engine.py --series LS9 --option suede_interior --format json --output outputs/tables/

核心输出（订单级）:
    selection_status / commercial_status / selection_certainty / payment_certainty /
    entitlement_type / observed_positive_prices / uncertainty_flag / uncertainty_reason

6 类商业状态:
    STANDARD_CONFIRMED   确定为标配（如 Hyper 麂皮）
    PAID_CONFIRMED       确定为付费选装（存在可信 price>0）
    PAID_INFERRED        按产品规则应付费、但价格证据缺失
    FREE_OPTION_CONFIRMED 确定选择但为免费可选（非标配非付费）
    NOT_SELECTED_CONFIRMED 确定未选目标配置（存在互斥配置值正面证据；用户实际选择了其他内饰）
    UNRESOLVED           无法确定（含 CONFLICTING_VALUES / MISSING_CONFIG_RECORD / UNKNOWN_MODEL_RULE 等原因）
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
_WS_ROOT = Path(__file__).resolve().parents[1]
if str(_WS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WS_ROOT))

import pandas as pd
from utils.result_contract import build_success_contract

ORDER_PARQUET = REPO_ROOT / "dataset" / "order_data.parquet"
CONFIG_PARQUET = REPO_ROOT / "dataset" / "config_attribute.parquet"

# ── 状态与原因常量 ──
STANDARD_CONFIRMED = "STANDARD_CONFIRMED"
PAID_CONFIRMED = "PAID_CONFIRMED"
PAID_INFERRED = "PAID_INFERRED"
FREE_OPTION_CONFIRMED = "FREE_OPTION_CONFIRMED"
NOT_SELECTED_CONFIRMED = "NOT_SELECTED_CONFIRMED"
UNRESOLVED = "UNRESOLVED"
ALL_STATUSES = [STANDARD_CONFIRMED, PAID_CONFIRMED, PAID_INFERRED,
                FREE_OPTION_CONFIRMED, NOT_SELECTED_CONFIRMED, UNRESOLVED]

MISSING_CONFIG_RECORD = "MISSING_CONFIG_RECORD"
CONFLICTING_VALUES = "CONFLICTING_VALUES"
UNKNOWN_OPTION_VALUE = "UNKNOWN_OPTION_VALUE"
UNKNOWN_MODEL_RULE = "UNKNOWN_MODEL_RULE"
POLICY_DATE_AMBIGUOUS = "POLICY_DATE_AMBIGUOUS"
MISSING_PRICE_EVIDENCE = "MISSING_PRICE_EVIDENCE"
PRICE_RULE_CONFLICT = "PRICE_RULE_CONFLICT"
MULTIPLE_POSITIVE_PRICES = "MULTIPLE_POSITIVE_PRICES"
MODEL_MAPPING_AMBIGUOUS = "MODEL_MAPPING_AMBIGUOUS"


def _read_snapshot_csv(path):
    """读取年度配置快照 CSV（2026=UTF-8 逗号分隔；旧年份=UTF-16 制表符分隔）。"""
    for enc, sep in [("utf-8", ","), ("utf-16", "\t"), ("utf-16", ",")]:
        try:
            df = pd.read_csv(path, sep=sep, encoding=enc, low_memory=False)
            if df.shape[1] >= 3:
                return df
        except Exception:
            continue
    return None


class YearlySnapshotResolver:
    """按"最晚年度快照"消解互斥冲突：同一订单在不同年份快照中值不一致时，取最新年份的值。

    数据无逐条时间戳，但 config_attribute.parquet 由多份年度快照拼接；
    将快照年份视为记录时间，最新年份快照为权威值。
    """

    # (年份, 文件名)：旧下划线命名已废弃，改用带 Value(code) 列的新快照
    SNAPSHOT_FILES = [
        ("2026", "config_attribute_data2026.csv"),
        ("2025", "config_attribute_data2025.csv"),
        ("2024", "config_attribute_data2024.csv"),
        ("2023", "config_attribute_data.csv"),
    ]

    def __init__(self, data_dir, option_config, snapshot_files=None):
        self.data_dir = Path(data_dir)
        self.attribute = option_config["attribute"]
        self.target_values = set(option_config["target_values"])
        self.snapshot_files = snapshot_files or self.SNAPSHOT_FILES
        self._latest = None

    def _load(self):
        if self._latest is not None:
            return
        self._latest = {}
        for year, fname in self.snapshot_files:
            f = self.data_dir / fname
            if not f.exists():
                continue
            df = _read_snapshot_csv(f)
            if df is None:
                continue
            try:
                oc = next(c for c in df.columns if "order" in c.lower())
                ac = next(c for c in df.columns if "attribute" in c.lower() and "name" in c.lower())
                vc = next(c for c in df.columns if "value" in c.lower() and "display" in c.lower())
            except StopIteration:
                continue
            sub = df[(df[ac].astype(str) == self.attribute) & (df[vc].astype(str).isin(self.target_values))]
            yr = int(year)
            for onum, g in sub.groupby(oc):
                key = str(onum)
                vals = set(g[vc].astype(str))
                if key not in self._latest or yr > self._latest[key][0]:
                    self._latest[key] = (yr, vals)

    def resolve(self, order_number):
        """返回该订单在最新快照中的目标配置值集合；无记录返回 None。"""
        self._load()
        entry = self._latest.get(str(order_number))
        return entry[1] if entry else None


# ── 选项配置（声明式，可 JSON 序列化，便于复用） ──

def _match_group(product_name, matchers):
    """按声明式 matchers 把 product_name 映射到 model_group；None 表示无法映射。"""
    for m in matchers:
        if m.get("contains") and m["contains"] in product_name:
            return m["group"]
        if m.get("equals") and m["equals"] == product_name:
            return m["group"]
        if m.get("startswith") and product_name.startswith(m["startswith"]):
            return m["group"]
    return None


SUEDE_OPTION_CONFIG = {
    "option": "suede_interior",
    "attribute": "内饰",
    "label": "麂皮/橙黑内饰",
    # 归并口径: 目标配置用 value_code 统一（橙黑+大地橘 = IN2-ASF 同一配置）
    "target_codes": {
        "IN1-ASH": "深色麂皮",
        "IN1-AMA": "浅色麂皮",
        "IN2-ASF": "橙黑/大地橘",
    },
    "target_values": ["深色麂皮", "浅色麂皮", "橙黑/大地橘"],
    "expected_price": 5000,
    "model_matchers": [
        {"group": "hyper", "contains": "Hyper"},
        {"group": "wire", "contains": "线控版"},
        {"group": "ultra", "contains": "Ultra"},
        {"group": "base", "equals": "智己LS9"},
    ],
    # 每个 model_group 的权益规则；overrides 按归并后的配置名覆盖默认权益
    "model_rules": {
        "hyper": {"default": "STANDARD", "overrides": {}},
        "wire": {"default": "PAID", "overrides": {"橙黑/大地橘": "FREE_OPTION"}},
        "ultra": {"default": "PAID", "overrides": {}},
        "base": {"default": "PAID", "overrides": {}},
    },
    # 车型上市可用性（业务判断）：某时间窗口内哪些车型在售，窗口外锁单的车型剔除
    "model_availability": [
        {"start": "2025-11-12", "end": "2026-07-16", "model_groups": ["ultra"]},
        {"start": "2026-07-16", "end": None, "model_groups": ["hyper", "ultra", "wire"]},
    ],
}


# ── Step 1: 订单级配置事实聚合 ──

@dataclass
class OrderConfigFact:
    order_number: str = ""
    model_version: str = ""
    model_group: str = ""
    lock_date: str = ""
    raw_option_values: list = field(default_factory=list)      # 出现的全部目标值（去重后）
    raw_values: list = field(default_factory=list)             # 出现的全部内饰值（去重后）
    positive_prices: list = field(default_factory=list)        # 该订单全部正价格记录
    value_prices: dict = field(default_factory=dict)           # value -> 该值全部价格列表
    has_config_record: bool = False


def _build_code_label_map(config_df, attribute):
    """按 value_code 建立该属性的规范配置名（同 code 多显示名取最常出现者）。"""
    if "value_code" not in config_df.columns:
        return {}
    sub = config_df[(config_df["Attribute"] == attribute) & (config_df["value_code"].notna())].copy()
    if not len(sub):
        return {}
    sub["value_code"] = sub["value_code"].astype(str).str.strip()
    sub["value"] = sub["value"].astype(str).str.strip()
    sub = sub[sub["value_code"].ne("") & sub["value"].ne("")]
    if not len(sub):
        return {}
    return sub.groupby("value_code")["value"].agg(lambda s: s.value_counts().idxmax()).to_dict()


def aggregate_config_facts(orders_df, config_df, option_config):
    """Step 1: 以唯一锁单订单为粒度聚合配置事实。

    按 value_code 归并配置：同一 (Attribute, value_code) 的多个显示名视为同一配置，
    统一为规范名（目标配置用业务 label，其余取数据中最常出现者）。
    """
    target_values = set(option_config["target_values"])
    code_labels = _build_code_label_map(config_df, option_config["attribute"])
    for code, biz in (option_config.get("target_codes") or {}).items():
        code_labels[code] = biz  # 目标配置用稳定业务名

    facts = {}
    for _, o in orders_df.iterrows():
        f = OrderConfigFact(
            order_number=o["order_number"],
            model_version=o.get("product_name", ""),
            model_group=_match_group(str(o.get("product_name", "")), option_config["model_matchers"]),
            lock_date=str(o.get("lock_time"))[:10],
            has_config_record=False,
        )
        facts[o["order_number"]] = f

    grouped = config_df.groupby("Order Number")
    for onum, g in grouped:
        if onum not in facts:
            continue
        f = facts[onum]
        f.has_config_record = True
        norm = {}  # 归并后配置名 -> 价格列表
        for _, row in g.iterrows():
            v = str(row["value"])
            code = row.get("value_code")
            if code is None or pd.isna(code) or str(code).strip().lower() in ("nan", "<na>", "", "none"):
                label = v
            else:
                label = code_labels.get(str(code).strip(), v)
            p = row.get("price")
            norm.setdefault(label, []).append(0 if pd.isna(p) else p)
        f.raw_values = sorted(norm.keys())
        f.raw_option_values = sorted(set(norm) & target_values)
        f.value_prices = {k: sorted(set(v)) for k, v in norm.items()}
        f.positive_prices = sorted({p for ps in f.value_prices.values() for p in ps if p > 0})
    return facts


# ── Step 2 + Step 3: 权益规则 + 状态判定 ──

def _entitlement_for(option_config, model_group, value):
    rules = option_config["model_rules"].get(model_group)
    if not rules:
        return None
    default = rules.get("default", "PAID")
    return rules.get("overrides", {}).get(value, default)


def determine_status(fact, option_config, conflict_resolver=None):
    """Step 2+3: 输出订单级判定结果。conflict_resolver 可选，用于消解互斥冲突（取最新快照值）。"""
    target_values = set(option_config["target_values"])
    result = {
        "order_number": fact.order_number,
        "model_version": fact.model_version,
        "model_group": fact.model_group,
        "lock_date": fact.lock_date,
        "option": option_config["option"],
        "raw_option_values": fact.raw_option_values,
        "raw_values": fact.raw_values,
        "selected_flag": bool(fact.raw_option_values),
        "entitlement_type": None,
        "expected_price": option_config.get("expected_price", 0),
        "observed_positive_prices": fact.positive_prices,
        "commercial_status": None,
        "selection_certainty": None,
        "payment_certainty": None,
        "uncertainty_flag": False,
        "uncertainty_reason": None,
        "evidence_summary": "",
    }

    # 1) 无任何内饰配置记录 → 无法判断
    if not fact.has_config_record:
        result.update(
            commercial_status=UNRESOLVED, selection_certainty="UNRESOLVED",
            payment_certainty="UNRESOLVED", uncertainty_flag=True,
            uncertainty_reason=MISSING_CONFIG_RECORD,
            evidence_summary="订单无内饰配置记录",
        )
        return result

    # 2) 未出现目标配置值
    if not fact.raw_option_values:
        if fact.raw_values:
            result.update(
                commercial_status=NOT_SELECTED_CONFIRMED, selection_certainty="CONFIRMED",
                payment_certainty="N/A",
                evidence_summary=f"存在互斥内饰值 {', '.join(fact.raw_values[:3])}，未选目标配置",
            )
        else:
            result.update(
                commercial_status=UNRESOLVED, selection_certainty="UNRESOLVED",
                payment_certainty="UNRESOLVED", uncertainty_flag=True,
                uncertainty_reason=UNKNOWN_OPTION_VALUE,
                evidence_summary="配置记录存在但无可用值",
            )
        return result

    # 3) 出现目标配置值
    # 3a) 同一订单多个互斥目标值 → 尝试按最新快照消解，否则判为冲突
    if len(fact.raw_option_values) > 1:
        resolved = None
        if conflict_resolver is not None:
            try:
                resolved = conflict_resolver(fact.order_number)
            except Exception:
                resolved = None
        if resolved and len(resolved) == 1:
            single = next(iter(resolved))
            if single in target_values:
                from dataclasses import replace
                return determine_status(replace(fact, raw_option_values=[single]), option_config,
                                        conflict_resolver=conflict_resolver)
        has_price = bool(fact.positive_prices)
        result.update(
            commercial_status=UNRESOLVED, selection_certainty="UNRESOLVED",
            payment_certainty="CONFIRMED" if has_price else "UNRESOLVED",
            uncertainty_flag=True, uncertainty_reason=CONFLICTING_VALUES,
            evidence_summary=f"同一订单出现互斥目标值 {', '.join(fact.raw_option_values)}",
        )
        if len(set(fact.positive_prices)) > 1:
            result["uncertainty_reason"] = CONFLICTING_VALUES
        return result

    value = fact.raw_option_values[0]
    model_group = fact.model_group
    if model_group is None:
        result.update(
            commercial_status=UNRESOLVED, selection_certainty="UNRESOLVED",
            payment_certainty="UNRESOLVED", uncertainty_flag=True,
            uncertainty_reason=MODEL_MAPPING_AMBIGUOUS,
            evidence_summary=f"车型无法映射到权益规则：{fact.model_version}",
        )
        return result

    entitlement = _entitlement_for(option_config, model_group, value)
    result["entitlement_type"] = entitlement
    if entitlement is None:
        result.update(
            commercial_status=UNRESOLVED, selection_certainty="CONFIRMED",
            payment_certainty="UNRESOLVED", uncertainty_flag=True,
            uncertainty_reason=UNKNOWN_MODEL_RULE,
            evidence_summary=f"缺少车型 {model_group} 的权益规则",
        )
        return result

    # 多正价格冲突检测（同一值出现多个不同正价格）
    val_prices = fact.value_prices.get(value, [])
    distinct_pos = sorted({p for p in val_prices if p > 0})
    if len(distinct_pos) > 1:
        result["evidence_summary"] = f"同一配置出现多个正价格 {distinct_pos}"

    if entitlement == "STANDARD":
        result.update(
            commercial_status=STANDARD_CONFIRMED, selection_certainty="CONFIRMED",
            payment_certainty="N/A",
            evidence_summary=f"{model_group} 车型权益将该配置标为标配",
        )
    elif entitlement == "FREE_OPTION":
        result.update(
            commercial_status=FREE_OPTION_CONFIRMED, selection_certainty="CONFIRMED",
            payment_certainty="N/A",
            evidence_summary=f"{model_group} 车型权益将该配置标为免费可选",
        )
    else:  # PAID
        if distinct_pos:
            result.update(
                commercial_status=PAID_CONFIRMED, selection_certainty="CONFIRMED",
                payment_certainty="CONFIRMED",
                evidence_summary=f"存在正价格证据 {distinct_pos}，判定付费",
            )
            if len(distinct_pos) > 1:
                result["uncertainty_flag"] = True
                result["uncertainty_reason"] = MULTIPLE_POSITIVE_PRICES
        else:
            result.update(
                commercial_status=PAID_INFERRED, selection_certainty="CONFIRMED",
                payment_certainty="INFERRED", uncertainty_flag=True,
                uncertainty_reason=MISSING_PRICE_EVIDENCE,
                evidence_summary=f"产品规则应收费（{model_group}），但价格缺失/为空",
            )
    return result


# ── Step 4: 批次指标 ──

def summarize(results, total_orders):
    counts = {s: 0 for s in ALL_STATUSES}
    unresolved_by_reason = {}
    for r in results:
        counts[r["commercial_status"]] += 1
        if r["commercial_status"] == UNRESOLVED and r["uncertainty_reason"]:
            unresolved_by_reason[r["uncertainty_reason"]] = unresolved_by_reason.get(r["uncertainty_reason"], 0) + 1

    selected = (counts[STANDARD_CONFIRMED] + counts[PAID_CONFIRMED] +
                counts[PAID_INFERRED] + counts[FREE_OPTION_CONFIRMED])
    confirmed = counts[PAID_CONFIRMED]
    inferred = counts[PAID_INFERRED]
    resolved_selection = total_orders - counts[UNRESOLVED]
    denom_paid = confirmed + inferred

    return {
        "total_orders": total_orders,
        "resolved_selection_count": resolved_selection,
        "selection_coverage_rate": round(resolved_selection / total_orders * 100, 1) if total_orders else 0.0,
        "option_selected_count": selected,
        "standard_count": counts[STANDARD_CONFIRMED],
        "paid_confirmed_count": confirmed,
        "paid_inferred_count": inferred,
        "free_option_count": counts[FREE_OPTION_CONFIRMED],
        "not_selected_count": counts[NOT_SELECTED_CONFIRMED],
        "unresolved_count": counts[UNRESOLVED],
        "unresolved_by_reason": unresolved_by_reason,
        "paid_price_completeness_rate": round(confirmed / denom_paid * 100, 1) if denom_paid else None,
        "paid_price_missing_rate": round(inferred / denom_paid * 100, 1) if denom_paid else None,
        "status_counts": counts,
    }


# ── 主流程 ──

def _model_group(option_config, product_name):
    return _match_group(str(product_name), option_config["model_matchers"])


def _model_available(option_config, product_name, lock_time):
    """车型可用性（业务判断）：按锁单时间判断该车型是否在售；不在售的预锁订单剔除。"""
    group = _model_group(option_config, product_name)
    if group is None:
        return True
    rules = option_config.get("model_availability") or []
    lt = pd.Timestamp(lock_time)
    for rule in rules:
        start = pd.Timestamp(rule["start"]) if rule.get("start") else None
        end = pd.Timestamp(rule["end"]) if rule.get("end") else None
        if (start is None or lt >= start) and (end is None or lt < end):
            return group in rule["model_groups"]
    return True


def run(orders_df, config_df, option_config, order_type="用户车", date_from=None, conflict_resolver=None,
        require_vin=False):
    """执行四步流水线，返回 (results, metrics)。orders_df 应已过滤到目标订单。

    conflict_resolver: 可选 callable(order_number)->set；用于消解互斥冲突（如按最新年度快照取值）。
    require_vin: 可选附加基础筛选，仅统计 vin 非空订单（默认关闭）。
    业务筛选：若 option_config 配置 model_availability，按锁单时间过滤在售车型。
    """
    orders_df = orders_df[orders_df["order_number"].notna()].copy()
    if require_vin and "vin" in orders_df.columns:
        orders_df = orders_df[orders_df["vin"].notna()]
    if order_type:
        orders_df = orders_df[orders_df.get("order_type", "") == order_type]
    if date_from is not None:
        orders_df = orders_df[orders_df["lock_time"] >= pd.Timestamp(date_from)]
    if option_config.get("model_availability") and "product_name" in orders_df.columns:
        orders_df = orders_df[
            orders_df.apply(lambda r: _model_available(option_config, r["product_name"], r["lock_time"]), axis=1)
        ]
    orders_df = orders_df.drop_duplicates(subset=["order_number"])

    cfg_df = config_df[config_df["Attribute"] == option_config["attribute"]].copy()
    cfg_df["price"] = pd.to_numeric(cfg_df.get("price"), errors="coerce").fillna(0)

    facts = aggregate_config_facts(orders_df, cfg_df, option_config)
    results = [determine_status(facts[o], option_config, conflict_resolver=conflict_resolver)
               for o in orders_df["order_number"]]
    metrics = summarize(results, len(results))
    return results, metrics


def load_option_config(option):
    if option == "suede_interior":
        return SUEDE_OPTION_CONFIG
    raise ValueError(f"未知选项配置: {option}")


def parse_args():
    p = argparse.ArgumentParser(description="通用配置判定引擎")
    p.add_argument("--series", type=str, default="LS9", help="车系过滤")
    p.add_argument("--option", type=str, default="suede_interior", help="选项配置名")
    p.add_argument("--order-type", type=str, default="用户车", help="订单类型过滤")
    p.add_argument("--date-from", type=str, default=None, help="起始锁单日期（含）")
    p.add_argument("--resolve-conflicts", action="store_true", help="互斥冲突按最新年度快照取值消解")
    p.add_argument("--require-vin", action="store_true", help="附加筛选：仅统计 vin 非空订单（默认关闭）")
    p.add_argument("--format", type=str, default="terminal", choices=["terminal", "json"])
    p.add_argument("--output", type=str, help="输出目录")
    p.add_argument("--limit", type=int, default=20, help="终端展示 UNRESOLVED 明细行数")
    return p.parse_args()


def main():
    args = parse_args()
    option_config = load_option_config(args.option)

    order = pd.read_parquet(str(ORDER_PARQUET))
    order["lock_time"] = pd.to_datetime(order["lock_time"], errors="coerce")
    orders_df = order[order["series"] == args.series] if args.series else order
    config_df = pd.read_parquet(str(CONFIG_PARQUET))

    resolver = None
    if args.resolve_conflicts:
        resolver = YearlySnapshotResolver(REPO_ROOT / "dataset", option_config).resolve

    results, metrics = run(orders_df, config_df, option_config,
                           order_type=args.order_type, date_from=args.date_from,
                           conflict_resolver=resolver, require_vin=args.require_vin)

    scope = {
        "data_source": f"{ORDER_PARQUET.name} ⋈ {CONFIG_PARQUET.name}",
        "time_window": {"start_date": args.date_from or "as-is", "type": "config"},
        "filters": {"series": args.series, "order_type": args.order_type, "option": args.option,
                    "model_availability": "按上市窗口过滤在售车型", "require_vin": args.require_vin},
        "metric_definition": (
            f"{option_config['label']} 配置判定：6 类商业状态（STANDARD_CONFIRMED/PAID_CONFIRMED/"
            f"PAID_INFERRED/FREE_OPTION_CONFIRMED/NOT_SELECTED_CONFIRMED/UNRESOLVED）；"
            f"业务筛选：按上市窗口过滤在售车型（LS9 上市后仅 52/66 Ultra；LS9Hyper 上市后含 Hyper/线控版）；"
            f"确认付费=有正价格证据；推定付费=产品规则应付费但价格缺失；"
            f"价格记录完整率=确认付费/(确认付费+推定付费)"
        ),
    }
    result = {
        "summary": (
            f"{option_config['label']}判定：{metrics['total_orders']} 单中可判定 {metrics['resolved_selection_count']} 单"
            f"（覆盖率 {metrics['selection_coverage_rate']}%）；确认付费 {metrics['paid_confirmed_count']}、"
            f"推定付费 {metrics['paid_inferred_count']}、标配 {metrics['standard_count']}、"
            f"免费可选 {metrics['free_option_count']}、未选 {metrics['not_selected_count']}、"
            f"无法判断 {metrics['unresolved_count']}。价格记录完整率 {metrics['paid_price_completeness_rate']}%。"
        ),
        "metrics": {
            "total_orders": metrics["total_orders"],
            "selection_coverage_rate_pct": metrics["selection_coverage_rate"],
            "paid_confirmed_count": metrics["paid_confirmed_count"],
            "paid_inferred_count": metrics["paid_inferred_count"],
            "standard_count": metrics["standard_count"],
            "free_option_count": metrics["free_option_count"],
            "not_selected_count": metrics["not_selected_count"],
            "unresolved_count": metrics["unresolved_count"],
            "paid_price_completeness_rate_pct": metrics["paid_price_completeness_rate"],
        },
        "dimensions": [{
            "name": "commercial_status",
            "items": [{"value": s, "metrics": {"count": c}} for s, c in metrics["status_counts"].items()],
        }],
    }

    contract = build_success_contract(
        script="runtime_scripts/config_decision_engine.py",
        command="python " + " ".join(sys.argv),
        scope=scope, result=result,
        followup_context={
            "metric": "config_decision", "option": args.option, "series": args.series,
            "available_dimensions": ["commercial_status", "model_group", "uncertainty_reason"],
        },
    )

    if args.format == "json":
        print(json.dumps(contract, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({
            "summary": result["summary"],
            "metrics": metrics,
            "unresolved_reasons": metrics["unresolved_by_reason"],
            "sample_unresolved": [r for r in results if r["commercial_status"] == UNRESOLVED][:args.limit],
        }, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
