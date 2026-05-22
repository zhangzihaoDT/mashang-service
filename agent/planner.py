import json
import datetime
import re

from openai import OpenAI
from agent.llm_config import DEEPSEEK_PLANNER_MODEL
from agent.runtime_decision import evaluate_state_readiness
from agent.state import AgentState
from schema import MetricRegistry
from operators.time_windows import (
    parse_time_window,
    parse_time_window_with_business,
    parse_comparison_type,
    infer_time_window_type,
    infer_goal_time_window_rule,
    infer_goal_time_window as _ts_infer_goal_time_window,
    remove_cumulative_time_dim,
    is_cumulative_query,
    contains_relative_to_today_hint,
    cumulative_adjust_time,
    parse_until_end_date,
    extract_compare_year,
)
from tools.config_cross_analysis_templates import TEMPLATE_CATALOG_MD, build_plan as template_build_plan, match as match_template

LOOP_RUNTIME_SYSTEM_PROMPT = """
你是一个数据分析 Agent Loop 调度器。
你需要根据目标与历史执行结果，决定下一步动作，并且必须输出 JSON。

输出格式:
{
  "action": "run_dsl 或 finish",
  "reason": "为什么这样决策",
  "query": "下一步要执行的自然语言查询（action=run_dsl 时必填）",
  "analysis": "你对当前进展的理解"
}

规则:
1. 如果信息还不足以回答用户目标，输出 run_dsl。
2. 如果信息已足够，输出 finish。
3. 最多执行 5 步，避免重复查询。
4. query 必须具体，且与目标直接相关。
5. 不允许输出除 JSON 以外的文本。
6. 若需要拆分时间区间多次查询，必须从历史 DSL 中读取实际查询窗口（filters/time），并确保窗口按 [start, end)（左闭右开）无重叠、无漏数：下一段 start 应等于上一段 end。
"""


PLANNING_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "create_planning_dsl",
        "description": "将自然语言问题转为规划 DSL（可拆解为多个子问题对应多个 plan）。",
        "parameters": {
            "type": "object",
            "properties": {
                "plans": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string"},
                            "dataset": {"type": "string"},
                            "metric": {
                                "type": "object",
                                "properties": {
                                    "field": {"type": "string"},
                                    "agg": {"type": "string", "enum": ["sum", "mean", "count", "min", "max"]},
                                    "alias": {"type": "string"},
                                    "business_name": {"type": "string"},
                                },
                                "required": ["field", "agg"],
                            },
                            "time": {
                                "type": "object",
                                "properties": {
                                    "field": {"type": "string"},
                                    "start": {"type": "string"},
                                    "end": {"type": "string"},
                                },
                                "required": ["field", "start", "end"],
                            },
                            "dimensions": {"type": "array", "items": {"type": "string"}},
                            "filters": {"type": "array"},
                            "comparison": {
                                "type": "object",
                                "properties": {
                                    "type": {"type": "string", "enum": ["none", "yoy", "wow", "dod"]},
                                },
                                "required": ["type"],
                            },
                            "ranking": {
                                "type": "object",
                                "properties": {
                                    "order": {"type": "string", "enum": ["asc", "desc"]},
                                    "top_k": {"type": "integer"},
                                },
                            },
                            "statistics": {
                                "type": "object",
                                "properties": {
                                    "type": {
                                        "type": "string",
                                        "enum": [
                                            "weekly_decline_ratio",
                                            "daily_threshold_count",
                                            "daily_mean",
                                            "daily_mean_median",
                                            "trend_summary",
                                            "contribution_summary",
                                            "category_share",
                                            "daily_percentile_rank",
                                            "weekend_percentile_rank",
                                            "weekday_percentile_rank",
                                        ],
                                    },
                                    "time_field": {"type": "string"},
                                    "window_weeks": {"type": "integer"},
                                    "window_days": {"type": "integer"},
                                    "window_weekends": {"type": "integer"},
                                    "category_field": {"type": "string"},
                                    "dimension_field": {"type": "string"},
                                    "top_k": {"type": "integer"},
                                    "reference_date": {"type": "string"},
                                    "weekdays": {"type": "array", "items": {"type": "integer"}},
                                    "op": {"type": "string", "enum": [">", ">=", "<", "<=", "==", "!="]},
                                    "threshold": {"type": "number"},
                                    "numerator_metric": {
                                        "type": "object",
                                        "properties": {
                                            "field": {"type": "string"},
                                            "agg": {"type": "string", "enum": ["sum", "mean", "count", "min", "max"]},
                                            "alias": {"type": "string"},
                                        },
                                    },
                                    "denominator_metric": {
                                        "type": "object",
                                        "properties": {
                                            "field": {"type": "string"},
                                            "agg": {"type": "string", "enum": ["sum", "mean", "count", "min", "max"]},
                                            "alias": {"type": "string"},
                                        },
                                    },
                                    "value_metric": {
                                        "type": "object",
                                        "properties": {
                                            "field": {"type": "string"},
                                            "agg": {"type": "string", "enum": ["sum", "mean", "count", "min", "max"]},
                                            "alias": {"type": "string"},
                                        },
                                    },
                                },
                            },
                            "fast_path": {
                                "type": "object",
                                "properties": {
                                    "type": {"type": "string", "enum": ["numeric_ratio", "current_iso_week", "small_talk_contextual"]},
                                    "current": {"type": "number"},
                                    "base": {"type": "number"},
                                },
                            },
                                "analysis_intent": {
                                "type": "object",
                                "properties": {
                                    "type": {"type": "string", "enum": [
                                        "share_breakdown", "attribute_penetration", "attribute_distribution",
                                        "active_store", "retained_intention", "retained_intention_conversion",
                                        "age_cohort", "city_tier", "province_topk", "store_avg_lock",
                                        "assign_conversion", "weighted_lead_conversion", "mature_lock_prediction"
                                    ]},
                                    "attribute_table": {"type": "string"},
                                    "attribute_field": {"type": "string"},
                                    "attribute_pattern": {"type": "string"},
                                    "value_field": {"type": "string"},
                                    "positive_value": {"type": "string"},
                                    "dimension_field": {"type": "string"},
                                    "dimension_mapping": {"type": "object"},
                                    "join_key_left": {"type": "string"},
                                    "join_key_right": {"type": "string"},
                                    "top_k": {"type": "integer"},
                                    "numerator_metric": {"type": "string"},
                                    "denominator_scope": {"type": "string"},
                                    "time_grain": {"type": "string"},
                                    "breakdown_dimension": {"type": "string"},
                                },
                                "required": ["type"],
                            },
                            "post_process": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {"type": "string", "enum": ["window_share", "ratio"]},
                                        "partition_by": {"type": "array", "items": {"type": "string"}},
                                        "value_field": {"type": "string"},
                                        "alias": {"type": "string"},
                                        "numerator": {"type": "string"},
                                        "denominator": {"type": "string"},
                                    },
                                    "required": ["type"],
                                },
                            },
                        },
                        "required": ["dataset", "metric", "time", "comparison"],
                    },
                },
                "clarification": {
                    "type": "object",
                    "properties": {
                        "need": {"type": "boolean"},
                        "question": {"type": "string"},
                        "options": {"type": "array", "items": {"type": "string"}},
                        "context": {"type": "object"},
                    },
                },
            },
            "required": ["plans"],
        },
    },
}

TIME_REWRITE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "rewrite_time_window",
        "description": "重写时间窗口（左闭右开），仅返回 start/end（YYYY-MM-DD）。",
        "parameters": {
            "type": "object",
            "properties": {
                "start": {"type": "string"},
                "end": {"type": "string"},
            },
            "required": ["start", "end"],
        },
    },
}


class PlanningAgent:
    _SERIES_CANDIDATES = ("LS9", "LS8", "LS7", "LS6", "L7", "L6")
    _TIME_REWRITE_WHITELIST = {
        "yesterday",
        "this_week",
        "this_month_to_today",
        "last_month",
        "month_to_today",
        "month",
        "year",
        "date",
        "date_range",
    }
    _DIMENSION_SYNONYMS = {
        "product_name": ["按产品名称", "分产品名称", "产品名称", "按产品", "分产品", "产品名", "product name", "product_name", "productname"],
        "series": ["分车型", "按车型", "车型分别", "车型", "分车系", "按车系", "车系分别", "车系", "按系列", "分系列", "系列", "series"],
        "parent_region_name": ["按大区", "分大区", "大区分别", "region"],
        "store_name": ["按门店", "分门店", "门店分别", "store"],
        "store_city": ["按门店城市", "分门店城市", "门店城市分别", "store city", "store_city"],
        "license_city": ["按上牌城市", "分上牌城市", "上牌城市分别", "license city", "license_city"],
        "order_gender": ["订单用户", "订单性别", "订单性别占比", "订单用户性别", "购车人性别", "用户性别", "order_gender"],
        "owner_gender": ["按性别", "分性别", "性别", "男女", "男女比例", "男女占比", "性别占比", "车主", "车主性别", "owner_gender"],
    }

    def __init__(self, client: OpenAI, schema_md: str, business_definition: str, operator_catalog: str = "", metric_registry: MetricRegistry | None = None):
        self.client = client
        self.schema_md = schema_md or ""
        self.business_definition = business_definition or ""
        self.operator_catalog = operator_catalog or ""
        self.metric_registry = metric_registry or MetricRegistry()
        self.last_planning_error: str = ""
        self.business_definition_obj: dict = {}
        try:
            raw = (self.business_definition or "").strip()
            if raw:
                self.business_definition_obj = json.loads(raw)
        except Exception:
            self.business_definition_obj = {}

    @staticmethod
    def _is_dimension_enumeration_query(user_query: str) -> bool:
        q = (user_query or "").strip()
        if not q:
            return False
        q_no_space = q.replace(" ", "")
        has_list_intent = any(k in q_no_space for k in ["有哪些", "有什么", "列出", "清单", "都有哪些", "分别有哪些", "包括哪些", "包含哪些"])
        if not has_list_intent:
            return False
        return any(
            PlanningAgent._contains_any_token(q_no_space, PlanningAgent._DIMENSION_SYNONYMS.get(dim) or [])
            for dim in ["product_name", "series", "parent_region_name", "store_name", "store_city", "license_city"]
        )

    def _build_dimension_enumeration_plan(self, user_query: str) -> dict | None:
        if not self._is_dimension_enumeration_query(user_query):
            return None
        today = datetime.date.today()
        series_tokens = self._infer_series_tokens(user_query)
        start = (today - datetime.timedelta(days=365)).isoformat()
        end = (today + datetime.timedelta(days=1)).isoformat()
        if series_tokens and isinstance(self.business_definition_obj, dict):
            periods = self.business_definition_obj.get("time_periods")
            if isinstance(periods, dict):
                token = series_tokens[0]
                meta = periods.get(token)
                if isinstance(meta, dict):
                    s = meta.get("start")
                    if isinstance(s, str) and s.strip():
                        try:
                            _ = datetime.date.fromisoformat(s.strip())
                            start = s.strip()
                        except Exception:
                            pass
        plan = {
            "dataset": "order_data",
            "metric": {"field": "order_number", "agg": "count", "alias": "count", "business_name": "订单计数"},
            "time": {"field": "order_create_date", "start": start, "end": end},
            "dimensions": [],
            "filters": [{"field": "order_create_date", "op": "!=", "value": None}],
            "comparison": {"type": "none"},
        }
        return self._normalize_plan(plan)

    @staticmethod
    def _is_retained_intention_query(user_query: str) -> bool:
        q = (user_query or "").replace(" ", "")
        if not q:
            return False
        if "留存小订" not in q:
            return False
        if "转化" in q:
            return False
        return True

    @staticmethod
    def _is_penetration_query(user_query: str) -> bool:
        q = (user_query or "").replace(" ", "")
        if not q:
            return False
        if "选装率" in q or "渗透率" in q or "配置率" in q:
            return True
        if "选装比例" in q or any(k in q for k in ["不同.*轮毂", "不同.*配置"]):
            return True
        return match_template(q) is not None

    def _build_penetration_plan(self, user_query: str) -> dict | None:
        if not self._is_penetration_query(user_query):
            return None
        from tools.config_cross_analysis_templates import is_distribution_query
        plan = template_build_plan(user_query, self.business_definition_obj)
        if plan:
            plan["question"] = user_query
            return self._normalize_plan(plan)
        return None

    def _resolve_retained_intention_time_window(self, user_query: str, today: datetime.date) -> tuple[str, str]:
        until_end = parse_until_end_date(user_query)
        if until_end:
            end_excl = until_end + datetime.timedelta(days=1)
            series_tokens = self._infer_series_tokens(user_query)
            if series_tokens and isinstance(self.business_definition_obj, dict):
                periods = self.business_definition_obj.get("time_periods")
                if isinstance(periods, dict):
                    token = series_tokens[0]
                    meta = periods.get(token)
                    if isinstance(meta, dict):
                        s = meta.get("start")
                        if isinstance(s, str) and s.strip():
                            try:
                                start_day = datetime.date.fromisoformat(s.strip())
                                if start_day < end_excl:
                                    return (start_day.isoformat(), end_excl.isoformat())
                            except Exception:
                                pass
            fallback_start = until_end - datetime.timedelta(days=30)
            return (fallback_start.isoformat(), end_excl.isoformat())

        m = re.search(r"(\d{4}-\d{2}-\d{2})\s*(?:到|至|[-~—–－])\s*(\d{4}-\d{2}-\d{2})", user_query or "")
        if m:
            try:
                start_day = datetime.date.fromisoformat(m.group(1))
                end_day = datetime.date.fromisoformat(m.group(2))
                end_excl = end_day + datetime.timedelta(days=1)
                if end_excl > start_day:
                    return (start_day.isoformat(), end_excl.isoformat())
            except Exception:
                pass

        window = self._parse_time_window_with_business(user_query, today)
        if window:
            start_s, end_s = window
            try:
                end_day = datetime.date.fromisoformat(str(end_s)[:10])
                start_day = datetime.date.fromisoformat(str(start_s)[:10])
                if end_day <= start_day:
                    return window
                return (start_day.isoformat(), end_day.isoformat())
            except Exception:
                return window
        series_tokens = self._infer_series_tokens(user_query)
        if series_tokens and isinstance(self.business_definition_obj, dict):
            periods = self.business_definition_obj.get("time_periods")
            if isinstance(periods, dict):
                token = series_tokens[0]
                meta = periods.get(token)
                if isinstance(meta, dict):
                    s = meta.get("start")
                    if isinstance(s, str) and s.strip():
                        try:
                            start_day = datetime.date.fromisoformat(s.strip())
                            if start_day < today:
                                return (start_day.isoformat(), today.isoformat())
                        except Exception:
                            pass
        start = (today - datetime.timedelta(days=30)).isoformat()
        return (start, today.isoformat())

    def _build_retained_intention_plan(self, user_query: str) -> dict | None:
        if not self._is_retained_intention_query(user_query):
            return None
        today = datetime.date.today()
        start, end = self._resolve_retained_intention_time_window(user_query, today)
        plan = {
            "dataset": "order_data",
            "metric": {"field": "order_number", "agg": "count", "alias": "留存小订数", "business_name": "留存小订数"},
            "time": {"field": "intention_payment_time", "start": start, "end": end},
            "dimensions": [],
            "filters": [],
            "comparison": {"type": "none"},
        }
        if "趋势" in (user_query or "").replace(" ", ""):
            plan["dimensions"] = ["intention_payment_time"]
            plan["statistics"] = {
                "type": "trend_summary",
                "window_days": 10,
                "value_metric": {"alias": "留存小订数"},
            }
        return self._normalize_plan(plan)

    @staticmethod
    def _contains_any_token(user_query: str, tokens: list[str]) -> bool:
        q = (user_query or "").replace(" ", "")
        q_lower = q.lower()
        if not q_lower:
            return False
        if not isinstance(tokens, list) or not tokens:
            return False
        for t in tokens:
            if not isinstance(t, str):
                continue
            raw = t.strip()
            if not raw:
                continue
            if raw.lower() in q_lower:
                return True
        return False

    def _parse_time_window_with_business(self, user_query: str, today: datetime.date) -> tuple[str, str] | None:
        return parse_time_window_with_business(user_query, today, self.business_definition_obj)

    @staticmethod
    def _parse_comparison_type(user_query: str) -> str:
        return parse_comparison_type(user_query)

    @staticmethod
    def _classify_intent(user_query: str) -> str:
        q = (user_query or "").strip()
        if not q:
            return "query"

        stat_keywords = [
            "有多少天",
            "多少天",
            "几天",
            "多少周",
            "几周",
            "连续",
            "超过",
            "大于",
            "小于",
            "高于",
            "低于",
            "阈值",
            "下降",
            "日均",
            "均值",
            "平均值",
            "平均",
            "中位数",
            "中值",
            "趋势",
            "走势",
            "波动",
            "分位",
            "百分位",
            "处于什么水平",
            "什么水平",
        ]
        has_stat_keyword = any(k in q for k in stat_keywords)
        has_explicit_window = PlanningAgent._parse_time_window(q, datetime.date.today()) is not None
        has_time_window = has_explicit_window or bool(re.search(r"近\s*\d+\s*(日|天|周|月|年)", q)) or any(
            k in q for k in ["昨天", "昨日", "本周", "上周", "本月", "上月", "今年", "去年", "上市至今", "上市以来", "预售至今", "预售以来"]
        )
        if has_stat_keyword and has_time_window:
            return "statistics"
        if any(k in q for k in ["同比", "年同比", "环比", "周环比"]):
            return "comparison"
        return "query"

    @staticmethod
    def _parse_time_window(user_query: str, today: datetime.date) -> tuple[str, str] | None:
        return parse_time_window(user_query, today)

    @staticmethod
    def infer_goal_time_window_rule(user_query: str, today: datetime.date) -> dict:
        return infer_goal_time_window_rule(user_query, today)

    def infer_goal_time_window(self, user_query: str, today: datetime.date) -> dict:
        return _ts_infer_goal_time_window(user_query, today, self.business_definition_obj)

    def _metric_defaults(self, user_query: str) -> dict | None:
        q = user_query or ""
        raw_matches = self.metric_registry.match_by_query(q)
        if not raw_matches:
            return None
        scored = []
        for name, cfg in raw_matches:
            score = 0
            all_tokens = [name] + cfg.get("aliases", [])
            for t in all_tokens:
                if t and t in q:
                    score += len(t)
            if cfg.get("type") == "operator":
                score += 200
            scored.append((score, name, cfg))
        scored.sort(key=lambda x: -x[0])
        name, cfg = scored[0][1], scored[0][2]
        dataset = cfg.get("dataset", "order_data")
        time_field = cfg.get("time_field", "lock_time")
        metric = {
            "field": cfg.get("field", "order_number"),
            "agg": cfg.get("agg", "count"),
            "alias": name,
            "business_name": name,
        }
        result: dict = {
            "dataset": dataset,
            "metric": metric,
            "time_field": time_field,
        }
        non_null_candidates = [f.get("value") for f in cfg.get("extra_filters", []) if f.get("op") == "!=" and f.get("value") is None]
        if cfg.get("field") in ("store_name",) or any(f.get("field") == time_field for f in cfg.get("extra_filters", []) if f.get("op") == "!="):
            result["non_null_field"] = time_field
        if cfg.get("extra_filters"):
            result["extra_filters"] = list(cfg.get("extra_filters"))
        if cfg.get("type") == "operator":
            result["operator_intent"] = cfg.get("operator")
        return result

    @staticmethod
    def _parse_fast_path_query(user_query: str) -> dict | None:
        q = (user_query or "").strip()
        if not q:
            return None
        q_lower = q.lower()
        if any(k in q_lower for k in ["welldone", "well done", "good job", "nice", "great"]) or any(
            k in q for k in ["你好", "您好", "在吗", "辛苦了", "谢谢", "感谢", "赞", "太棒了", "干得好", "厉害"]
        ):
            return {"type": "small_talk_contextual"}
        iso_week_hint = any(k in q for k in ["第几周", "ISO周", "ISO 周", "isoweek", "iso week"])
        has_today = any(k in q for k in ["今天", "今日", "当前日期"])
        if iso_week_hint and has_today:
            return {"type": "current_iso_week"}
        is_sync = "数据更新并同步" in q or "更新数据并同步" in q
        if not is_sync and "同步数据" in q:
            is_sync = True
        is_update = any(k in q for k in ["更新数据", "刷新数据", "数据更新", "刷新数据集", "更新订单", "更新选配", "全部更新", "刷新全部", "更新归属"])
        if not is_update and not is_sync and (q.startswith("更新") or q.startswith("刷新")):
            is_update = True
        if is_sync or is_update:
            scope = "all"
            if "订单" in q or "order" in q.lower():
                scope = "order"
            elif "选配" in q or "config" in q.lower():
                scope = "config"
            elif "归属" in q:
                scope = "lock"
            if is_sync:
                return {"type": "data_sync", "scope": scope}
            return {"type": "data_update", "scope": scope}
        if any(k in q for k in ["锁单", "交付", "开票", "门店", "线索", "试驾", "在营"]):
            return None
        if any(k in q for k in ["订单"]):
            return None
        has_compare_intent = any(k in q for k in ["环比", "同比", "提升", "增长", "下降", "减少", "涨幅", "降幅", "相比", "较", "比"])
        has_ask = any(k in q for k in ["多少", "几", "百分比", "%", "百分点"])
        if not (has_compare_intent and has_ask):
            return None
        nums = re.findall(r"-?\d+(?:\.\d+)?", q.replace(",", ""))
        if len(nums) < 2:
            return None
        try:
            current = float(nums[0])
            base = float(nums[1])
        except Exception:
            return None
        return {"type": "numeric_ratio", "current": current, "base": base}

    @staticmethod
    def _infer_series_tokens(user_query: str) -> list[str]:
        q = (user_query or "").upper()
        tokens: list[str] = []
        for s in PlanningAgent._SERIES_CANDIDATES:
            if s in q:
                tokens.append(s)
        return list(dict.fromkeys(tokens))

    _RE_PRODUCT_NAME = re.compile(
        r'(智己[\w\u4e00-\u9fff]+(?:\s+[\w\u4e00-\u9fff+]+)*?(?:Max\+?|Pro|Ultra|标准|长续|奢享|科技|大五座|大六座|豪华|性能|续航|光年)(?:\s+[\w\u4e00-\u9fff+]+)*)'
    )
    _RE_PRODUCT_NAME_NO_PREFIX = re.compile(
        r'(LS\d[\w\u4e00-\u9fff\+]*(?:\s+[\w\u4e00-\u9fff+]+)*?(?:Max\+?|Pro|Ultra|标准|长续|奢享|科技|大五座|大六座|豪华|性能|续航|光年)(?:\s+[\w\u4e00-\u9fff+]+)*)'
    )

    @staticmethod
    def _infer_product_name_token(user_query: str) -> str | None:
        q = (user_query or "").strip()
        if not q:
            return None
        m = PlanningAgent._RE_PRODUCT_NAME.search(q)
        if m:
            return m.group(1).strip()
        m = PlanningAgent._RE_PRODUCT_NAME_NO_PREFIX.search(q)
        if m:
            return m.group(1).strip()
        return None

    @staticmethod
    def _has_field_filter(filters: list, fields: set[str]) -> bool:
        for f in filters:
            if not isinstance(f, dict):
                continue
            if str(f.get("field") or "") in fields:
                return True
        return False

    @staticmethod
    def _apply_semantic_filters(filters: list, user_query: str) -> list:
        q = (user_query or "").replace(" ", "")
        has_trial_metric_context = any(k in q for k in ["试驾率", "试驾数", "有效试驾"])
        ask_trial_car = (("试驾车" in q) or ("试驾" in q and not has_trial_metric_context)) and not any(
            k in q for k in ["非试驾车", "不是试驾车", "排除试驾", "不含试驾", "剔除试驾"]
        )
        ask_non_trial_car = any(k in q for k in ["非试驾车", "不是试驾车", "排除试驾", "不含试驾", "剔除试驾"])
        ask_user_car = "用户车" in q

        has_order_type_filter = PlanningAgent._has_field_filter(filters, {"order_type"})
        if not has_order_type_filter:
            if ask_trial_car and not ask_user_car:
                filters.append({"field": "order_type", "op": "==", "value": "试驾车"})
            elif ask_user_car and not ask_trial_car:
                filters.append({"field": "order_type", "op": "==", "value": "用户车"})
            elif ask_non_trial_car:
                filters.append({"field": "order_type", "op": "!=", "value": "试驾车"})

        series_tokens = PlanningAgent._infer_series_tokens(q)
        has_series_filter = PlanningAgent._has_field_filter(filters, {"series", "product_name", "drive_series_cn", "belong_intent_series"})
        if (not has_series_filter) and series_tokens and ("下发线索" not in q):
            if len(series_tokens) == 1:
                filters.append({"field": "series", "op": "==", "value": series_tokens[0]})
            elif len(series_tokens) > 1:
                filters.append({"field": "series", "op": "in", "value": series_tokens})

        has_product_name_filter = PlanningAgent._has_field_filter(filters, {"product_name"})
        if not has_product_name_filter:
            product_token = PlanningAgent._infer_product_name_token(user_query)
            if product_token and series_tokens:
                filters = PlanningAgent._append_filter(filters, {"field": "product_name", "op": "matches", "value": re.escape(product_token)})

        return filters

    def _infer_series_group_tokens(self, user_query: str) -> list[str]:
        q_upper = (user_query or "").upper()
        candidates: list[str] = []
        if isinstance(self.business_definition_obj, dict):
            logic = self.business_definition_obj.get("series_group_logic")
            if isinstance(logic, dict):
                for k in logic.keys():
                    if not isinstance(k, str):
                        continue
                    kk = k.strip()
                    if not kk or kk == "其他":
                        continue
                    if not re.fullmatch(r"(?:CM|DM)\d+", kk.upper()):
                        continue
                    candidates.append(kk.upper())
        if not candidates:
            candidates = ["CM0", "CM1", "CM2", "DM0", "DM1"]
        tokens: list[str] = []
        for tok in candidates:
            if tok and tok in q_upper:
                tokens.append(tok)
        return list(dict.fromkeys(tokens))

    def _apply_business_semantic_filters(self, filters: list, user_query: str) -> list:
        q = (user_query or "").replace(" ", "")
        q_upper = q.upper()

        series_group_tokens = self._infer_series_group_tokens(q_upper)
        if series_group_tokens:
            for tok in series_group_tokens:
                filters = PlanningAgent._append_filter(filters, {"field": "series_group_logic", "op": "==", "value": tok})

        has_product_name_regex_filter = any(
            isinstance(f, dict)
            and f.get("field") == "product_name"
            and f.get("op") in {"matches", "not matches"}
            and isinstance(f.get("value"), str)
            for f in (filters or [])
        )

        exclude_reev = any(k in q for k in ["非增程", "不是增程", "排除增程", "不含增程", "剔除增程"])
        exclude_ev = any(k in q for k in ["非纯电", "不是纯电", "排除纯电", "不含纯电", "剔除纯电"])

        if ("增程" in q) and (not exclude_reev) and (not has_product_name_regex_filter) and ("纯电" not in q):
            filters = PlanningAgent._append_filter(filters, {"field": "product_name", "op": "matches", "value": "52|66"})
        elif ("纯电" in q) and (not exclude_ev) and (not has_product_name_regex_filter) and ("增程" not in q):
            filters = PlanningAgent._append_filter(filters, {"field": "product_name", "op": "not matches", "value": "52|66"})

        return filters

    @staticmethod
    def _should_sales_clarify(user_query: str) -> bool:
        q = user_query or ""
        if not q:
            return False
        if not any(k in q for k in ["销量", "卖了多少", "成交量"]):
            return False
        if any(k in q for k in ["锁单", "交付", "开票"]):
            return False
        return True

    @staticmethod
    def _sales_clarification(original_question: str) -> dict:
        return {
            "need": True,
            "question": "你提到的“销量”具体是指哪个业务口径？",
            "options": ["锁单量", "交付数", "开票数"],
            "context": {"original_question": original_question},
        }

    @staticmethod
    def _extract_city_token(user_query: str) -> str | None:
        q = (user_query or "").strip().lstrip(" \t\r\n\"'“”‘’")
        if not q:
            return None
        stop = {"查询", "统计", "汇总", "查看", "分析", "对比", "输出", "导出", "列出", "展示", "打印", "生成"}
        m = re.search(r"([\u4e00-\u9fff]{2,8})市", q)
        if m:
            city = (m.group(1) or "").strip()
            if not city or city in stop:
                return None
            if any(bad in city for bad in stop):
                return None
            return city
        m = re.search(r"^([\u4e00-\u9fff]{2,8})(?=(昨天|昨日|今日|今天|本周|上周|本月|上月|今年|去年|前年|\d{2,4}年))", q)
        if m:
            city = (m.group(1) or "").strip()
            if not city or city in stop:
                return None
            if any(bad in city for bad in stop):
                return None
            return city
        return None

    @staticmethod
    def _should_city_clarify(user_query: str) -> tuple[bool, str | None]:
        q = user_query or ""
        if not q:
            return (False, None)
        if any(k in q for k in ["门店城市", "store_city", "上牌城市", "license_city"]):
            return (False, None)
        if not any(k in q for k in ["锁单", "交付", "开票", "小订", "意向金", "订单"]):
            return (False, None)
        city = PlanningAgent._extract_city_token(q)
        if not city:
            return (False, None)
        return (True, city)

    @staticmethod
    def _city_clarification(city: str, original_question: str) -> dict:
        return {
            "need": True,
            "question": f"你问的“{city}”是指门店城市(store_city)，还是上牌城市(license_city)？",
            "options": ["门店城市", "上牌城市", "两者都要"],
            "context": {"city": city, "original_question": original_question},
        }

    @staticmethod
    def _resolve_gender_dimension(user_query: str) -> str | None:
        q = (user_query or "").replace(" ", "")
        if not q:
            return None
        if any(k in q for k in ["订单用户", "订单性别", "订单性别占比", "订单用户性别", "购车人性别", "下单用户性别", "锁单用户性别", "order_gender"]):
            return "order_gender"
        if any(k in q for k in ["车主性别", "owner_gender", "车主"]):
            return "owner_gender"
        if any(k in q for k in ["性别", "男女", "男女比例", "男女占比", "性别占比"]):
            return "owner_gender"
        return None

    @staticmethod
    def _parse_top_k_token(user_query: str) -> int | None:
        q = (user_query or "").upper().replace(" ", "")
        m = re.search(r"TOP\s*(\d{1,3})", q)
        if not m:
            m = re.search(r"前\s*(\d{1,3})\s*个", (user_query or "").replace(" ", ""))
        if not m:
            m = re.search(r"TOP(\d{1,3})", q)
        if not m:
            return None
        try:
            v = int(m.group(1))
            return v if 1 <= v <= 200 else None
        except Exception:
            return None

    @staticmethod
    def _resolve_category_share_dimension(user_query: str) -> str | None:
        q = (user_query or "").replace(" ", "")
        if not q:
            return None
        if any(k in q for k in ["线级", "一线", "新一线", "二线", "三线"]):
            return None
        if any(k in q.upper() for k in ["TOP"]) and any(k in q for k in ["省", "省份"]):
            return None
        gender_dim = PlanningAgent._resolve_gender_dimension(q)
        if gender_dim:
            return gender_dim
        if any(k in q for k in ["订单类型", "order_type"]):
            return "order_type"
        if any(k in q for k in ["尾款支付方式", "支付方式", "final_payment_way"]):
            return "final_payment_way"
        if any(k in q for k in ["金融产品", "finance_product"]):
            return "finance_product"
        return None

    @staticmethod
    def _is_category_share_query(user_query: str) -> bool:
        q = (user_query or "").replace(" ", "")
        if not q:
            return False
        if not any(k in q for k in ["占比", "比例", "分布"]):
            return False
        return PlanningAgent._resolve_category_share_dimension(q) is not None

    def _build_category_share_plan(self, user_query: str) -> dict | None:
        today = datetime.date.today()
        metric_defaults = self._metric_defaults(user_query)
        if not metric_defaults:
            return None
        dim = PlanningAgent._resolve_category_share_dimension(user_query)
        if not dim:
            return None
        time_window = self._parse_time_window_with_business(user_query, today) or (
            (today - datetime.timedelta(days=1)).isoformat(),
            today.isoformat(),
        )
        start, end = time_window
        time_field = metric_defaults["time_field"]
        metric_obj = metric_defaults.get("metric") if isinstance(metric_defaults.get("metric"), dict) else {}
        non_null_field = metric_defaults.get("non_null_field")
        filters: list[dict] = []
        if non_null_field:
            filters = PlanningAgent._append_filter(filters, {"field": non_null_field, "op": "!=", "value": None})
        series_tokens = PlanningAgent._infer_series_tokens(user_query)
        if len(series_tokens) == 1:
            filters = PlanningAgent._append_filter(filters, {"field": "series", "op": "==", "value": series_tokens[0]})
        top_k = PlanningAgent._parse_top_k_token(user_query)
        plan = {
            "dataset": metric_defaults["dataset"],
            "metric": {
                "field": metric_obj.get("field") or "order_number",
                "agg": metric_obj.get("agg") or "count",
                "alias": metric_obj.get("alias") or "value",
                "business_name": metric_obj.get("business_name") or metric_obj.get("alias") or "value",
            },
            "time": {"field": time_field, "start": start, "end": end},
            "dimensions": [dim],
            "filters": filters,
            "comparison": {"type": "none"},
            "statistics": {
                "type": "category_share",
                "category_field": dim,
                "top_k": top_k,
                "value_metric": {
                    "field": metric_obj.get("field") or "order_number",
                    "agg": metric_obj.get("agg") or "count",
                    "alias": metric_obj.get("alias") or "value",
                },
            },
            "question": "分类占比",
        }
        return self._fill_defaults(self._normalize_plan(plan), user_query)

    @staticmethod
    def _is_share_breakdown_query(user_query: str) -> bool:
        q = (user_query or "").replace(" ", "")
        if not q:
            return False
        if not any(k in q for k in ["占比", "比例", "份额", "占"]):
            return False
        has_dim = any(
            PlanningAgent._contains_any_token(q, PlanningAgent._DIMENSION_SYNONYMS.get(dim) or [])
            for dim in ["series", "product_name", "parent_region_name", "store_name", "store_city", "license_city", "order_gender", "owner_gender"]
        )
        has_time_grain = any(k in q for k in ["按周", "每周", "周度", "逐周", "按日", "每日", "逐日", "日度", "按天", "每天",
                                                "按月", "每月", "月度", "逐月", "按季", "每季度", "季度"])
        return has_dim and has_time_grain

    @staticmethod
    def _infer_time_grain(user_query: str) -> str:
        q = (user_query or "").replace(" ", "")
        if any(k in q for k in ["按周", "每周", "周度", "逐周", "周别"]):
            return "week"
        if any(k in q for k in ["按日", "每日", "逐日", "日度", "按天", "每天", "日别"]):
            return "day"
        if any(k in q for k in ["按月", "每月", "月度", "逐月", "月别"]):
            return "month"
        return "week"

    @staticmethod
    def _resolve_breakdown_dimension(user_query: str, has_series_filter: bool = False) -> str:
        q = (user_query or "").replace(" ", "")
        for dim, synonyms in PlanningAgent._DIMENSION_SYNONYMS.items():
            if PlanningAgent._contains_any_token(q, synonyms):
                if dim == "series" and has_series_filter:
                    return "product_name"
                return dim
        return "series"

    def _build_share_breakdown_plan(self, user_query: str) -> dict | None:
        metric_defaults = self._metric_defaults(user_query)
        if not metric_defaults:
            return None
        today = datetime.date.today()
        time_window = self._parse_time_window_with_business(user_query, today) or (
            (today - datetime.timedelta(days=7)).isoformat(),
            today.isoformat(),
        )
        start, end = time_window
        time_field = metric_defaults["time_field"]
        non_null_field = metric_defaults.get("non_null_field")
        metric_obj: dict = metric_defaults.get("metric") or {}
        metric_alias = metric_obj.get("alias") or "value"

        time_grain = self._infer_time_grain(user_query)
        time_grain_cn = {"week": "周", "day": "日", "month": "月"}.get(time_grain, "周")
        series_tokens = PlanningAgent._infer_series_tokens(user_query)
        breakdown_dim = self._resolve_breakdown_dimension(user_query, has_series_filter=bool(series_tokens))

        filters: list[dict] = []
        if non_null_field:
            filters = PlanningAgent._append_filter(filters, {"field": non_null_field, "op": "!=", "value": None})

        is_cumulative = PlanningAgent._is_cumulative_query(user_query)
        dimensions = [breakdown_dim] if is_cumulative else [time_field, breakdown_dim]
        plan = {
            "dataset": metric_defaults["dataset"],
            "metric": {
                "field": metric_obj.get("field") or "order_number",
                "agg": metric_obj.get("agg") or "count",
                "alias": metric_alias,
                "business_name": metric_obj.get("business_name") or metric_alias,
            },
            "time": {"field": time_field, "start": start, "end": end},
            "dimensions": dimensions,
            "filters": filters,
            "comparison": {"type": "none"},
        }
        if not is_cumulative:
            plan["analysis_intent"] = {
                "type": "share_breakdown",
                "numerator_metric": metric_alias,
                "denominator_scope": f"within_each_{time_grain}",
                "time_grain": time_grain,
                "breakdown_dimension": breakdown_dim,
            }
            plan["post_process"] = [
                {
                    "type": "window_share",
                    "partition_by": [time_field],
                    "value_field": metric_alias,
                    "alias": f"每{time_grain_cn}占比",
                }
            ]
        return self._fill_defaults(self._normalize_plan(plan), user_query)

    @staticmethod
    def _append_filter(filters: list[dict], new_filter: dict) -> list[dict]:
        if not isinstance(new_filter, dict):
            return filters
        field = new_filter.get("field")
        op = new_filter.get("op")
        value = new_filter.get("value", None)
        for f in filters:
            if not isinstance(f, dict):
                continue
            if f.get("field") == field and f.get("op") == op and f.get("value", None) == value:
                return filters
        return [*filters, new_filter]

    @staticmethod
    def _parse_recent_weeks(user_query: str) -> int | None:
        q = user_query or ""
        m = re.search(r"近\s*(\d{1,3})\s*(?:个)?\s*周", q)
        if not m:
            return None
        try:
            v = int(m.group(1))
            return v if v > 0 else None
        except Exception:
            return None

    @staticmethod
    def _parse_recent_days(user_query: str) -> int | None:
        q = user_query or ""
        m = re.search(r"近\s*(\d{1,3})\s*(?:日|天)", q)
        if not m:
            return None
        try:
            v = int(m.group(1))
            return v if v > 0 else None
        except Exception:
            return None

    @staticmethod
    def _parse_recent_weekends(user_query: str) -> int | None:
        q = user_query or ""
        m = re.search(r"近\s*(\d{1,3})\s*(?:个)?\s*周末", q)
        if not m:
            return None
        try:
            v = int(m.group(1))
            return v if v > 0 else None
        except Exception:
            return None

    @staticmethod
    def _parse_threshold_condition(user_query: str) -> tuple[str, float] | None:
        q = (user_query or "").replace(" ", "")
        pattern_map = [
            (r"(?:大于等于|不低于|不少于|>=)\s*(\d+(?:\.\d+)?)", ">="),
            (r"(?:小于等于|不高于|不大于|<=)\s*(\d+(?:\.\d+)?)", "<="),
            (r"(?:大于|高于|超过|>)\s*(\d+(?:\.\d+)?)", ">"),
            (r"(?:小于|低于|<)\s*(\d+(?:\.\d+)?)", "<"),
            (r"(?:等于|==)\s*(\d+(?:\.\d+)?)", "=="),
            (r"(?:不等于|!=)\s*(\d+(?:\.\d+)?)", "!="),
        ]
        for pattern, op in pattern_map:
            m = re.search(pattern, q)
            if not m:
                continue
            try:
                return (op, float(m.group(1)))
            except Exception:
                continue
        return None

    @staticmethod
    def _parse_weekdays(user_query: str) -> list[int]:
        q = user_query or ""
        mapping = {
            "周一": 1,
            "星期一": 1,
            "周二": 2,
            "星期二": 2,
            "周三": 3,
            "星期三": 3,
            "周四": 4,
            "星期四": 4,
            "周五": 5,
            "星期五": 5,
            "周六": 6,
            "星期六": 6,
            "周日": 7,
            "周天": 7,
            "星期日": 7,
            "星期天": 7,
        }
        out: list[int] = []
        for k, v in mapping.items():
            if k in q:
                out.append(v)
        return sorted(list(dict.fromkeys(out)))

    @staticmethod
    def _is_weekly_decline_ratio_query(user_query: str) -> bool:
        q = user_query or ""
        if not q:
            return False
        has_rate = "锁单率" in q
        has_decline = ("下降" in q and "多少" in q) or "下降周数" in q
        has_week_window = "近" in q and "周" in q
        has_source = "下发线索" in q and "门店" in q
        has_weekday = ("周四" in q or "星期四" in q or "周五" in q or "星期五" in q)
        return has_rate and has_decline and has_week_window and has_source and has_weekday

    @staticmethod
    def _is_daily_threshold_count_query(user_query: str) -> bool:
        q = user_query or ""
        if not q:
            return False
        has_day_count = ("多少天" in q) or ("几天" in q)
        has_recent_day = ("近" in q) and (("日" in q) or ("天" in q))
        has_threshold = PlanningAgent._parse_threshold_condition(q) is not None
        return has_day_count and has_recent_day and has_threshold

    @staticmethod
    def _is_daily_mean_query(user_query: str) -> bool:
        q = user_query or ""
        if not q:
            return False
        has_mean = any(k in q for k in ["日均", "均值", "平均值", "平均"])
        has_recent_day = bool(re.search(r"近\s*(?:\d+|[一二两三四五六七八九十])\s*(日|天|周|月|年)", q))
        has_relative_day = any(k in q for k in ["昨天", "昨日", "今天", "今日", "本周", "上周", "本月", "上月", "上市至今", "上市以来", "预售至今", "预售以来", "至今", "截至", "目前", "现在"])
        has_explicit_window = PlanningAgent._extract_explicit_time_window(q, datetime.date.today()) is not None
        return has_mean and (has_recent_day or has_relative_day or has_explicit_window)

    @staticmethod
    def _is_daily_mean_median_query(user_query: str) -> bool:
        q = user_query or ""
        if not q:
            return False
        has_mean = any(k in q for k in ["日均", "均值", "平均值", "平均"])
        has_median = any(k in q for k in ["中位数", "中值"])
        if not (has_mean and has_median):
            return False
        has_recent = bool(re.search(r"近\s*(?:\d+|[一二两三四五六七八九十])\s*(日|天|周|月|年)", q))
        has_relative = any(k in q for k in ["昨天", "昨日", "今天", "今日", "本周", "上周", "本月", "上月", "上市至今", "上市以来", "预售至今", "预售以来", "至今", "截至", "目前", "现在"])
        has_explicit = PlanningAgent._extract_explicit_time_window(q, datetime.date.today()) is not None
        return has_recent or has_relative or has_explicit

    @staticmethod
    def _is_trend_summary_query(user_query: str) -> bool:
        q = user_query or ""
        if not q:
            return False
        has_trend = any(k in q for k in ["趋势", "走势", "变化趋势", "波动趋势", "波动情况"])
        has_recent = bool(re.search(r"近\s*(?:\d+|[一二两三四五六七八九十])\s*(日|天|周|月|年)", q))
        has_relative = any(k in q for k in ["昨天", "昨日", "今天", "今日", "本周", "上周", "本月", "上月", "今年", "去年", "至今", "截至"])
        has_explicit = PlanningAgent._extract_explicit_time_window(q, datetime.date.today()) is not None
        return has_trend and (has_recent or has_relative or has_explicit)

    @staticmethod
    def _is_contribution_summary_query(user_query: str) -> bool:
        q = user_query or ""
        if not q:
            return False
        has_contrib = any(k in q for k in ["贡献", "拆解", "贡献项", "主要贡献", "贡献度", "贡献来源"])
        has_recent = bool(re.search(r"近\s*(?:\d+|[一二两三四五六七八九十])\s*(日|天)", q))
        return has_contrib and has_recent

    @staticmethod
    def _is_daily_percentile_rank_query(user_query: str) -> bool:
        q = user_query or ""
        if not q:
            return False
        has_percentile = any(k in q for k in ["分位", "百分位", "分位值", "百分位值"])
        has_level = any(k in q for k in ["处于什么水平", "什么水平", "处于什么位置", "高低水平"])
        has_ref = any(k in q for k in ["昨天", "昨日", "今天", "今日"])
        has_recent_day = bool(re.search(r"近\s*\d+\s*(日|天)", q))
        return (has_percentile or has_level) and has_ref and has_recent_day

    @staticmethod
    def _is_weekend_percentile_rank_query(user_query: str) -> bool:
        q = user_query or ""
        if not q:
            return False
        has_level = any(k in q for k in ["处于什么水平", "什么水平", "处于什么位置", "高低水平", "分位", "百分位"])
        has_weekend = "周末" in q
        has_recent_weekend = bool(re.search(r"近\s*\d+\s*(?:个)?\s*周末", q))
        has_ref = any(k in q for k in ["本周末", "这个周末", "上周末", "上一个周末"])
        return has_level and has_weekend and (has_recent_weekend or has_ref)

    @staticmethod
    def _is_weekday_percentile_rank_query(user_query: str) -> bool:
        q = user_query or ""
        if not q:
            return False
        has_level = any(k in q for k in ["处于什么水平", "什么水平", "处于什么位置", "高低水平", "分位", "百分位"])
        has_weekday = bool(PlanningAgent._parse_weekdays(q))
        has_recent_weeks = bool(re.search(r"近\s*\d+\s*(?:个)?\s*周", q))
        has_ref = any(k in q for k in ["昨天", "昨日", "今天", "今日"])
        return has_level and has_weekday and has_recent_weeks and has_ref

    @staticmethod
    def _extract_explicit_time_window(user_query: str, today: datetime.date) -> tuple[str, str] | None:
        q = user_query or ""
        sanitized = re.sub(r"(昨天|昨日|今天|今日|本周|上周|本月|上月|今年|去年|前年)", " ", q)
        return PlanningAgent._parse_time_window(sanitized, today)

    def _build_yesterday_vs_range_daily_mean_plans(self, user_query: str) -> list[dict] | None:
        q = user_query or ""
        if not q:
            return None
        has_compare = any(k in q for k in ["对比", "相比", "对照", "较"])
        has_yesterday = any(k in q for k in ["昨天", "昨日"])
        has_mean = any(k in q for k in ["日均", "均值", "平均值", "平均"])
        if not (has_compare and has_yesterday and has_mean):
            return None

        today = datetime.date.today()
        explicit_window = self._extract_explicit_time_window(q, today)
        if not explicit_window:
            return None

        metric_defaults = self._metric_defaults(q)
        if not metric_defaults:
            return None

        range_start, range_end = explicit_window
        start_date = datetime.date.fromisoformat(range_start)
        end_date = datetime.date.fromisoformat(range_end)
        window_days = max(1, (end_date - start_date).days)
        time_field = metric_defaults["time_field"]
        value_metric = metric_defaults["metric"]
        yesterday_start = (today - datetime.timedelta(days=1)).isoformat()
        yesterday_end = today.isoformat()

        yesterday_plan = self._normalize_plan(
            {
                "dataset": metric_defaults["dataset"],
                "metric": value_metric,
                "time": {"field": time_field, "start": yesterday_start, "end": yesterday_end},
                "dimensions": [],
                "filters": [{"field": time_field, "op": "!=", "value": None}],
                "comparison": {"type": "none"},
                "question": "昨天的锁单数",
            }
        )
        mean_plan = self._normalize_plan(
            {
                "dataset": metric_defaults["dataset"],
                "metric": value_metric,
                "time": {"field": time_field, "start": range_start, "end": range_end},
                "dimensions": [time_field],
                "filters": [{"field": time_field, "op": "!=", "value": None}],
                "comparison": {"type": "none"},
                "statistics": {
                    "type": "daily_mean",
                    "time_field": time_field,
                    "window_days": window_days,
                    "value_metric": value_metric,
                },
                "question": "指定区间日均锁单数",
            }
        )
        return [yesterday_plan, mean_plan]

    def _build_weekly_decline_ratio_plan(self, user_query: str) -> dict:
        today = datetime.date.today()
        weeks = self._parse_recent_weeks(user_query) or 10
        start = today - datetime.timedelta(days=weeks * 7)
        end = today
        weekdays = self._parse_weekdays(user_query) or [4, 5]
        time_field = "Assign Time 年/月/日"
        numerator = {"field": "下发线索当日锁单数 (门店)", "agg": "sum", "alias": "门店当日锁单数"}
        denominator = {"field": "下发线索数 (门店)", "agg": "sum", "alias": "门店线索数"}
        plan = {
            "dataset": "assign_data",
            "metric": numerator,
            "time": {"field": time_field, "start": start.isoformat(), "end": end.isoformat()},
            "dimensions": [time_field],
            "filters": [],
            "comparison": {"type": "none"},
            "statistics": {
                "type": "weekly_decline_ratio",
                "time_field": time_field,
                "window_weeks": weeks,
                "weekdays": weekdays,
                "numerator_metric": numerator,
                "denominator_metric": denominator,
            },
        }
        return self._fill_defaults(self._normalize_plan(plan), user_query)

    def _build_daily_threshold_count_plan(self, user_query: str) -> dict | None:
        metric_defaults = self._metric_defaults(user_query)
        threshold_cond = self._parse_threshold_condition(user_query)
        if not metric_defaults or not threshold_cond:
            return None
        op, threshold = threshold_cond
        today = datetime.date.today()
        days = self._parse_recent_days(user_query) or 30
        start = today - datetime.timedelta(days=days)
        end = today
        time_field = metric_defaults["time_field"]
        value_metric = metric_defaults["metric"]

        plan = {
            "dataset": metric_defaults["dataset"],
            "metric": value_metric,
            "time": {"field": time_field, "start": start.isoformat(), "end": end.isoformat()},
            "dimensions": [time_field],
            "filters": [{"field": time_field, "op": "!=", "value": None}],
            "comparison": {"type": "none"},
            "statistics": {
                "type": "daily_threshold_count",
                "time_field": time_field,
                "window_days": days,
                "op": op,
                "threshold": threshold,
                "value_metric": value_metric,
            },
        }
        return self._fill_defaults(self._normalize_plan(plan), user_query)

    def _build_daily_mean_plan(self, user_query: str) -> dict | None:
        metric_defaults = self._metric_defaults(user_query)
        if not metric_defaults:
            return None
        today = datetime.date.today()
        explicit_window = self._extract_explicit_time_window(user_query, today)
        if explicit_window:
            start_s, end_s = explicit_window
            start = datetime.date.fromisoformat(start_s)
            end = datetime.date.fromisoformat(end_s)
            days = max(1, (end - start).days)
        else:
            macro_window = self._parse_time_window_with_business(user_query, today)
            if macro_window:
                start_s, end_s = macro_window
                start = datetime.date.fromisoformat(start_s)
                end = datetime.date.fromisoformat(end_s)
                days = max(1, (end - start).days)
            else:
                days = self._parse_recent_days(user_query) or 30
                start = today - datetime.timedelta(days=days)
                end = today
        time_field = metric_defaults["time_field"]
        value_metric = metric_defaults["metric"]
        plan = {
            "dataset": metric_defaults["dataset"],
            "metric": value_metric,
            "time": {"field": time_field, "start": start.isoformat(), "end": end.isoformat()},
            "dimensions": [time_field],
            "filters": [{"field": time_field, "op": "!=", "value": None}],
            "comparison": {"type": "none"},
            "statistics": {
                "type": "daily_mean",
                "time_field": time_field,
                "window_days": days,
                "value_metric": value_metric,
            },
        }
        return self._fill_defaults(self._normalize_plan(plan), user_query)

    def _build_daily_mean_median_plan(self, user_query: str) -> dict | None:
        metric_defaults = self._metric_defaults(user_query)
        if not metric_defaults:
            return None
        today = datetime.date.today()
        explicit_window = self._extract_explicit_time_window(user_query, today)
        if explicit_window:
            start_s, end_s = explicit_window
            start = datetime.date.fromisoformat(start_s)
            end = datetime.date.fromisoformat(end_s)
            days = max(1, (end - start).days)
        else:
            macro_window = self._parse_time_window_with_business(user_query, today)
            if macro_window:
                start_s, end_s = macro_window
                start = datetime.date.fromisoformat(start_s)
                end = datetime.date.fromisoformat(end_s)
                days = max(1, (end - start).days)
            else:
                days = self._parse_recent_days(user_query) or 30
                start = today - datetime.timedelta(days=days)
                end = today
        time_field = metric_defaults["time_field"]
        value_metric = metric_defaults["metric"]
        plan = {
            "dataset": metric_defaults["dataset"],
            "metric": value_metric,
            "time": {"field": time_field, "start": start.isoformat(), "end": end.isoformat()},
            "dimensions": [time_field],
            "filters": [{"field": time_field, "op": "!=", "value": None}],
            "comparison": {"type": "none"},
            "statistics": {
                "type": "daily_mean_median",
                "time_field": time_field,
                "window_days": days,
                "value_metric": value_metric,
            },
        }
        return self._fill_defaults(self._normalize_plan(plan), user_query)

    def _build_trend_summary_plan(self, user_query: str) -> dict | None:
        metric_defaults = self._metric_defaults(user_query)
        if not metric_defaults:
            return None
        today = datetime.date.today()
        explicit_window = self._extract_explicit_time_window(user_query, today)
        if explicit_window:
            start_s, end_s = explicit_window
            start = datetime.date.fromisoformat(start_s)
            end = datetime.date.fromisoformat(end_s)
            days = max(1, (end - start).days)
        else:
            macro_window = self._parse_time_window_with_business(user_query, today)
            if macro_window:
                start_s, end_s = macro_window
                start = datetime.date.fromisoformat(start_s)
                end = datetime.date.fromisoformat(end_s)
                days = max(1, (end - start).days)
            else:
                days = self._parse_recent_days(user_query) or 10
                start = today - datetime.timedelta(days=days)
                end = today
        time_field = metric_defaults["time_field"]
        value_metric = metric_defaults["metric"]
        plan = {
            "dataset": metric_defaults["dataset"],
            "metric": value_metric,
            "time": {"field": time_field, "start": start.isoformat(), "end": end.isoformat()},
            "dimensions": [time_field],
            "filters": [{"field": time_field, "op": "!=", "value": None}],
            "comparison": {"type": "none"},
            "statistics": {
                "type": "trend_summary",
                "time_field": time_field,
                "window_days": days,
                "value_metric": value_metric,
            },
        }
        return self._fill_defaults(self._normalize_plan(plan), user_query)

    def _build_contribution_summary_plan(self, user_query: str) -> dict | None:
        metric_defaults = self._metric_defaults(user_query)
        if not metric_defaults:
            return None
        today = datetime.date.today()
        days = self._parse_recent_days(user_query) or 10
        start = today - datetime.timedelta(days=days)
        end = today
        time_field = metric_defaults["time_field"]
        value_metric = metric_defaults["metric"]
        dimension_field = "series"
        q = (user_query or "").replace(" ", "")
        if any(k in q for k in ["门店"]):
            dimension_field = "store_name"
        elif any(k in q for k in ["门店城市", "店城"]):
            dimension_field = "store_city"
        elif any(k in q for k in ["上牌城市", "牌照城市", "城市"]):
            dimension_field = "license_city"
        elif any(k in q for k in ["车型", "车系", "系列"]):
            dimension_field = "series"
        plan = {
            "dataset": metric_defaults["dataset"],
            "metric": value_metric,
            "time": {"field": time_field, "start": start.isoformat(), "end": end.isoformat()},
            "dimensions": [time_field, dimension_field],
            "filters": [{"field": time_field, "op": "!=", "value": None}],
            "comparison": {"type": "none"},
            "statistics": {
                "type": "contribution_summary",
                "time_field": time_field,
                "dimension_field": dimension_field,
                "window_days": days,
                "top_k": 10,
                "value_metric": value_metric,
            },
        }
        return self._fill_defaults(self._normalize_plan(plan), user_query)

    def _build_daily_percentile_rank_plan(self, user_query: str) -> dict | None:
        metric_defaults = self._metric_defaults(user_query)
        if not metric_defaults:
            return None
        today = datetime.date.today()
        days = self._parse_recent_days(user_query) or 30
        start = today - datetime.timedelta(days=days)
        end = today
        time_field = metric_defaults["time_field"]
        value_metric = metric_defaults["metric"]
        reference_date = (today - datetime.timedelta(days=1)).isoformat() if any(k in user_query for k in ["昨天", "昨日"]) else today.isoformat()
        plan = {
            "dataset": metric_defaults["dataset"],
            "metric": value_metric,
            "time": {"field": time_field, "start": start.isoformat(), "end": end.isoformat()},
            "dimensions": [time_field],
            "filters": [{"field": time_field, "op": "!=", "value": None}],
            "comparison": {"type": "none"},
            "statistics": {
                "type": "daily_percentile_rank",
                "time_field": time_field,
                "window_days": days,
                "reference_date": reference_date,
                "value_metric": value_metric,
            },
        }
        return self._fill_defaults(self._normalize_plan(plan), user_query)

    def _build_weekend_percentile_rank_plan(self, user_query: str) -> dict | None:
        metric_defaults = self._metric_defaults(user_query)
        if not metric_defaults:
            return None
        today = datetime.date.today()
        weekends = self._parse_recent_weekends(user_query) or 10
        start = today - datetime.timedelta(days=(weekends * 7 + 14))
        end = today + datetime.timedelta(days=1)
        time_field = metric_defaults["time_field"]
        value_metric = metric_defaults["metric"]
        reference_date = today.isoformat()
        plan = {
            "dataset": metric_defaults["dataset"],
            "metric": value_metric,
            "time": {"field": time_field, "start": start.isoformat(), "end": end.isoformat()},
            "dimensions": [time_field],
            "filters": [{"field": time_field, "op": "!=", "value": None}],
            "comparison": {"type": "none"},
            "statistics": {
                "type": "weekend_percentile_rank",
                "time_field": time_field,
                "window_weekends": weekends,
                "reference_date": reference_date,
                "value_metric": value_metric,
            },
            "question": "周末锁单数在近N个周末中的分位",
        }
        return self._fill_defaults(self._normalize_plan(plan), user_query)

    def _build_weekday_percentile_rank_plan(self, user_query: str) -> dict | None:
        metric_defaults = self._metric_defaults(user_query)
        if not metric_defaults:
            return None
        today = datetime.date.today()
        weeks = self._parse_recent_weeks(user_query) or 10
        weekdays = self._parse_weekdays(user_query) or [7]
        start = today - datetime.timedelta(days=(weeks * 7 + 7))
        end = today + datetime.timedelta(days=1)
        time_field = metric_defaults["time_field"]
        value_metric = metric_defaults["metric"]
        reference_date = (
            (today - datetime.timedelta(days=1)).isoformat()
            if any(k in user_query for k in ["昨天", "昨日"])
            else today.isoformat()
        )
        plan = {
            "dataset": metric_defaults["dataset"],
            "metric": value_metric,
            "time": {"field": time_field, "start": start.isoformat(), "end": end.isoformat()},
            "dimensions": [time_field],
            "filters": [{"field": time_field, "op": "!=", "value": None}],
            "comparison": {"type": "none"},
            "statistics": {
                "type": "weekday_percentile_rank",
                "time_field": time_field,
                "window_weeks": weeks,
                "weekdays": weekdays,
                "reference_date": reference_date,
                "value_metric": value_metric,
            },
            "question": "指定周内日锁单数在近N周中的分位",
        }
        return self._fill_defaults(self._normalize_plan(plan), user_query)

    @staticmethod
    def _statistics_plan_valid(statistics: dict, plan: dict) -> bool:
        stype = statistics.get("type")
        dims = plan.get("dimensions")
        if not isinstance(dims, list):
            dims = []
        if stype == "weekly_decline_ratio":
            time_field = statistics.get("time_field") or (plan.get("time", {}) or {}).get("field")
            weekdays = statistics.get("weekdays")
            numerator = statistics.get("numerator_metric")
            denominator = statistics.get("denominator_metric")
            if not isinstance(time_field, str) or not time_field:
                return False
            if time_field not in dims:
                return False
            if not isinstance(weekdays, list) or not weekdays:
                return False
            if not isinstance(numerator, dict) or not isinstance(denominator, dict):
                return False
            if not numerator.get("field") or not denominator.get("field"):
                return False
            if not numerator.get("agg") or not denominator.get("agg"):
                return False
            if (
                numerator.get("field") == denominator.get("field")
                and numerator.get("agg") == denominator.get("agg")
                and (numerator.get("alias") or "") == (denominator.get("alias") or "")
            ):
                return False
            return True

        if stype == "daily_threshold_count":
            time_field = statistics.get("time_field") or (plan.get("time", {}) or {}).get("field")
            op = statistics.get("op")
            threshold = statistics.get("threshold")
            value_metric = statistics.get("value_metric")
            if not isinstance(time_field, str) or not time_field:
                return False
            if time_field not in dims:
                return False
            if op not in {">", ">=", "<", "<=", "==", "!="}:
                return False
            if not isinstance(value_metric, dict):
                return False
            if not value_metric.get("field") or not value_metric.get("agg"):
                return False
            try:
                float(threshold)
            except Exception:
                return False
            return True

        if stype == "daily_mean":
            time_field = statistics.get("time_field") or (plan.get("time", {}) or {}).get("field")
            value_metric = statistics.get("value_metric")
            if not isinstance(time_field, str) or not time_field:
                return False
            if time_field not in dims:
                return False
            if not isinstance(value_metric, dict):
                return False
            if not value_metric.get("field") or not value_metric.get("agg"):
                return False
            return True

        if stype == "daily_mean_median":
            time_field = statistics.get("time_field") or (plan.get("time", {}) or {}).get("field")
            value_metric = statistics.get("value_metric")
            if not isinstance(time_field, str) or not time_field:
                return False
            if time_field not in dims:
                return False
            if not isinstance(value_metric, dict):
                return False
            if not value_metric.get("field") or not value_metric.get("agg"):
                return False
            return True

        if stype == "trend_summary":
            time_field = statistics.get("time_field") or (plan.get("time", {}) or {}).get("field")
            value_metric = statistics.get("value_metric")
            window_days = statistics.get("window_days")
            if not isinstance(time_field, str) or not time_field:
                return False
            if time_field not in dims:
                return False
            if not isinstance(value_metric, dict):
                return False
            if not value_metric.get("field") or not value_metric.get("agg"):
                return False
            try:
                window_days = int(window_days)
            except Exception:
                return False
            return window_days > 0

        if stype == "contribution_summary":
            time_field = statistics.get("time_field") or (plan.get("time", {}) or {}).get("field")
            value_metric = statistics.get("value_metric")
            window_days = statistics.get("window_days")
            dimension_field = statistics.get("dimension_field")
            if not isinstance(time_field, str) or not time_field:
                return False
            if time_field not in dims:
                return False
            if not isinstance(dimension_field, str) or not dimension_field:
                return False
            if dimension_field not in dims:
                return False
            if not isinstance(value_metric, dict):
                return False
            if not value_metric.get("field") or not value_metric.get("agg"):
                return False
            try:
                window_days = int(window_days)
            except Exception:
                return False
            return window_days > 0

        if stype == "category_share":
            category_field = statistics.get("category_field")
            if not isinstance(category_field, str) or not category_field:
                return False
            if category_field not in dims:
                return False
            top_k = statistics.get("top_k")
            if top_k is not None:
                try:
                    _ = int(top_k)
                except Exception:
                    return False
            return True

        if stype == "weekday_percentile_rank":
            time_field = statistics.get("time_field") or (plan.get("time", {}) or {}).get("field")
            value_metric = statistics.get("value_metric")
            weekdays = statistics.get("weekdays")
            window_weeks = statistics.get("window_weeks")
            reference_date = statistics.get("reference_date")
            if not isinstance(time_field, str) or not time_field:
                return False
            if time_field not in dims:
                return False
            if not isinstance(value_metric, dict):
                return False
            if not value_metric.get("field") or not value_metric.get("agg"):
                return False
            if not isinstance(weekdays, list) or not weekdays:
                return False
            try:
                window_weeks = int(window_weeks)
            except Exception:
                return False
            if reference_date is not None and not isinstance(reference_date, str):
                return False
            return window_weeks > 0

        if stype == "daily_percentile_rank":
            time_field = statistics.get("time_field") or (plan.get("time", {}) or {}).get("field")
            value_metric = statistics.get("value_metric")
            reference_date = statistics.get("reference_date")
            if not isinstance(time_field, str) or not time_field:
                return False
            if time_field not in dims:
                return False
            if not isinstance(value_metric, dict):
                return False
            if not value_metric.get("field") or not value_metric.get("agg"):
                return False
            if reference_date is not None and not isinstance(reference_date, str):
                return False
            return True

        if stype == "weekend_percentile_rank":
            time_field = statistics.get("time_field") or (plan.get("time", {}) or {}).get("field")
            value_metric = statistics.get("value_metric")
            reference_date = statistics.get("reference_date")
            if not isinstance(time_field, str) or not time_field:
                return False
            if time_field not in dims:
                return False
            if not isinstance(value_metric, dict):
                return False
            if not value_metric.get("field") or not value_metric.get("agg"):
                return False
            if reference_date is not None and not isinstance(reference_date, str):
                return False
            return True

        return False

    @staticmethod
    def _normalize_plan(plan: dict) -> dict:
        dataset = plan.get("dataset")
        if isinstance(dataset, str):
            lowered = dataset.lower()
            if lowered.endswith(".parquet") or lowered.endswith(".csv"):
                plan["dataset"] = dataset.rsplit(".", 1)[0]

        filters = plan.get("filters")
        if not isinstance(filters, list):
            filters = []

        normalized_filters: list[dict] = []
        seen_filters: set[tuple[str, str, str]] = set()
        for f in filters:
            if not isinstance(f, dict):
                continue
            field = f.get("field")
            op = f.get("op")
            value = f.get("value", None)

            if field in {"store_city", "license_city"} and isinstance(value, str):
                raw = value.strip()
                if "市" in raw:
                    raw = raw.split("市", 1)[0] + "市"
                else:
                    m_city = re.search(r"([\u4e00-\u9fff]{2,8})", raw)
                    if m_city:
                        raw = m_city.group(1)

                base = raw[:-1] if raw.endswith("市") and len(raw) > 1 else raw
                if base:
                    value = base

            if op in {"not null", "not_null", "is not null", "is_not_null"}:
                normalized = {"field": field, "op": "!=", "value": None}
                key = (str(field), "!=", "None")
                if key not in seen_filters:
                    normalized_filters.append(normalized)
                    seen_filters.add(key)
                continue
            if op in {"null", "is null", "is_null"}:
                normalized = {"field": field, "op": "==", "value": None}
                key = (str(field), "==", "None")
                if key not in seen_filters:
                    normalized_filters.append(normalized)
                    seen_filters.add(key)
                continue
            if op in {"=", "eq"}:
                normalized = {"field": field, "op": "==", "value": value}
                key = (str(field), "==", repr(value))
                if key not in seen_filters:
                    normalized_filters.append(normalized)
                    seen_filters.add(key)
                continue

            if field in {"store_city", "license_city"} and op == "==" and isinstance(value, str) and value:
                variants = []
                base = value[:-1] if value.endswith("市") and len(value) > 1 else value
                if base:
                    variants.append(base)
                    variants.append(f"{base}市")
                variants = list(dict.fromkeys(variants))
                normalized = {"field": field, "op": "in", "value": variants}
                key = (str(field), "in", repr(variants))
                if key not in seen_filters:
                    normalized_filters.append(normalized)
                    seen_filters.add(key)
                continue

            if op == "!=" and "value" not in f:
                normalized = {"field": field, "op": "!=", "value": None}
                key = (str(field), "!=", "None")
                if key not in seen_filters:
                    normalized_filters.append(normalized)
                    seen_filters.add(key)
                continue

            normalized = {"field": field, "op": op, "value": value}
            key = (str(field), str(op), repr(value))
            if key not in seen_filters:
                normalized_filters.append(normalized)
                seen_filters.add(key)

        plan["filters"] = normalized_filters

        dims = plan.get("dimensions")
        if dims is None:
            plan["dimensions"] = []
        elif not isinstance(dims, list):
            plan["dimensions"] = [str(dims)]

        comparison = plan.get("comparison")
        if not isinstance(comparison, dict):
            plan["comparison"] = {"type": "none"}
        else:
            ctype = comparison.get("type")
            if ctype not in {"none", "yoy", "wow", "dod"}:
                plan["comparison"] = {"type": "none"}

        time = plan.get("time")
        if not isinstance(time, dict):
            plan["time"] = {}

        metric = plan.get("metric")
        if not isinstance(metric, dict):
            plan["metric"] = {}

        statistics = plan.get("statistics")
        if statistics is not None and not isinstance(statistics, dict):
            plan["statistics"] = {}
        elif isinstance(statistics, dict):
            stype = statistics.get("type")
            if stype not in {
                "weekly_decline_ratio",
                "daily_threshold_count",
                "daily_mean",
                "daily_mean_median",
                "trend_summary",
                "contribution_summary",
                "category_share",
                "daily_percentile_rank",
                "weekend_percentile_rank",
                "weekday_percentile_rank",
            }:
                plan["statistics"] = {}
            elif stype == "weekly_decline_ratio":
                wdays = statistics.get("weekdays")
                if isinstance(wdays, list):
                    normalized_wdays = []
                    for w in wdays:
                        if isinstance(w, (int, float, str)) and str(w).isdigit():
                            iv = int(w)
                            if 1 <= iv <= 7:
                                normalized_wdays.append(iv)
                    statistics["weekdays"] = sorted(list(dict.fromkeys(normalized_wdays)))
                wweeks = statistics.get("window_weeks")
                if isinstance(wweeks, str) and wweeks.isdigit():
                    statistics["window_weeks"] = int(wweeks)
            elif stype == "daily_threshold_count":
                op = statistics.get("op")
                if op not in {">", ">=", "<", "<=", "==", "!="}:
                    statistics["op"] = ">"
                threshold = statistics.get("threshold")
                try:
                    statistics["threshold"] = float(threshold)
                except Exception:
                    statistics["threshold"] = 0.0
                wdays = statistics.get("window_days")
                if isinstance(wdays, str) and wdays.isdigit():
                    statistics["window_days"] = int(wdays)
            elif stype == "daily_mean":
                wdays = statistics.get("window_days")
                if isinstance(wdays, str) and wdays.isdigit():
                    statistics["window_days"] = int(wdays)
            elif stype == "daily_mean_median":
                wdays = statistics.get("window_days")
                if isinstance(wdays, str) and wdays.isdigit():
                    statistics["window_days"] = int(wdays)
            elif stype == "trend_summary":
                wdays = statistics.get("window_days")
                if isinstance(wdays, str) and wdays.isdigit():
                    statistics["window_days"] = int(wdays)
            elif stype == "contribution_summary":
                wdays = statistics.get("window_days")
                if isinstance(wdays, str) and wdays.isdigit():
                    statistics["window_days"] = int(wdays)
                top_k = statistics.get("top_k")
                if isinstance(top_k, str) and top_k.isdigit():
                    statistics["top_k"] = int(top_k)
            elif stype == "category_share":
                top_k = statistics.get("top_k")
                if isinstance(top_k, str) and top_k.isdigit():
                    statistics["top_k"] = int(top_k)
            elif stype == "daily_percentile_rank":
                wdays = statistics.get("window_days")
                if isinstance(wdays, str) and wdays.isdigit():
                    statistics["window_days"] = int(wdays)
            elif stype == "weekend_percentile_rank":
                wends = statistics.get("window_weekends")
                if isinstance(wends, str) and wends.isdigit():
                    statistics["window_weekends"] = int(wends)
            elif stype == "weekday_percentile_rank":
                wdays = statistics.get("weekdays")
                if isinstance(wdays, list):
                    normalized = []
                    for w in wdays:
                        if isinstance(w, (int, float, str)) and str(w).isdigit():
                            iv = int(w)
                            if 1 <= iv <= 7:
                                normalized.append(iv)
                    statistics["weekdays"] = sorted(list(dict.fromkeys(normalized)))
                wweeks = statistics.get("window_weeks")
                if isinstance(wweeks, str) and wweeks.isdigit():
                    statistics["window_weeks"] = int(wweeks)
            if not PlanningAgent._statistics_plan_valid(statistics, plan):
                plan["statistics"] = {}

        fast_path = plan.get("fast_path")
        if fast_path is not None and not isinstance(fast_path, dict):
            plan["fast_path"] = {}
        elif isinstance(fast_path, dict):
            fp_type = fast_path.get("type")
            if fp_type not in {"numeric_ratio", "current_iso_week", "small_talk_contextual", "data_update", "data_sync"}:
                plan["fast_path"] = {}
            elif fp_type == "numeric_ratio":
                try:
                    fast_path["current"] = float(fast_path.get("current"))
                    fast_path["base"] = float(fast_path.get("base"))
                except Exception:
                    plan["fast_path"] = {}

        analysis_intent = plan.get("analysis_intent")
        if not isinstance(analysis_intent, dict):
            plan["analysis_intent"] = {}
        else:
            atype = analysis_intent.get("type")
            valid_intents = {
                "share_breakdown", "attribute_penetration", "attribute_distribution",
                "active_store", "retained_intention", "retained_intention_conversion",
                "age_cohort", "city_tier", "province_topk", "store_avg_lock",
                "assign_conversion", "weighted_lead_conversion", "mature_lock_prediction",
            }
            if atype not in valid_intents:
                plan["analysis_intent"] = {}

        post_process = plan.get("post_process")
        if not isinstance(post_process, list):
            plan["post_process"] = []
        else:
                normalized_pp: list[dict] = []
                for pp in post_process:
                    if not isinstance(pp, dict):
                        continue
                    pptype = pp.get("type")
                    if pptype == "window_share":
                        partition_by = pp.get("partition_by")
                        value_field = pp.get("value_field")
                        alias = str(pp.get("alias") or "")
                        if isinstance(partition_by, list) and partition_by and isinstance(value_field, str) and value_field and alias:
                            normalized_pp.append({
                                "type": "window_share",
                                "partition_by": list(partition_by),
                                "value_field": value_field,
                                "alias": alias,
                            })
                    elif pptype == "ratio":
                        numerator = pp.get("numerator")
                        denominator = pp.get("denominator")
                        alias = str(pp.get("alias") or "")
                        if isinstance(numerator, str) and isinstance(denominator, str) and alias:
                            normalized_pp.append({
                                "type": "ratio",
                                "numerator": numerator,
                                "denominator": denominator,
                                "alias": alias,
                            })
                plan["post_process"] = normalized_pp

        return plan

    def _rule_based_plan(self, user_query: str) -> dict | None:
        today = datetime.date.today()
        comparison_type = self._parse_comparison_type(user_query)
        metric_defaults = self._metric_defaults(user_query)
        if not metric_defaults:
            return None

        time_window = self._parse_time_window_with_business(user_query, today) or (
            (today - datetime.timedelta(days=1)).isoformat(),
            today.isoformat(),
        )

        start, end = time_window
        time_field = metric_defaults["time_field"]
        non_null_field = metric_defaults.get("non_null_field")

        plan = {
            "dataset": metric_defaults["dataset"],
            "metric": metric_defaults["metric"],
            "time": {"field": time_field, "start": start, "end": end},
            "dimensions": [],
            "filters": [],
            "comparison": {"type": comparison_type},
        }

        if non_null_field:
            plan["filters"].append({"field": non_null_field, "op": "!=", "value": None})

        extra_filters = metric_defaults.get("extra_filters")
        if isinstance(extra_filters, list):
            plan["filters"].extend(extra_filters)

        return self._normalize_plan(plan)

    @staticmethod
    def _split_user_query(user_query: str) -> list[str]:
        q = (user_query or "").strip()
        if not q:
            return []
        parts = re.split(r"[？?\n；;]+", q)
        return [p.strip() for p in parts if p and p.strip()]

    @staticmethod
    def _looks_like_time_only_clause(text: str) -> bool:
        q = (text or "").strip()
        if not q:
            return False
        q_nospace = q.replace(" ", "")
        has_date = bool(re.search(r"\d{4}-\d{2}-\d{2}", q_nospace)) or bool(re.search(r"\d{2,4}年\d{1,2}月\d{1,2}", q_nospace))
        has_time_keyword = any(k in q_nospace for k in ["截至", "截止", "到", "至", "本月", "上月", "今年", "去年", "昨天", "昨日", "近"])
        if not (has_date or has_time_keyword):
            return False
        metric_markers = ["锁单", "交付", "开票", "小订", "意向金", "大定", "定金", "下发线索", "在营门店", "留存小订", "订单"]
        if any(k in q_nospace for k in metric_markers):
            return False
        if PlanningAgent._infer_series_tokens(q_nospace):
            return False
        return True

    def _finalize_plans(self, plans: list[dict], user_query: str) -> list[dict]:
        finalized: list[dict] = []
        for plan in plans:
            if not isinstance(plan, dict) or not plan:
                continue
            q = plan.get("question") or user_query
            semantic_q = user_query if q == user_query else f"{user_query}；{q}"
            normalized = self._fill_defaults(self._normalize_plan(plan), semantic_q)
            has_compare = any(k in semantic_q for k in ["对比", "相比", "对照", "较"])
            if self._is_weekday_percentile_rank_query(semantic_q):
                stat = normalized.get("statistics")
                if not isinstance(stat, dict) or stat.get("type") != "weekday_percentile_rank":
                    weekday_plan = self._build_weekday_percentile_rank_plan(semantic_q)
                    if isinstance(weekday_plan, dict) and weekday_plan:
                        weekday_plan["question"] = q
                        finalized.append(weekday_plan)
                        continue
            if self._is_weekend_percentile_rank_query(semantic_q):
                stat = normalized.get("statistics")
                if not isinstance(stat, dict) or stat.get("type") != "weekend_percentile_rank":
                    weekend_plan = self._build_weekend_percentile_rank_plan(semantic_q)
                    if isinstance(weekend_plan, dict) and weekend_plan:
                        weekend_plan["question"] = q
                        finalized.append(weekend_plan)
                        continue
            if self._is_share_breakdown_query(semantic_q) and not has_compare:
                stat = normalized.get("statistics")
                if not isinstance(stat, dict) or stat.get("type") not in ("category_share", "weekly_decline_ratio", "daily_mean"):
                    sb_plan = self._build_share_breakdown_plan(semantic_q)
                    if isinstance(sb_plan, dict) and sb_plan:
                        sb_plan["question"] = q
                        finalized.append(sb_plan)
                        continue
            if self._is_category_share_query(semantic_q) and not has_compare:
                stat = normalized.get("statistics")
                if not isinstance(stat, dict) or stat.get("type") != "category_share":
                    share_plan = self._build_category_share_plan(semantic_q)
                    if isinstance(share_plan, dict) and share_plan:
                        share_plan["question"] = q
                        finalized.append(share_plan)
                        continue
            if self._is_contribution_summary_query(semantic_q) and not has_compare:
                stat = normalized.get("statistics")
                if not isinstance(stat, dict) or stat.get("type") != "contribution_summary":
                    contrib_plan = self._build_contribution_summary_plan(semantic_q)
                    if isinstance(contrib_plan, dict) and contrib_plan:
                        contrib_plan["question"] = q
                        finalized.append(contrib_plan)
                        continue
            if self._is_trend_summary_query(semantic_q) and not has_compare:
                stat = normalized.get("statistics")
                if not isinstance(stat, dict) or stat.get("type") != "trend_summary":
                    trend_plan = self._build_trend_summary_plan(semantic_q)
                    if isinstance(trend_plan, dict) and trend_plan:
                        trend_plan["question"] = q
                        finalized.append(trend_plan)
                        continue
            if self._is_daily_mean_median_query(semantic_q) and not has_compare:
                stat = normalized.get("statistics")
                if not isinstance(stat, dict) or stat.get("type") != "daily_mean_median":
                    summary_plan = self._build_daily_mean_median_plan(semantic_q)
                    if isinstance(summary_plan, dict) and summary_plan:
                        summary_plan["question"] = q
                        finalized.append(summary_plan)
                        continue
            if self._is_daily_mean_query(semantic_q):
                stat = normalized.get("statistics")
                if has_compare and any(k in semantic_q for k in ["昨天", "昨日"]):
                    pair = self._build_yesterday_vs_range_daily_mean_plans(semantic_q)
                    if isinstance(pair, list) and pair:
                        finalized.extend(pair)
                        continue
                if not has_compare and (not isinstance(stat, dict) or stat.get("type") != "daily_mean"):
                    daily_plan = self._build_daily_mean_plan(semantic_q)
                    if isinstance(daily_plan, dict) and daily_plan:
                        daily_plan["question"] = q
                        finalized.append(daily_plan)
                        continue
            if self._is_daily_percentile_rank_query(semantic_q):
                stat = normalized.get("statistics")
                if not isinstance(stat, dict) or stat.get("type") != "daily_percentile_rank":
                    percentile_plan = self._build_daily_percentile_rank_plan(semantic_q)
                    if isinstance(percentile_plan, dict) and percentile_plan:
                        percentile_plan["question"] = q
                        finalized.append(percentile_plan)
                        continue
            normalized["question"] = q
            finalized.append(normalized)
        return [p for p in finalized if isinstance(p, dict) and p]

    def create_plans(self, user_query: str, memory_context: dict | None = None) -> list[dict]:
        parts = self._split_user_query(user_query) or [user_query]
        if len(parts) >= 2 and PlanningAgent._looks_like_time_only_clause(parts[0]):
            merged = f"{parts[0]} {parts[1]}".strip()
            rest = parts[2:] if len(parts) > 2 else []
            parts = [merged, *rest]
        fp = self._parse_fast_path_query(user_query)
        if isinstance(fp, dict) and fp.get("type"):
            self.last_planning_error = ""
            return [
                self._normalize_plan(
                    {
                        "question": user_query,
                        "dataset": "order_data",
                        "metric": {"field": "order_number", "agg": "count", "alias": "count", "business_name": "订单计数"},
                        "time": {
                            "field": "order_create_time",
                            "start": datetime.date.today().isoformat(),
                            "end": (datetime.date.today() + datetime.timedelta(days=1)).isoformat(),
                        },
                        "dimensions": [],
                        "filters": [],
                        "comparison": {"type": "none"},
                        "fast_path": fp,
                    }
                )
            ]
        for part in parts:
            if self._should_sales_clarify(part):
                return [{"question": part, "clarification": self._sales_clarification(part)}]
            need, city = self._should_city_clarify(part)
            if need and city:
                return [{"question": part, "clarification": self._city_clarification(city, part)}]

        retained_plans: list[dict] = []
        retained_window = None
        if PlanningAgent._is_retained_intention_query(user_query):
            retained_window = self._resolve_retained_intention_time_window(user_query, datetime.date.today())
        for part in parts:
            retained = self._build_retained_intention_plan(part)
            if isinstance(retained, dict) and retained:
                if retained_window and isinstance(retained.get("time"), dict):
                    retained["time"]["start"], retained["time"]["end"] = retained_window
                retained["question"] = part
                retained_plans.append(retained)
        if retained_plans:
            self.last_planning_error = ""
            return self._finalize_plans(retained_plans, user_query)

        penetration_plan = self._build_penetration_plan(user_query)
        if isinstance(penetration_plan, dict) and penetration_plan:
            self.last_planning_error = ""
            return self._finalize_plans([penetration_plan], user_query)

        current_date = datetime.date.today().isoformat()
        memory_context = memory_context if isinstance(memory_context, dict) else {}
        memory_facts = memory_context.get("facts") if isinstance(memory_context.get("facts"), dict) else {}
        memory_working = memory_context.get("working_memory") if isinstance(memory_context.get("working_memory"), dict) else {}
        memory_text = (
            "执行记忆:\n"
            f"- 已有 facts: {json.dumps(memory_facts, ensure_ascii=False)}\n"
            f"- 当前 working_memory: {json.dumps(memory_working, ensure_ascii=False)}\n\n"
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "你是一个智能数据分析助手 (Planning Agent)。"
                    "你的任务是把用户问题转成可执行前的规划 DSL（包含时间范围、对比类型、拆解维度、过滤口径）。"
                    "不要直接回答结论，必须调用 create_planning_dsl 工具返回 plans。\n\n"
                    f"今天是: {current_date}\n\n"
                    "数据集与 Schema:\n"
                    f"{self.schema_md}\n\n"
                    "业务定义:\n"
                    f"{self.business_definition}\n\n"
                    "算子目录:\n"
                    f"{self.operator_catalog}\n\n"
                    "指标注册表:\n"
                    f"{self.metric_registry.to_metric_defaults_md()}\n\n"
                    f"{memory_text}"
                    "约束:\n"
                    "- 默认返回 1 个 plan；多子问题才拆多个，保持原顺序。\n"
                    "- 每个 plan 必须填写 question 字段。\n"
                    "- time.start/end 必须是 YYYY-MM-DD，end 为开区间。\n"
                    "- 遇到歧义（如销量口径、城市口径）必须 clarification.need=true。\n"
                    "- 口径定义以 Schema 文档为准，约束仅列 Schema 未覆盖的行为规则。\n"
                    "- 路由为 Intent-Driven：Fast Path > Operator Intents > Analysis Intents > Comparison/Statistics/Query。\n"
                    "- 算子类指标（即下文 算子目录 中列出的）必须设置 analysis_intent.type 为对应算子 intent。\n"
                    "- 意图驱动路由的 operator intents: active_store, retained_intention, retained_intention_conversion, age_cohort, city_tier, province_topk, store_avg_lock, assign_conversion, weighted_lead_conversion, mature_lock_prediction。\n"
                    "- 纯数字比较输出 fast_path={type:numeric_ratio,current,base}。\n"
                    "- 日期周序输出 fast_path={type:current_iso_week}。\n"
                    "- 闲聊致谢输出 fast_path={type:small_talk_contextual}。\n"
                    "- 用户出现‘试驾车’时 filters 必须含 order_type == 试驾车；出现‘用户车’时必须含 order_type == 用户车。\n"
                    "- 用户出现系列词（L6/L7/LS6/LS7/LS8/LS9）时，filters 应补充 series 约束。\n"
                    "- 若用户出现 CM0/CM1/CM2/DM0/DM1 等二级车型分组，使用 business_definition.series_group_logic（product_name 逻辑）生成 filters，禁止直接写到 series 字段。\n"
                    "- LS6/L6 是 series 车系，不要按 model_series_mapping 展开成 CM0/CM1/CM2/DM0/DM1；仅当用户明确问二级分组时才使用 series_group_logic。\n"
                    "- 用户问性别/男女比例时，默认 owner_gender；明确提到订单用户/订单性别时用 order_gender。\n"
                    "- 同比/年同比用 comparison.type=yoy；周环比=wow；日环比=dod。\n"
                    "- 时序统计输出 statistics：weekly_decline_ratio/daily_threshold_count/daily_mean/daily_mean_median/trend_summary/daily_percentile_rank/weekend_percentile_rank/weekday_percentile_rank，并补齐必需字段。\n"
                    "- 近 N 日/周/月 的趋势/走势/波动，优先 trend_summary，设 window_days 与 value_metric。\n"
                    "- 近 N 周的周日/周一..周日 水平，用 weekday_percentile_rank，设 window_weeks、weekdays、reference_date。\n"
                    "- 配置渗透率/选装率：analysis_intent.type=attribute_penetration，补齐 attribute_pattern、dimension_field。\n"
                    "- 配置分布/比例：analysis_intent.type=attribute_distribution，补齐 attribute_pattern、top_k。\n"
                    f"{TEMPLATE_CATALOG_MD}\n"
                ),
            },
            {"role": "user", "content": user_query},
        ]

        try:
            response = self.client.chat.completions.create(
                model=DEEPSEEK_PLANNER_MODEL,
                messages=messages,
                tools=[PLANNING_TOOL_SCHEMA],
                tool_choice={"type": "function", "function": {"name": "create_planning_dsl"}},
                temperature=0,
            )

            message = response.choices[0].message
            finish_reason = str(getattr(response.choices[0], "finish_reason", "") or "")
            tool_calls = message.tool_calls or []
            for tool_call in tool_calls:
                if tool_call.function.name != "create_planning_dsl":
                    continue
                try:
                    args = json.loads(tool_call.function.arguments or "{}")
                except Exception as e:
                    self.last_planning_error = f"planning_tool_args_parse_failed: {e.__class__.__name__}: {e}"
                    continue
                raw_plans = args.get("plans")
                clarification = args.get("clarification")
                if isinstance(clarification, dict) and clarification.get("need"):
                    self.last_planning_error = ""
                    return [{"question": user_query, "clarification": clarification}]
                if isinstance(raw_plans, list):
                    plans: list[dict] = []
                    for p in raw_plans:
                        if not isinstance(p, dict):
                            continue
                        plans.append(p)
                    self.last_planning_error = ""
                    return self._finalize_plans(plans, user_query)
                raw_plan = args.get("plan")
                if isinstance(raw_plan, dict):
                    self.last_planning_error = ""
                    return self._finalize_plans([raw_plan], user_query)

            content = message.content or ""
            try:
                obj = json.loads(content)
            except Exception as e:
                self.last_planning_error = f"planning_content_json_parse_failed: {e.__class__.__name__}: {e}"
                obj = None
            if isinstance(obj, dict) and isinstance(obj.get("plans"), list):
                plans: list[dict] = []
                for p in obj["plans"]:
                    if not isinstance(p, dict):
                        continue
                    plans.append(p)
                self.last_planning_error = ""
                return self._finalize_plans(plans, user_query)
            if isinstance(obj, dict) and isinstance(obj.get("clarification"), dict) and obj["clarification"].get("need"):
                self.last_planning_error = ""
                return [{"question": user_query, "clarification": obj["clarification"]}]
            if isinstance(obj, dict) and isinstance(obj.get("plan"), dict):
                self.last_planning_error = ""
                return self._finalize_plans([obj["plan"]], user_query)
            if not tool_calls:
                preview = (content or "").strip().replace("\n", " ")
                if len(preview) > 240:
                    preview = preview[:240] + "...(truncated)"
                self.last_planning_error = f"planning_no_tool_calls: finish_reason={finish_reason} content_preview={preview}"

                retry_messages = [
                    {
                        "role": "system",
                        "content": (
                            "你是一个智能数据分析助手 (Planning Agent)。"
                            "必须调用 create_planning_dsl 工具返回 plans 或 clarification。"
                            "不要输出任何非工具调用文本。"
                        ),
                    },
                    {"role": "user", "content": user_query},
                ]
                try:
                    retry = self.client.chat.completions.create(
                        model=DEEPSEEK_PLANNER_MODEL,
                        messages=retry_messages,
                        tools=[PLANNING_TOOL_SCHEMA],
                        tool_choice={"type": "function", "function": {"name": "create_planning_dsl"}},
                        temperature=0,
                    )
                    retry_msg = retry.choices[0].message
                    retry_tool_calls = retry_msg.tool_calls or []
                    for tool_call in retry_tool_calls:
                        if tool_call.function.name != "create_planning_dsl":
                            continue
                        try:
                            args = json.loads(tool_call.function.arguments or "{}")
                        except Exception as e:
                            self.last_planning_error = f"planning_retry_tool_args_parse_failed: {e.__class__.__name__}: {e}"
                            continue
                        raw_plans = args.get("plans")
                        clarification = args.get("clarification")
                        if isinstance(clarification, dict) and clarification.get("need"):
                            self.last_planning_error = ""
                            return [{"question": user_query, "clarification": clarification}]
                        if isinstance(raw_plans, list):
                            plans: list[dict] = []
                            for p in raw_plans:
                                if not isinstance(p, dict):
                                    continue
                                plans.append(p)
                            self.last_planning_error = ""
                            return self._finalize_plans(plans, user_query)
                        raw_plan = args.get("plan")
                        if isinstance(raw_plan, dict):
                            self.last_planning_error = ""
                            return self._finalize_plans([raw_plan], user_query)
                    retry_content = retry_msg.content or ""
                    try:
                        obj = json.loads(retry_content)
                    except Exception:
                        obj = None
                    if isinstance(obj, dict) and isinstance(obj.get("plans"), list):
                        plans: list[dict] = []
                        for p in obj["plans"]:
                            if not isinstance(p, dict):
                                continue
                            plans.append(p)
                        self.last_planning_error = ""
                        return self._finalize_plans(plans, user_query)
                    if isinstance(obj, dict) and isinstance(obj.get("clarification"), dict) and obj["clarification"].get("need"):
                        self.last_planning_error = ""
                        return [{"question": user_query, "clarification": obj["clarification"]}]
                    if isinstance(obj, dict) and isinstance(obj.get("plan"), dict):
                        self.last_planning_error = ""
                        return self._finalize_plans([obj["plan"]], user_query)
                    if not retry_tool_calls:
                        rf = str(getattr(retry.choices[0], "finish_reason", "") or "")
                        p2 = (retry_content or "").strip().replace("\n", " ")
                        if len(p2) > 240:
                            p2 = p2[:240] + "...(truncated)"
                        self.last_planning_error = f"planning_retry_no_tool_calls: finish_reason={rf} content_preview={p2}"
                except Exception as e:
                    self.last_planning_error = f"planning_retry_call_failed: {e.__class__.__name__}: {e}"
        except Exception as e:
            self.last_planning_error = f"planning_llm_call_failed: {e.__class__.__name__}: {e}"

        for part in parts:
            intent = self._classify_intent(part)
            if intent == "statistics":
                ps = self._build_yesterday_vs_range_daily_mean_plans(part)
                if isinstance(ps, list) and ps:
                    return ps
            if intent == "statistics" and self._is_weekly_decline_ratio_query(part):
                p = self._build_weekly_decline_ratio_plan(part)
                p["question"] = part
                return [p]
            if intent == "statistics" and self._is_daily_threshold_count_query(part):
                p = self._build_daily_threshold_count_plan(part)
                if isinstance(p, dict) and p:
                    p["question"] = part
                    return [p]
            if intent == "statistics" and self._is_daily_mean_median_query(part) and not any(k in part for k in ["对比", "相比", "对照", "较"]):
                p = self._build_daily_mean_median_plan(part)
                if isinstance(p, dict) and p:
                    p["question"] = part
                    return [p]
            if intent == "statistics" and self._is_trend_summary_query(part) and not any(k in part for k in ["对比", "相比", "对照", "较"]):
                p = self._build_trend_summary_plan(part)
                if isinstance(p, dict) and p:
                    p["question"] = part
                    return [p]
            if intent == "statistics" and self._is_contribution_summary_query(part) and not any(k in part for k in ["对比", "相比", "对照", "较"]):
                p = self._build_contribution_summary_plan(part)
                if isinstance(p, dict) and p:
                    p["question"] = part
                    return [p]
            if intent == "statistics" and self._is_daily_mean_query(part) and not any(k in part for k in ["对比", "相比", "对照", "较"]):
                p = self._build_daily_mean_plan(part)
                if isinstance(p, dict) and p:
                    p["question"] = part
                    return [p]
            if intent == "statistics" and self._is_daily_percentile_rank_query(part):
                p = self._build_daily_percentile_rank_plan(part)
                if isinstance(p, dict) and p:
                    p["question"] = part
                    return [p]
            if intent == "statistics" and self._is_weekend_percentile_rank_query(part):
                p = self._build_weekend_percentile_rank_plan(part)
                if isinstance(p, dict) and p:
                    p["question"] = part
                    return [p]
            if intent == "statistics" and self._is_weekday_percentile_rank_query(part):
                p = self._build_weekday_percentile_rank_plan(part)
                if isinstance(p, dict) and p:
                    p["question"] = part
                    return [p]

        base_defaults = self._metric_defaults(user_query)
        rule_plans: list[dict] = []
        for part in parts:
            effective_part = part
            if base_defaults and not self._metric_defaults(part):
                metric_hint = base_defaults.get("metric", {}).get("business_name") or base_defaults.get("metric", {}).get("alias")
                if metric_hint:
                    effective_part = f"{metric_hint} {part}"
            plan = self._rule_based_plan(effective_part)
            if isinstance(plan, dict) and plan:
                plan["question"] = part
                rule_plans.append(plan)
        if rule_plans:
            self.last_planning_error = ""
            return self._finalize_plans(rule_plans, user_query)
        enum_plan = self._build_dimension_enumeration_plan(user_query)
        if isinstance(enum_plan, dict) and enum_plan:
            enum_plan["question"] = user_query
            self.last_planning_error = ""
            return self._finalize_plans([enum_plan], user_query)
        return self._finalize_plans(rule_plans, user_query)

    def _fill_defaults(self, plan: dict, user_query: str) -> dict:
        metric_defaults = self._metric_defaults(user_query)
        today = datetime.date.today()
        default_start = (today - datetime.timedelta(days=1)).isoformat()
        default_end = today.isoformat()

        if not plan.get("dataset"):
            plan["dataset"] = metric_defaults["dataset"] if metric_defaults else "order_data"

        metric = plan.get("metric")
        if not isinstance(metric, dict):
            metric = {}
        if not metric.get("field") or not metric.get("agg"):
            if metric_defaults:
                plan["metric"] = metric_defaults["metric"]

        time = plan.get("time")
        if not isinstance(time, dict):
            time = {}
        if not time.get("start") or not time.get("end"):
            time["start"] = time.get("start") or default_start
            time["end"] = time.get("end") or default_end
        if not time.get("field") and metric_defaults:
            time["field"] = metric_defaults["time_field"]
        plan["time"] = time

        filters = plan.get("filters")
        if not isinstance(filters, list):
            filters = []

        time_field = time.get("field")
        if isinstance(time_field, str) and time_field in {"lock_time", "delivery_date", "invoice_upload_time", "intention_payment_time", "Assign Time 年/月/日"}:
            has_non_null = any(
                isinstance(f, dict) and f.get("field") == time_field and f.get("op") == "!=" and f.get("value") is None
                for f in filters
            )
            if not has_non_null:
                filters.append({"field": time_field, "op": "!=", "value": None})
        statistics = plan.get("statistics")
        if isinstance(statistics, dict) and statistics.get("type") in {
            "weekly_decline_ratio",
            "daily_threshold_count",
            "daily_mean",
            "daily_mean_median",
            "trend_summary",
            "contribution_summary",
            "daily_percentile_rank",
            "weekend_percentile_rank",
            "weekday_percentile_rank",
        }:
            if isinstance(time_field, str) and time_field:
                stype = statistics.get("type")
                if stype == "contribution_summary":
                    dim_field = statistics.get("dimension_field")
                    if isinstance(dim_field, str) and dim_field:
                        plan["dimensions"] = [time_field, dim_field]
                    else:
                        plan["dimensions"] = [time_field]
                else:
                    plan["dimensions"] = [time_field]
        if metric_defaults and metric_defaults.get("operator_intent"):
            op_intent = metric_defaults["operator_intent"]
            existing_intent = (plan.get("analysis_intent", {}) or {}).get("type")
            if not existing_intent:
                plan.setdefault("analysis_intent", {})["type"] = op_intent

        if metric_defaults and (metric_defaults.get("metric") or {}).get("alias") == "在营门店数":
            if isinstance(time, dict):
                time["field"] = "order_create_date"
                if not any(
                    isinstance(f, dict) and f.get("field") == "order_create_date" and f.get("op") == "!=" and f.get("value") is None
                    for f in filters
                ):
                    filters.append({"field": "order_create_date", "op": "!=", "value": None})
            q = user_query or ""
            if any(k in q for k in ["最大", "最高", "峰值", "最小", "最低"]):
                dims = plan.get("dimensions")
                if not isinstance(dims, list) or not dims:
                    plan["dimensions"] = ["order_create_date"]
                if isinstance(plan.get("statistics"), dict):
                    plan["statistics"] = {}

        dims = plan.get("dimensions")
        if not isinstance(dims, list):
            dims = []
        if not dims:
            q = (user_query or "").replace(" ", "")
            dataset = str(plan.get("dataset") or "")
            time_field = (plan.get("time", {}) or {}).get("field")
            gender_dimension = self._resolve_gender_dimension(q)
            want_date = any(k in q for k in ["按日期", "按天", "按日", "每天", "逐日", "分日期", "日维度", "日别"])
            if not want_date:
                want_date = len(re.findall(r"\d{4}-\d{2}-\d{2}", q)) >= 2 or len(re.findall(r"\d{1,2}月\d{1,2}[日号]?", q)) >= 2
            want_series = self._contains_any_token(q, self._DIMENSION_SYNONYMS.get("series") or [])
            want_product = self._contains_any_token(q, self._DIMENSION_SYNONYMS.get("product_name") or [])
            want_region = self._contains_any_token(q, self._DIMENSION_SYNONYMS.get("parent_region_name") or [])
            want_store = self._contains_any_token(q, self._DIMENSION_SYNONYMS.get("store_name") or [])
            want_store_city = self._contains_any_token(q, self._DIMENSION_SYNONYMS.get("store_city") or [])
            want_license_city = self._contains_any_token(q, self._DIMENSION_SYNONYMS.get("license_city") or [])
            if dataset == "order_data":
                if want_date and isinstance(time_field, str) and time_field:
                    inferred_dims = [time_field]
                    if gender_dimension:
                        inferred_dims.append(gender_dimension)
                    elif want_product:
                        inferred_dims.append("product_name")
                    elif want_series:
                        if PlanningAgent._infer_series_tokens(user_query):
                            inferred_dims.append("product_name")
                        else:
                            inferred_dims.append("series")
                    elif want_store_city:
                        inferred_dims.append("store_city")
                    elif want_license_city:
                        inferred_dims.append("license_city")
                    elif want_store:
                        inferred_dims.append("store_name")
                    elif want_region:
                        inferred_dims.append("parent_region_name")
                    plan["dimensions"] = inferred_dims
                elif gender_dimension:
                    plan["dimensions"] = [gender_dimension]
                elif want_product:
                    plan["dimensions"] = ["product_name"]
                elif want_series:
                    if PlanningAgent._infer_series_tokens(user_query):
                        plan["dimensions"] = ["product_name"]
                    else:
                        plan["dimensions"] = ["series"]
                elif want_store_city:
                    plan["dimensions"] = ["store_city"]
                elif want_license_city:
                    plan["dimensions"] = ["license_city"]
                elif want_store:
                    plan["dimensions"] = ["store_name"]
                elif want_region:
                    plan["dimensions"] = ["parent_region_name"]
        filters = self._apply_semantic_filters(filters, user_query)
        filters = self._apply_business_semantic_filters(filters, user_query)
        plan["filters"] = filters


        comparison = plan.get("comparison")
        if not isinstance(comparison, dict) or comparison.get("type") not in {"none", "yoy", "wow", "dod"}:
            plan["comparison"] = {"type": self._parse_comparison_type(user_query)}

        fast_path = self._parse_fast_path_query(user_query)
        if fast_path:
            plan["fast_path"] = fast_path
        elif "fast_path" not in plan:
            plan["fast_path"] = {}

        time = plan.get("time")
        if isinstance(time, dict):
            if not time.get("start") or not time.get("end"):
                time["start"] = time.get("start") or default_start
                time["end"] = time.get("end") or default_end

        return self._normalize_plan(plan)

    @staticmethod
    def _is_cumulative_query(user_query: str) -> bool:
        return is_cumulative_query(user_query)

    @staticmethod
    def _remove_cumulative_time_dim(plan: dict, user_query: str) -> dict:
        return remove_cumulative_time_dim(plan, user_query)

    def create_plan(self, user_query: str, memory_context: dict | None = None) -> dict:
        plans = self.create_plans(user_query, memory_context=memory_context)
        if plans:
            first = plans[0]
            if isinstance(first, dict) and first:
                metric = first.get("metric")
                metric_text = ""
                if isinstance(metric, dict):
                    metric_text = " ".join(
                        [
                            str(metric.get("alias") or ""),
                            str(metric.get("business_name") or ""),
                            str(metric.get("field") or ""),
                        ]
                    )
                if "留存小订" in metric_text:
                    return first
                first = self._validate_and_rewrite_time(first, user_query)
                first = self._remove_cumulative_time_dim(first, user_query)
                if isinstance(first.get("comparison"), dict) and first["comparison"].get("type") in ("yoy", "wow"):
                    time_info = first.get("time")
                    if isinstance(time_info, dict):
                        start_str = time_info.get("start")
                        if isinstance(start_str, str):
                            try:
                                current_year = int(start_str[:4])
                            except (ValueError, IndexError):
                                current_year = None
                            if current_year:
                                target = extract_compare_year(user_query, current_year)
                                if target is not None:
                                    first["comparison"]["target_year"] = target
                return first
            return first
        return {}

    @staticmethod
    def _contains_relative_to_today_hint(user_query: str) -> bool:
        return contains_relative_to_today_hint(user_query)

    @staticmethod
    def _infer_time_window_type(user_query: str) -> str | None:
        return infer_time_window_type(user_query)

    @staticmethod
    def _safe_parse_iso_date(value: object) -> datetime.date | None:
        if not isinstance(value, str):
            return None
        raw = value.strip()
        if not raw:
            return None
        try:
            return datetime.date.fromisoformat(raw)
        except Exception:
            return None

    def _rewrite_time_with_llm(
        self,
        user_query: str,
        current_time: dict,
        rule_window: tuple[str, str],
        today: datetime.date,
        time_type: str,
    ) -> tuple[str, str] | None:
        if self.client is None:
            return rule_window
        messages = [
            {
                "role": "system",
                "content": (
                    "你是时间窗口修复器。"
                    "给定用户问题与当前 time（start/end），当发现不一致时你需要重写 time。"
                    "时间窗口必须是左闭右开：[start,end)。"
                    "start/end 必须是 YYYY-MM-DD。"
                    "如果时间类型为 this_month_to_today / month_to_today / yesterday，必须严格符合语义。"
                    "必须与规则解析窗口一致。"
                    "只输出工具调用 rewrite_time_window。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"今天日期: {today.isoformat()}\n"
                    f"用户问题: {user_query}\n"
                    f"时间类型: {time_type}\n"
                    f"当前 time: {json.dumps(current_time, ensure_ascii=False)}\n"
                    f"规则解析窗口(供参考): start={rule_window[0]} end={rule_window[1]}\n"
                    "请重写 time.start/time.end。"
                ),
            },
        ]
        try:
            response = self.client.chat.completions.create(
                model=DEEPSEEK_PLANNER_MODEL,
                messages=messages,
                tools=[TIME_REWRITE_TOOL_SCHEMA],
                tool_choice={"type": "function", "function": {"name": "rewrite_time_window"}},
            )
            message = response.choices[0].message
            tool_calls = message.tool_calls or []
            for tool_call in tool_calls:
                if tool_call.function.name != "rewrite_time_window":
                    continue
                args = json.loads(tool_call.function.arguments or "{}")
                start = args.get("start")
                end = args.get("end")
                s = self._safe_parse_iso_date(start)
                e = self._safe_parse_iso_date(end)
                if not s or not e or e <= s:
                    return rule_window
                out = (s.isoformat(), e.isoformat())
                if time_type in {"this_month_to_today", "month_to_today"} and out[1] != today.isoformat():
                    return rule_window
                if time_type == "yesterday" and out[1] != today.isoformat():
                    return rule_window
                if out != rule_window:
                    return rule_window
                return out
        except Exception:
            return rule_window
        return rule_window

    def _validate_and_rewrite_time(self, plan: dict, user_query: str, today: datetime.date | None = None) -> dict:
        if not isinstance(plan, dict) or not plan:
            return plan
        time = plan.get("time")
        if not isinstance(time, dict):
            return plan
        today = today or datetime.date.today()
        rule_window = self._parse_time_window_with_business(user_query, today)
        if not rule_window:
            return plan
        time_type = self._infer_time_window_type(user_query)
        if not time_type or time_type not in self._TIME_REWRITE_WHITELIST:
            return plan
        if time.get("start") == rule_window[0] and time.get("end") == rule_window[1]:
            return plan
        rewritten = self._rewrite_time_with_llm(
            user_query=user_query,
            current_time=time,
            rule_window=rule_window,
            today=today,
            time_type=time_type,
        )
        if rewritten:
            time["start"], time["end"] = rewritten
            plan["time"] = time
        return plan


def _extract_json_content(text: str) -> str:
    raw = (text or "").strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return raw


def plan_runtime_action(client: OpenAI, state: AgentState) -> dict:
    readiness = evaluate_state_readiness(state)
    if isinstance(readiness, dict):
        recommended = str(readiness.get("recommended_next_action") or "").strip().lower()
        if recommended in {"run_dsl", "finish"}:
            if recommended == "finish":
                return {
                    "action": "finish",
                    "reason": str(readiness.get("reason") or "ready"),
                    "analysis": str(readiness.get("reason") or ""),
                }
            recommended_query = readiness.get("recommended_query")
            query = str(recommended_query or state.question).strip() or state.question
            if readiness.get("reason") == "result_does_not_satisfy_goal":
                state.memory.working_memory["repair_count"] = int(state.memory.working_memory.get("repair_count", 0)) + 1
            if state.loop.iteration == 0 and not state.loop.history:
                return {
                    "action": "run_dsl",
                    "reason": "首次执行，先获取核心数据事实。",
                    "query": query,
                    "analysis": "开始围绕用户目标进行首轮查询。",
                }
            return {
                "action": "run_dsl",
                "reason": str(readiness.get("reason") or "not_ready"),
                "query": query,
                "analysis": str(readiness.get("reason") or ""),
            }

    history_payload = json.dumps(state.loop.history[-3:], ensure_ascii=False)
    facts_payload = json.dumps(state.memory.facts, ensure_ascii=False)
    working_payload = json.dumps(state.memory.working_memory, ensure_ascii=False)
    messages = [
        {"role": "system", "content": LOOP_RUNTIME_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"用户目标:\n{state.question}\n\n"
                f"已执行步数: {state.loop.iteration}/{state.loop.max_steps}\n"
                f"已有 facts:\n{facts_payload}\n\n"
                f"当前 working_memory:\n{working_payload}\n\n"
                f"历史:\n{history_payload}\n\n"
                "请输出下一步 JSON。"
            ),
        },
    ]
    try:
        response = client.chat.completions.create(model=DEEPSEEK_PLANNER_MODEL, messages=messages)
        content = response.choices[0].message.content or ""
        parsed = json.loads(_extract_json_content(content))
        if not isinstance(parsed, dict):
            raise ValueError("runtime action is not an object")
    except Exception as e:
        return {
            "action": "finish",
            "reason": "loop action 解析失败，触发保底收敛。",
            "analysis": f"解析异常: {str(e)}",
        }

    action = str(parsed.get("action") or "").strip().lower()
    if action not in {"run_dsl", "finish"}:
        action = "finish"
    out = {
        "action": action,
        "reason": str(parsed.get("reason") or ""),
        "analysis": str(parsed.get("analysis") or ""),
    }
    if action == "run_dsl":
        query = str(parsed.get("query") or "").strip() or state.question
        out["query"] = query
    return out
