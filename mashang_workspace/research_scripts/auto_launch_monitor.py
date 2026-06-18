#!/usr/bin/env python3
"""
汽车新车事件监测器 — Auto Launch Monitor (v0.5.4)

Market Intelligence / New Vehicle Event Monitor

查询指定日期范围内中国市场的汽车新车上市、预售、发布会、首发亮相、
开启交付等产品投放事件，输出可追溯的结构化市场情报报告。

当前范围: 新车事件（发布会/上市/预售/首发亮相/开启交付/官图发布/媒体预热/其他）
未覆盖: 价格变化、权益变化、销量异动、舆情热点、政策信息、渠道动作等

体系位置:
   市场情报 Market Intelligence
   ├── 新车事件监测 auto_launch_monitor.py     <- 当前 v0.4.5
   ├── 价格/权益监测 price_incentive_monitor.py
   ├── 销量/订单异动监测 sales_signal_monitor.py
   ├── 舆情热点监测 public_opinion_monitor.py
   ├── 政策/法规监测 policy_monitor.py
   └── 竞品动作周报 competitor_weekly_digest.py

阶段定义:
   v0.1 新车事件查询链路跑通
   v0.2 新车事件质量规则增强
   v0.3 可配置情报源 + 品牌/关键词过滤
   v0.4 关注车型池监测
   v0.4.1 Firecrawl 抓取容错 + 质量诊断
   v0.4.2 结果污染修复 + 匹配强化
   v0.4.3 规则层 final guard 收口
   v0.4.4 降级传导 + snippet 污染 + 可信度收紧
    v0.4.5 真实 E2E 中 brand conflict / polluted snippet 未触发修复
    v0.5   DeepSeek LLM Judge（默认关闭，只裁判 uncertain candidates）
v0.5.1 source_publish_date 误当作 event_date / 空 brand+model 已确认 / 历史上市误入修复
v0.5.2 Makefile 产品入口默认启用 LLM Judge；Python 脚本默认关闭
v0.5.3 Polluted Evidence Judge Guard — 污染证据治理、reject intent 后处理
v0.5.4 LLM Judge Cache Versioning + Event Scope Classification (当前)

v0.5 新增:
    - DeepSeek LLM Judge：只对规则层不确定的候选事件做语义裁判
    - 新增 --llm-judge / --llm-judge-mode / --llm-judge-max / --llm-judge-cache CLI 参数
    - LLMJudgeConfig / LLMJudgeDecision dataclass
    - should_send_to_llm_judge 候选选择逻辑
    - build_llm_judge_prompt / call_deepseek_llm_judge / parse_llm_judge_response
    - 缓存层 (outputs/cache/auto_launch_monitor_llm_judge_cache.json)
    - apply_llm_judge_decision 决策应用（含可信度上限锁定）
    - diagnostics 扩展（11 个新字段 + LLM Judge 样例区块）
    - Mock 测试覆盖，不依赖真实 DeepSeek API

v0.5.1 修复:
    - Strict Event Date Guard: source_publish_date + 强事件类型无同日证据→降级/丢弃
    - Core Entity Final Guard: 已确认事件无品牌/车型→丢弃（LLM Judge 可修正后保留）
    - 历史回顾/非当期事件 guard: 此前上市/已上市/北京车展上市等→丢弃
    - has_explicit_same_day_event_evidence / has_historical_event_phrase / is_missing_core_entity
    - diagnostics 新增字段: source_publish_date_guard_count / historical_event_filtered_count / missing_core_entity_filtered_count
    - LLM Judge diagnostics 始终显示（即使未启用 --llm-judge）

v0.5.2 变更:
    - Makefile 产品入口默认启用 LLM Judge（LLM_JUDGE ?= 1）
    - Python 脚本入口保持默认关闭（action=store_true, default=False）
    - Makefile 支持 LLM_JUDGE=0 显式关闭
    - LLM_JUDGE_MAX 默认从 20 改为 10

v0.5.3 变更:
    - 新增 POLLUTED_EVIDENCE_PATTERNS + is_polluted_evidence_snippet() 污染证据识别函数
    - LLM Judge prompt 对污染证据标记 evidence_polluted 强提示
    - 新增 has_reject_intent() 后处理：LLM 说"不保留"但 action=downgrade 时转为 discard
    - 新增 final guard：待确认+低可信+污染证据 → 移出主事件列表
    - 污染证据 confidence cap：polluted evidence 最高可信度限制为"低"
    - diagnostics 新增字段: polluted_evidence_llm_prompt_count / llm_reject_intent_discard_count / low_confidence_polluted_filtered_count

用法:
    python mashang_workspace/research_scripts/auto_launch_monitor.py \\
        --start 2026-06-05 --end 2026-06-07 \\
        --targets-file mashang_workspace/configs/ls8_competitor_watchlist.csv \\
        --source-types official,mainstream_media,industry_media

环境变量:
    TAVILY_API_KEY      (必填) Tavily 搜索 API Key
    FIRECRAWL_API_KEY   (必填) Firecrawl 网页抓取 API Key

可信度规则:
    - 官方来源（品牌官网）= 高
    - 2 个及以上主流汽车媒体交叉验证同一事件 = 高
    - 单一主流汽车媒体 = 中
    - 自媒体、论坛、聚合页、二次转载、无明确日期 = 低
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

_WS_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = _WS_ROOT.parent

ALL_EVENT_TYPES = ["发布会", "上市", "预售", "首发亮相", "开启交付", "官图发布", "媒体预热", "其他"]

DEFAULT_EVENT_TYPES = ["发布会", "上市", "预售", "首发亮相", "开启交付"]
DEFAULT_SOURCE_TYPES = ["official", "mainstream_media", "industry_media"]
DEFAULT_KEYWORDS = ["新车上市", "新车预售", "新车发布会", "新车首发", "新车亮相", "新车交付", "新车发布"]
DEFAULT_EXCLUDE_KEYWORDS = [
    "谍照", "假想图", "申报图", "路试", "曝光", "或将", "预计", "有望", "疑似", "网传", "价格猜测",
]
IRRELEVANT_KEYWORDS = {"哈兰德", "世界杯", "中国女排", "欧冠", "英超"}

CONFIRMED_EVENT_VERBS = {"正式上市", "上市", "开启预售", "开启交付", "正式发布", "发布", "首发亮相", "官图发布"}

POLLUTED_SNIPPET_MARKERS = {
    "相关资讯", "推荐阅读", "查看更多评论", "推荐视频",
    "询底价", "点击查看", "车型报价", "对比评测",
    "车型新闻", "全部新车资讯", "导购", "试驾", "测评",
    "自驾游", "用车",
    "dy_recommends", "post2020",
    "spss=dy_author", "[![",
    "model_",
    "db.m.auto.sohu.com/model_",
}

POLLUTED_EVIDENCE_PATTERNS = [
    "db.m.auto.sohu.com/model_",
    "/model_",
    "相关资讯",
    "### 相关资讯",
    "- [**",
    ") - [**",
    "post2020_dy_recommends",
    "f=post2020_dy_recommends",
    "www.163.com/v/video",
]

LLM_JUDGE_PROMPT_VERSION = "v0.5.4"
LLM_JUDGE_SCHEMA_VERSION = "v1"
LLM_JUDGE_GUARD_VERSION = "polluted-evidence-v2"

EVENT_SCOPE_NATIONAL = "national"
EVENT_SCOPE_REGIONAL = "regional"
EVENT_SCOPE_DEALER = "dealer"
EVENT_SCOPE_AUTO_SHOW = "auto_show"
EVENT_SCOPE_MEDIA = "media"
EVENT_SCOPE_UNKNOWN = "unknown"

SCOPE_CITY_NAMES = [
    "重庆", "成都", "上海", "广州", "深圳", "北京",
    "杭州", "南京", "苏州", "武汉", "西安", "长沙",
    "郑州", "天津", "青岛", "宁波", "佛山",
]

REJECT_INTENT_PHRASES = [
    "不保留",
    "不应保留",
    "不支持",
    "证据不支持",
    "缺乏正文支持",
    "无关",
    "与目标车型无关",
    "非目标车型",
    "主体不是",
    "不是目标车型",
    "仅 source_title 命中",
    "仅标题命中",
    "仅来源标题命中",
    "evidence不支持",
    "evidence 不支持",
    "keep=false",
    "keep = false",
    "should reject",
    "reject",
]

HISTORICAL_EVENT_PHRASES = [
    "此前上市", "已经上市", "已上市", "上市后",
    "上市以来", "自上市以来", "上市仅", "上市满",
    "上市一个月", "上市仅一个月",
    "北京车展正式上市", "上海车展正式上市",
    "成都车展正式上市", "广州车展正式上市",
    "曾于", "此前发布", "此前开启预售",
    "回顾", "早在", "当年", "历史上",
]
STRONG_DATE_EVENT_TYPES = {"上市", "发布会", "预售", "开启交付", "首发亮相"}

OTHER_MODEL_PATTERN_MARKERS = {
    "EX90", "ES90", "宋U", "贝塔T1", "海豹08", "S07", "乐道L60",
    "插混中型SUV", "系新爆款",
}

SOURCE_TYPE_MAP = {
    "official": "official",
    "mainstream": "mainstream_media",
    "industry_media": "industry_media",
    "social": "social_media",
    "social_media": "social_media",
    "aggregator": "aggregator",
    "ugc_media": "ugc_media",
    "forum": "forum",
    "low": "social_media",
    "normal": "unknown",
}

LOW_QUALITY_SOURCE_TYPES = {"aggregator", "social_media", "ugc_media", "forum", "unknown"}

OFFICIAL_DOMAINS = [
    "lixiang.com", "xiaopeng.com", "saicmotor.com",
    "ntgame.com", "byd.com", "zeekr.com",
]

MAINSTREAM_DOMAINS = [
    "autohome.com.cn", "dongchedi.com", "pcauto.com.cn",
    "bitauto.com", "sina.com.cn", "sohu.com",
    "163.com", "qq.com", "cheshi.com",
    "yiche.com", "12365auto.com", "eastmoney.com",
]

INDUSTRY_DOMAINS = [
    "gasgoo.com", "news18a.com", "xchuxing.com",
    "autos.sina.com.cn", "cls.cn", "nbd.com.cn",
    "stcn.com", "weeklyonstock.com",
]

LOW_QUALITY_DOMAINS = [
    "zhihu.com", "baijiahao.baidu.com", "toutiao.com",
    "k.sina.com.cn", "weibo.com",
]

SOCIAL_MEDIA_DOMAINS = [
    "chejiahao.autohome.com.cn",
]

AGGREGATOR_DOMAINS = [
    "tags.sina.com.cn",
]

UGC_DOMAINS = [
    "163.com/dy",
]


@dataclass
class MonitorFilters:
    brands: list[str] = field(default_factory=list)
    event_types: list[str] = field(default_factory=lambda: DEFAULT_EVENT_TYPES[:])
    source_types: list[str] = field(default_factory=lambda: DEFAULT_SOURCE_TYPES[:])
    keywords: list[str] = field(default_factory=lambda: DEFAULT_KEYWORDS[:])
    exclude_keywords: list[str] = field(default_factory=lambda: DEFAULT_EXCLUDE_KEYWORDS[:])

    def to_dict(self):
        return {
            "brands": self.brands,
            "event_types": self.event_types,
            "source_types": self.source_types,
            "keywords": self.keywords,
            "exclude_keywords": self.exclude_keywords,
        }


@dataclass
class CrawlDiagnostics:
    generated_query_count: int = 0
    dedup_url_count: int = 0
    pre_crawl_skipped_count: int = 0
    pre_crawl_skipped_urls: list[dict[str, str]] = field(default_factory=list)
    planned_crawl_count: int = 0
    crawled_page_count: int = 0
    failed_crawl_count: int = 0
    failed_urls: list[dict[str, str]] = field(default_factory=list)
    raw_extracted_event_count: int = 0
    source_filtered_count: int = 0
    target_matched_event_count: int = 0
    conflict_filtered_count: int = 0
    final_event_count: int = 0
    conflict_filtered_events: list[dict[str, str]] = field(default_factory=list)
    final_guard_filtered_count: int = 0
    final_guard_filtered_events: list[dict] = field(default_factory=list)
    out_of_range_event_count: int = 0
    brand_model_conflict_count: int = 0
    evidence_irrelevant_count: int = 0
    date_basis_downgraded_count: int = 0
    polluted_snippet_count: int = 0
    confidence_downgraded_count: int = 0
    status_downgraded_count: int = 0
    degrade_samples: list[dict] = field(default_factory=list)
    llm_judge_enabled: bool = False
    llm_judge_mode: str = ""
    llm_judge_candidate_count: int = 0
    llm_judge_called_count: int = 0
    llm_judge_cache_hit_count: int = 0
    llm_judge_cache_miss_count: int = 0
    llm_judge_keep_count: int = 0
    llm_judge_discard_count: int = 0
    llm_judge_downgrade_count: int = 0
    llm_judge_error_count: int = 0
    llm_judge_samples: list[dict] = field(default_factory=list)
    historical_downgraded_count: int = 0
    source_pub_empty_brand_model_count: int = 0
    source_publish_date_guard_count: int = 0
    historical_event_filtered_count: int = 0
    missing_core_entity_filtered_count: int = 0
    polluted_evidence_llm_prompt_count: int = 0
    llm_reject_intent_discard_count: int = 0
    low_confidence_polluted_filtered_count: int = 0
    llm_judge_cache_stale_count: int = 0
    llm_judge_cache_bypass_count: int = 0
    event_scope_classified_count: int = 0
    national_event_count: int = 0
    regional_event_count: int = 0
    dealer_event_count: int = 0
    auto_show_event_count: int = 0
    media_event_count: int = 0
    unknown_event_scope_count: int = 0
    related_event_count: int = 0
    non_national_event_filtered_count: int = 0
    related_event_samples: list[dict] = field(default_factory=list)


@dataclass
class LLMJudgeConfig:
    enabled: bool = False
    mode: str = "uncertain"
    max_candidates: int = 20
    cache_enabled: bool = True
    model: str = ""
    api_key_env: str = "DEEPSEEK_API_KEY"
    base_url_env: str = "DEEPSEEK_BASE_URL"
    default_model: str = "deepseek-v4-flash"


DEFAULT_LLM_MODEL = "deepseek-v4-flash"


@dataclass
class LLMJudgeDecision:
    keep: bool = True
    action: str = "keep"
    target_match: bool = True
    event_is_about_target: bool = True
    event_subject_brand: str = ""
    event_subject_model: str = ""
    corrected_brand: str = ""
    corrected_model: str = ""
    event_type: str = ""
    event_status: str = ""
    confidence: str = "中"
    event_date: str = ""
    source_publish_date: str = ""
    date_basis: str = ""
    date_confidence: str = "medium"
    source_context_type: str = "unknown"
    polluted_snippet: bool = False
    conflict: bool = False
    conflict_reason: str = ""
    evidence_quality: str = "medium"
    reason: str = ""


@dataclass(frozen=True)
class WatchTarget:
    watchlist_name: str
    target_id: str
    brand: str
    brand_aliases: list[str]
    model: str
    model_aliases: list[str]
    display_name: str
    group: str
    priority: str
    active: bool
    notes: str = ""


# ─── CSV arg parsing ──────────────────────────────────────────────

def parse_csv_arg(value: Optional[str]) -> list[str]:
    if not value or not value.strip():
        return []
    return [s.strip() for s in value.split(",") if s.strip()]


# ─── WatchTarget loading ─────────────────────────────────────────

def load_watch_targets(targets_file: str | Path) -> list[WatchTarget]:
    path = Path(targets_file)
    if not path.exists():
        print(f"[ERROR] 关注车型文件不存在: {path}", file=sys.stderr)
        sys.exit(1)

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print(f"[ERROR] 关注车型文件为空: {path}", file=sys.stderr)
        sys.exit(1)

    required = {"watchlist_name", "target_id", "brand", "model", "display_name", "group", "priority", "active"}
    for r in rows:
        missing = required - set(r.keys())
        if missing:
            print(f"[ERROR] 关注车型文件缺少字段: {missing}", file=sys.stderr)
            sys.exit(1)

    targets = []
    seen_ids = set()
    for r in rows:
        if r.get("active", "").strip().lower() != "true":
            continue
        tid = r["target_id"].strip()
        if tid in seen_ids:
            print(f"[ERROR] 重复 target_id: {tid}", file=sys.stderr)
            sys.exit(1)
        seen_ids.add(tid)

        brand = r["brand"].strip()
        model = r["model"].strip()
        brand_aliases = [a.strip() for a in r.get("brand_aliases", "").split("|") if a.strip()]
        model_aliases = [a.strip() for a in r.get("model_aliases", "").split("|") if a.strip()]

        if brand not in brand_aliases:
            brand_aliases.insert(0, brand)
        if model not in model_aliases:
            model_aliases.insert(0, model)

        targets.append(WatchTarget(
            watchlist_name=r.get("watchlist_name", "").strip(),
            target_id=tid,
            brand=brand,
            brand_aliases=brand_aliases,
            model=model,
            model_aliases=model_aliases,
            display_name=r.get("display_name", f"{brand} {model}").strip(),
            group=r.get("group", "").strip(),
            priority=r.get("priority", "medium").strip(),
            active=True,
            notes=r.get("notes", "").strip(),
        ))

    if not targets:
        print(f"[ERROR] 没有 active=true 的关注车型", file=sys.stderr)
        sys.exit(1)

    return targets


# ─── Target matching helpers ─────────────────────────────────────

_SHORT_MODEL_ALIASES = {"i6", "M7", "GX", "06", "900", "8X", "L80", "D19", "S600"}


def is_strong_model_alias(alias: str) -> bool:
    if alias in _SHORT_MODEL_ALIASES:
        return False
    if len(alias) <= 2 and any(c.isdigit() for c in alias):
        return False
    return True


def has_target_brand_signal(text: str, target: WatchTarget) -> bool:
    return any(alias in text for alias in target.brand_aliases)


def has_target_model_signal(text: str, target: WatchTarget) -> bool:
    return any(alias in text for alias in target.model_aliases)


def is_strong_model_match(text: str, target: WatchTarget) -> bool:
    for alias in target.model_aliases:
        if alias in text and is_strong_model_alias(alias):
            return True
    return False


# ─── v0.4.5: Text normalization helpers ─────────────────────────

def normalize_text_value(value: object) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    if s in ("-",):
        return ""
    return s


def get_event_text_blob(event: dict) -> str:
    fields = [
        event.get("brand") or "",
        event.get("model") or "",
        event.get("target_display_name") or "",
        event.get("title") or "",
        event.get("source_title") or "",
        event.get("evidence") or "",
        event.get("source_url") or "",
    ]
    return " ".join(f.strip() for f in fields if f.strip())


# ─── Conflict detection ──────────────────────────────────────────

def detect_target_conflict(event, target: WatchTarget, all_targets: list[WatchTarget]) -> tuple[bool, str]:
    eb = event.get("brand", "")
    if not eb:
        return False, ""

    if eb in target.brand_aliases:
        return False, ""

    text_pool = " ".join([
        event.get("source_title", ""), event.get("evidence", ""),
        event.get("model", ""),
    ])

    for ot in all_targets:
        if ot.target_id == target.target_id:
            continue
        if eb in ot.brand_aliases:
            ot_model_hit = any(ma in text_pool for ma in ot.model_aliases)
            if ot_model_hit:
                return True, f"brand '{eb}' matches {ot.target_id}"

    return False, ""


# ─── v0.4.5: Brand/model conflict hard filter (evidence-based) ────

def is_brand_model_conflict(event: dict, target: WatchTarget, all_targets: list[WatchTarget]) -> tuple[bool, str]:
    eb = normalize_text_value(event.get("brand"))
    em = normalize_text_value(event.get("model"))
    if not eb and not em:
        return False, ""

    evidence_text = event.get("evidence") or ""
    source_title = event.get("source_title") or ""
    full_text_blob = get_event_text_blob(event)

    def evidence_has_target_strong_signal() -> bool:
        for alias in target.model_aliases:
            if alias in evidence_text and is_strong_model_alias(alias):
                return True
        hbs = has_target_brand_signal(evidence_text, target)
        hms = has_target_model_signal(evidence_text, target)
        if hbs and hms:
            return True
        if hbs:
            for alias in target.model_aliases:
                if alias in evidence_text:
                    return True
        return False

    evidence_ok = evidence_has_target_strong_signal()

    if eb and eb not in target.brand_aliases:
        if not evidence_ok:
            return True, f"brand '{eb}' conflicts with target '{target.target_id}'"

    if em and em not in target.model_aliases:
        if not evidence_ok:
            for marker in OTHER_MODEL_PATTERN_MARKERS:
                if marker in em or marker in evidence_text:
                    return True, f"model '{em}' matches other model marker '{marker}'"
            if not evidence_ok:
                return True, f"model '{em}' conflicts with target '{target.target_id}'"

    return False, ""


# ─── v0.4.3: Evidence relevance guard ──────────────────────────────

def has_final_target_evidence(event: dict, target: WatchTarget) -> bool:
    text_pool = " ".join(filter(None, [
        event.get("evidence") or "",
        event.get("source_title") or "",
    ]))

    for alias in target.model_aliases:
        if alias in text_pool and is_strong_model_alias(alias):
            return True

    has_brand = has_target_brand_signal(text_pool, target)
    has_model = has_target_model_signal(text_pool, target)
    if has_brand and has_model:
        return True

    if has_brand:
        for alias in target.model_aliases:
            if alias in text_pool:
                return True

    return False


# ─── v0.4.5: Polluted snippet detection (extended) ────────────────

def is_polluted_snippet(event: dict) -> tuple[bool, str]:
    text_pool = " ".join(filter(None, [
        event.get("evidence") or "",
        event.get("source_title") or "",
        event.get("title") or "",
        event.get("source_url") or "",
    ]))
    for marker in POLLUTED_SNIPPET_MARKERS:
        if marker in text_pool:
            return True, marker
    return False, ""


# ─── v0.4.4: Post-aggregation confidence normalization ─────────────

def post_aggregate_normalize(events: list[dict], diagnostics: CrawlDiagnostics | None = None) -> list[dict]:
    for e in events:
        date_basis = e.get("date_basis", "")
        evidence = e.get("evidence", "")
        source_type = e.get("source_type", "")
        unique_urls = e.get("source_urls", [])
        has_official = "official" in source_type

        polluted, p_marker = is_polluted_snippet(e)

        downgrade_reason = None

        if polluted:
            if has_official and len(unique_urls) >= 2:
                new_conf = "中"
            else:
                new_conf = "低"
            if e.get("confidence") != new_conf:
                old_conf = e.get("confidence", "")
                e["confidence"] = new_conf
                downgrade_reason = f"polluted_snippet:{p_marker}"
                if diagnostics:
                    diagnostics.confidence_downgraded_count += 1
            if e.get("event_status") == "已确认":
                e["event_status"] = "待确认"
                if diagnostics:
                    diagnostics.status_downgraded_count += 1

        if date_basis == "source_publish_date" and not polluted:
            new_conf = e.get("confidence", "")
            if new_conf == "高":
                e["confidence"] = "中"
                new_conf = "中"
                downgrade_reason = "date_basis_source_publish_date"
                if diagnostics:
                    diagnostics.confidence_downgraded_count += 1
            evidence_text = " ".join(filter(None, [
                e.get("evidence") or "",
                e.get("source_title") or "",
            ]))
            has_verb = any(verb in evidence_text for verb in CONFIRMED_EVENT_VERBS)
            if not has_verb and e.get("event_status") == "已确认":
                e["event_status"] = "待确认"
                if diagnostics:
                    diagnostics.status_downgraded_count += 1

        if downgrade_reason:
            if diagnostics and len(diagnostics.degrade_samples) < 10:
                diagnostics.degrade_samples.append({
                    "target_id": e.get("target_id", ""),
                    "reason": downgrade_reason,
                    "before_status": e.get("event_status", ""),
                    "after_status": e.get("event_status", ""),
                    "before_confidence": e.get("confidence", ""),
                    "after_confidence": e.get("confidence", ""),
                    "evidence_snippet": (e.get("evidence") or "")[:60],
                })

    return events


# ─── v0.5.1: Explicit same-day event evidence ────────────────────

def has_explicit_same_day_event_evidence(
    evidence: str,
    event_date: str | None,
    event_type: str | None,
) -> bool:
    if not evidence or not event_date:
        return False
    try:
        dt = datetime.strptime(event_date, "%Y-%m-%d")
        y, m, d = dt.year, dt.month, dt.day
    except (ValueError, TypeError):
        return False
    patterns = [
        f"{m}月{d}日正式上市",
        f"{m}月{d}日上市",
        f"{m}月{d}日正式发布",
        f"{m}月{d}日发布",
        f"{m}月{d}日开启预售",
        f"{m}月{d}日开启交付",
        f"{m}月{d}日首发亮相",
        f"{y}年{m}月{d}日正式上市",
        f"{y}年{m}月{d}日上市",
        f"{y}年{m}月{d}日正式发布",
        f"{y}年{m}月{d}日开启预售",
        f"{y}年{m}月{d}日开启交付",
        f"{y}年{m}月{d}日首发亮相",
        "今日正式上市", "昨日正式上市", "当天正式上市",
        "今日上市", "昨日上市", "当天上市",
        "今日开启预售", "昨日开启预售",
        "今日开启交付", "昨日开启交付",
    ]
    for pat in patterns:
        if pat in evidence:
            return True
    return False


# ─── v0.5.1: Historical event phrase detection ──────────────────

def has_historical_event_phrase(text: str) -> bool:
    return any(phrase in text for phrase in HISTORICAL_EVENT_PHRASES)


# ─── v0.5.1: Core entity check for confirmed events ─────────────

def is_missing_core_entity_for_confirmed_event(
    event: dict, target: WatchTarget | None = None,
) -> tuple[bool, str]:
    eb = normalize_text_value(event.get("brand"))
    em = normalize_text_value(event.get("model"))
    if not eb and not em:
        return True, "missing_brand_and_model"
    if not eb:
        return True, "missing_brand"
    if not em and target:
        if not has_target_model_signal(event.get("evidence", ""), target):
            return True, "missing_model_no_target_signal"
    return False, ""


# ─── v0.4.3: Final event guard ─────────────────────────────────────

def apply_final_event_guard(
    events: list[dict],
    targets: list[WatchTarget] | None,
    *,
    start_date: str,
    end_date: str,
    diagnostics: CrawlDiagnostics | None = None,
) -> list[dict]:
    guarded = []
    for event in events:
        target_id = event.get("target_id")
        target = None
        if target_id and targets:
            for t in targets:
                if t.target_id == target_id:
                    target = t
                    break

        reason = None

        ed = (event.get("event_date") or "").strip()
        if ed:
            if ed < start_date or ed > end_date:
                reason = "event_date_out_of_range"
                if diagnostics:
                    diagnostics.out_of_range_event_count += 1

        if not reason and target:
            conflict, conflict_reason = is_brand_model_conflict(event, target, targets or [])
            if conflict:
                reason = f"brand_model_conflict: {conflict_reason}"
                if diagnostics:
                    diagnostics.brand_model_conflict_count += 1

        if not reason and target:
            if not has_final_target_evidence(event, target):
                reason = "missing_target_evidence"
                if diagnostics:
                    diagnostics.evidence_irrelevant_count += 1

        if not reason:
            text_pool = " ".join(filter(None, [
                event.get("evidence") or "",
                event.get("source_title") or "",
            ]))
            if any(ik in text_pool for ik in IRRELEVANT_KEYWORDS):
                reason = "irrelevant_keywords"
                if diagnostics:
                    diagnostics.evidence_irrelevant_count += 1

        polluted, p_marker = is_polluted_snippet(event)
        if polluted and diagnostics:
            diagnostics.polluted_snippet_count += 1

        if reason or polluted:
            if reason:
                record_reason = reason
            elif target and polluted:
                evidence_text = event.get("evidence") or ""
                source_title = event.get("source_title") or ""
                has_target_signal = False
                for alias in target.model_aliases:
                    if alias in evidence_text and is_strong_model_alias(alias):
                        has_target_signal = True
                        break
                if not has_target_signal:
                    if has_target_brand_signal(evidence_text, target):
                        for alias in target.model_aliases:
                            if alias in evidence_text:
                                has_target_signal = True
                                break
                if not has_target_signal and not has_target_brand_signal(source_title, target):
                    record_reason = f"polluted_snippet_without_target_signal:{p_marker}"
                else:
                    record_reason = None
                    event["_polluted"] = True
                    event["_polluted_marker"] = p_marker
            else:
                record_reason = None
                event["_polluted"] = True
                event["_polluted_marker"] = p_marker

            if record_reason:
                if diagnostics:
                    diagnostics.final_guard_filtered_count += 1
                    if len(diagnostics.final_guard_filtered_events) < 10:
                        diagnostics.final_guard_filtered_events.append({
                            "target_id": target_id or "",
                            "brand": event.get("brand", ""),
                            "model": event.get("model", ""),
                            "event_date": event.get("event_date", ""),
                            "source_publish_date": event.get("source_publish_date", ""),
                            "reason": record_reason,
                            "evidence_snippet": (event.get("evidence") or "")[:80],
                        })
                continue

        db = event.get("date_basis") or ""
        spd = event.get("source_publish_date") or ""
        ev_type = event.get("event_type", "")
        ed_val = (event.get("event_date") or "").strip()
        evidence = event.get("evidence") or ""
        source_title = event.get("source_title") or ""
        text_pool = " ".join(filter(None, [evidence, source_title]))

        # ── v0.5.1: source_publish_date guard (downgrade first) ──
        orig_status = event.get("event_status", "")
        if db == "source_publish_date" and spd:
            event["date_confidence"] = "low"
            if diagnostics:
                diagnostics.date_basis_downgraded_count += 1
            if ev_type in STRONG_DATE_EVENT_TYPES:
                has_same_day = has_explicit_same_day_event_evidence(evidence, ed_val, ev_type)
                if not has_same_day:
                    if diagnostics:
                        diagnostics.source_publish_date_guard_count += 1
                    if event.get("event_status") == "已确认":
                        event["event_status"] = "待确认"
                        if diagnostics:
                            diagnostics.status_downgraded_count += 1
                    if event.get("confidence") == "高":
                        event["confidence"] = "中"
                        if diagnostics:
                            diagnostics.confidence_downgraded_count += 1

        # ── v0.5.1: discard-level checks ─────────────────────────
        discard_reason = None

        # Historical event phrase + no same-day evidence → discard
        if has_historical_event_phrase(text_pool):
            ed_for_check = ed_val or spd
            if not has_explicit_same_day_event_evidence(evidence, ed_for_check, ev_type):
                discard_reason = "historical_event_phrase"
                if diagnostics:
                    diagnostics.historical_event_filtered_count += 1

        # Core entity missing for confirmed (or originally confirmed) event → discard
        check_core = orig_status == "已确认" or event.get("event_status") == "已确认"
        if not discard_reason and check_core:
            missing_core, core_reason = is_missing_core_entity_for_confirmed_event(event, target)
            if missing_core:
                discard_reason = f"missing_core_entity_for_confirmed_event:{core_reason}"
                if diagnostics:
                    diagnostics.missing_core_entity_filtered_count += 1

        # Triple problem: source_publish_date + no same-day + (missing core entity or date mismatch) → discard
        ev_polluted, _ = is_polluted_evidence_snippet(evidence)
        if ev_polluted:
            event["confidence"] = "低"
            event["event_status"] = "待确认"
        if not discard_reason and event.get("event_status") == "待确认" and event.get("confidence") == "低":
            if ev_polluted:
                discard_reason = "low_confidence_polluted_evidence"
                if diagnostics:
                    diagnostics.low_confidence_polluted_filtered_count += 1

        if not discard_reason and db == "source_publish_date" and ev_type in STRONG_DATE_EVENT_TYPES:
            has_same_day = has_explicit_same_day_event_evidence(evidence, ed_val, ev_type)
            if not has_same_day:
                missing_core, _ = is_missing_core_entity_for_confirmed_event(event, target)
                date_mismatch = False
                if ed_val:
                    m_date_match = re.search(r"(\d{1,2})月(\d{1,2})日", evidence)
                    if m_date_match:
                        try:
                            ev_dt = datetime.strptime(ed_val, "%Y-%m-%d")
                            if int(m_date_match.group(1)) != ev_dt.month or int(m_date_match.group(2)) != ev_dt.day:
                                date_mismatch = True
                        except (ValueError, TypeError):
                            pass
                if missing_core or date_mismatch:
                    discard_reason = "source_publish_date_no_same_day_plus_missing_core_entity"
                    if diagnostics:
                        diagnostics.missing_core_entity_filtered_count += 1

        if not discard_reason:
            scope = classify_event_scope(evidence, source_title, event.get("source_url", ""), ev_type)
            event["event_scope"] = scope
            if diagnostics:
                diagnostics.event_scope_classified_count += 1
                if scope == EVENT_SCOPE_NATIONAL:
                    diagnostics.national_event_count += 1
                elif scope == EVENT_SCOPE_REGIONAL:
                    diagnostics.regional_event_count += 1
                elif scope == EVENT_SCOPE_DEALER:
                    diagnostics.dealer_event_count += 1
                elif scope == EVENT_SCOPE_AUTO_SHOW:
                    diagnostics.auto_show_event_count += 1
                elif scope == EVENT_SCOPE_MEDIA:
                    diagnostics.media_event_count += 1
                else:
                    diagnostics.unknown_event_scope_count += 1
            if scope in (EVENT_SCOPE_REGIONAL, EVENT_SCOPE_DEALER):
                discard_reason = f"non_national_event_scope:{scope}"
                if diagnostics:
                    diagnostics.non_national_event_filtered_count += 1
                    diagnostics.related_event_count += 1
                    if len(diagnostics.related_event_samples) < 10:
                        diagnostics.related_event_samples.append({
                            "target_id": target_id or "",
                            "brand": event.get("brand", ""),
                            "model": event.get("model", ""),
                            "event_date": event.get("event_date", ""),
                            "scope": scope,
                            "event_type": ev_type,
                            "evidence_snippet": (evidence or "")[:60],
                        })
            elif scope == EVENT_SCOPE_AUTO_SHOW and ev_type == "上市":
                discard_reason = f"non_national_event_scope:{scope}"
                if diagnostics:
                    diagnostics.non_national_event_filtered_count += 1
                    diagnostics.related_event_count += 1
                    if len(diagnostics.related_event_samples) < 10:
                        diagnostics.related_event_samples.append({
                            "target_id": target_id or "",
                            "brand": event.get("brand", ""),
                            "model": event.get("model", ""),
                            "event_date": event.get("event_date", ""),
                            "scope": scope,
                            "event_type": ev_type,
                            "evidence_snippet": (evidence or "")[:60],
                        })
            elif scope == EVENT_SCOPE_MEDIA and ev_type != "媒体预热":
                discard_reason = f"non_national_event_scope:{scope}"
                if diagnostics:
                    diagnostics.non_national_event_filtered_count += 1
                    diagnostics.related_event_count += 1
                    if len(diagnostics.related_event_samples) < 10:
                        diagnostics.related_event_samples.append({
                            "target_id": target_id or "",
                            "brand": event.get("brand", ""),
                            "model": event.get("model", ""),
                            "event_date": event.get("event_date", ""),
                            "scope": scope,
                            "event_type": ev_type,
                            "evidence_snippet": (evidence or "")[:60],
                        })

        if discard_reason:
            if diagnostics:
                diagnostics.final_guard_filtered_count += 1
                if len(diagnostics.final_guard_filtered_events) < 10:
                    diagnostics.final_guard_filtered_events.append({
                        "target_id": target_id or "",
                        "brand": event.get("brand", ""),
                        "model": event.get("model", ""),
                        "event_date": event.get("event_date", ""),
                        "source_publish_date": event.get("source_publish_date", ""),
                        "reason": discard_reason,
                        "evidence_snippet": (evidence or "")[:80],
                    })
            continue

        guarded.append(event)

    return guarded


# ─── CLI ─────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="汽车新车事件监测")
    parser.add_argument("--start", required=True, help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--market", default="中国", help="市场区域 (默认 中国)")
    parser.add_argument("--topic", default="新车发布会", help="事件主题 (默认 新车发布会)")
    parser.add_argument("--max-results", type=int, default=20, help="最大搜索结果数 (默认 20)")
    parser.add_argument("--format", default="markdown", choices=["markdown", "csv", "json"],
                        help="输出格式 (default markdown)")
    parser.add_argument("--output", default=str(REPO_ROOT / "mashang_workspace" / "outputs" / "reports"),
                        help="输出目录 (default outputs/reports/)")
    parser.add_argument("--brands", type=str, default=None, help="品牌过滤，逗号分隔")
    parser.add_argument("--event-types", type=str, default=None, help="事件类型过滤")
    parser.add_argument("--source-types", type=str, default=None, help="来源类型过滤")
    parser.add_argument("--keywords", type=str, default=None, help="搜索关键词")
    parser.add_argument("--exclude-keywords", type=str, default=None, help="排除关键词")
    parser.add_argument("--targets-file", type=str, default=None, help="关注车型 CSV 文件路径")
    parser.add_argument("--llm-judge", action="store_true", default=False,
                        help="启用 DeepSeek LLM Judge（默认关闭）")
    parser.add_argument("--llm-judge-mode", type=str, default="uncertain",
                        choices=["uncertain", "all_candidates"],
                        help="LLM Judge 模式: uncertain (默认) 只裁判不确定事件, all_candidates 仅用于 debug")
    parser.add_argument("--llm-judge-max", type=int, default=20,
                        help="LLM Judge 最大裁判数，防止成本失控 (默认 20)")
    parser.add_argument("--llm-judge-cache", action="store_true", default=False,
                        help="启用 LLM Judge 缓存 (默认开启)")
    parser.add_argument("--no-llm-judge-cache", action="store_true", default=False,
                        help="禁用 LLM Judge 缓存")
    return parser.parse_args()


def build_filters(args) -> MonitorFilters:
    return MonitorFilters(
        brands=parse_csv_arg(args.brands),
        event_types=parse_csv_arg(args.event_types) or DEFAULT_EVENT_TYPES[:],
        source_types=parse_csv_arg(args.source_types) or DEFAULT_SOURCE_TYPES[:],
        keywords=parse_csv_arg(args.keywords) or DEFAULT_KEYWORDS[:],
        exclude_keywords=parse_csv_arg(args.exclude_keywords) or DEFAULT_EXCLUDE_KEYWORDS[:],
    )


def check_env():
    missing = [k for k in ("TAVILY_API_KEY", "FIRECRAWL_API_KEY") if k not in os.environ]
    if missing:
        print(f"[ERROR] 缺少环境变量: {', '.join(missing)}")
        print(f"请确保 {', '.join(missing)} 已设置在 .env 或环境中。")
        sys.exit(1)


# ─── v0.5.3: Polluted evidence snippet detector ──────────────────

def is_polluted_evidence_snippet(text: str | None) -> tuple[bool, str | None]:
    if not text:
        return False, None
    for pat in POLLUTED_EVIDENCE_PATTERNS:
        if pat in text:
            return True, pat
    return False, None


# ─── v0.5.3: Reject intent detector ─────────────────────────────

def has_reject_intent(reason: str | None) -> bool:
    if not reason:
        return False
    return any(phrase in reason for phrase in REJECT_INTENT_PHRASES)


# ─── LLM Judge: should_send_to_llm_judge ──────────────────────────

_CACHE_DIR = _WS_ROOT / "outputs" / "cache"
LLM_JUDGE_CACHE_PATH = _CACHE_DIR / "auto_launch_monitor_llm_judge_cache.json"


def should_send_to_llm_judge(event: dict, target: WatchTarget, *,
                              mode: str = "uncertain",
                              start_date: str = "", end_date: str = "") -> tuple[bool, str]:
    if mode == "all_candidates":
        return True, "all_candidates_mode"

    ed = (event.get("event_date") or "").strip()
    if ed:
        if ed < start_date or ed > end_date:
            return False, "event_date_out_of_range"
    eb = normalize_text_value(event.get("brand"))
    em = normalize_text_value(event.get("model"))
    evidence = event.get("evidence") or ""
    if eb and em:
        if eb not in target.brand_aliases:
            if em not in target.model_aliases:
                if not any(alias in evidence for alias in target.model_aliases):
                    return False, "brand_model_conflict"
    text_pool = " ".join(filter(None, [evidence, event.get("source_title", "")]))
    if any(ik in text_pool for ik in IRRELEVANT_KEYWORDS):
        return False, "irrelevant_keywords"

    polluted, _ = is_polluted_snippet(event)
    if polluted:
        return True, "polluted_snippet"

    if not eb or not em:
        return True, "missing_brand_or_model"
    db = event.get("date_basis", "")
    if db == "source_publish_date":
        return True, "date_basis_source_publish_date"
    if not any(alias in evidence for alias in target.model_aliases):
        return True, "weak_evidence"
    es = event.get("event_status", "")
    if es == "待确认":
        return True, "pending_status"
    cf = event.get("confidence", "")
    if cf == "低":
        return True, "low_confidence"
    src_url = event.get("source_url", "")
    if "model_" in src_url:
        return True, "model_page_url"
    return False, "sufficient_confidence"


# ─── LLM Judge: prompt builder ──────────────────────────────────

def build_llm_judge_prompt(event: dict, target: WatchTarget, *,
                            start_date: str, end_date: str) -> str:
    evidence_text = event.get("evidence", "") or ""
    source_title = event.get("source_title", "") or ""
    is_polluted, pollute_reason = is_polluted_evidence_snippet(evidence_text)

    extra_rule = ""
    if is_polluted:
        extra_rule = f"""
evidence_polluted: true
pollution_reason: {pollute_reason}

⚠️ 污染证据规则（因为 evidence_polluted=true）：
该 evidence 可能来自车型页相关资讯列表、聚合卡片、视频推荐或截断链接片段，不可默认视为 article_body。
只有当 evidence 自身同时清楚包含：
1. 目标品牌/车型
2. 事件动作，如 上市/预售/发布/开启交付/亮相
3. 明确日期或同日证据
4. 主体不是其他车型
才允许 keep。
否则应输出 reject。
不要仅凭 source_title 命中目标车型就 keep。"""
    else:
        extra_rule = """
evidence_polluted: false"""

    return f"""你是汽车市场情报系统中的 LLM Judge。
你的任务不是搜索信息，而是判断一个候选事件是否应该进入最终报告。

请只基于给定 evidence/source_title/source_url 判断，不要引入外部知识。

查询时间范围：
{start_date} 至 {end_date}

目标车型：
target_id: {target.target_id}
brand: {target.brand}
brand_aliases: {', '.join(target.brand_aliases)}
model: {target.model}
model_aliases: {', '.join(target.model_aliases)}
display_name: {target.display_name}

候选事件：
brand: {event.get("brand", "")}
model: {event.get("model", "")}
event_type: {event.get("event_type", "")}
event_status: {event.get("event_status", "")}
confidence: {event.get("confidence", "")}
date: {event.get("date", "")}
event_date: {event.get("event_date", "")}
source_publish_date: {event.get("source_publish_date", "")}
date_basis: {event.get("date_basis", "")}
source_title: {source_title}
source_url: {event.get("source_url", "")}
evidence: {evidence_text}{extra_rule}

判断规则：
1. 如果 evidence 主体不是目标车型，keep=false。
2. 如果 evidence 是推荐阅读、相关资讯、车型页列表、推荐流，而不是正文事件，通常 keep=false 或 action=downgrade。
3. 如果 evidence 只出现其他车型，例如乐道L60、沃尔沃EX90、比亚迪宋U，而目标是大众ID. ERA 9X或极氪8X，keep=false。
4. 如果只有 source_title 命中目标，但 evidence 不支持，keep=false。
5. 如果没有明确事件日期，date_basis 应为 source_publish_date，date_confidence=low。
6. 如果证据不扎实，不要给"高"可信度。
7. 不要编造外部事实。

source_context_type 必须准确：
- article_body: 正常正文
- related_links: 相关资讯/推荐阅读列表
- aggregator_card: 聚合卡片
- video_recommendation: 视频推荐
- search_snippet: 搜索结果摘要
- unknown: 不确定

如果 evidence 是 model_... - [**、相关资讯、/a/... - [** 等片段，应倾向：
source_context_type = related_links 或 aggregator_card
evidence_quality = low
action = reject

只返回 JSON：
{{
  "keep": true,
  "action": "keep",
  "target_match": true,
  "event_is_about_target": true,
  "event_subject_brand": "",
  "event_subject_model": "",
  "corrected_brand": "",
  "corrected_model": "",
  "event_type": "",
  "event_status": "已确认",
  "confidence": "中",
  "event_date": "",
  "source_publish_date": "",
  "date_basis": "source_publish_date",
  "date_confidence": "medium",
  "source_context_type": "article_body",
  "polluted_snippet": false,
  "conflict": false,
  "conflict_reason": "",
  "evidence_quality": "medium",
  "reason": ""
}}"""


# ─── LLM Judge: DeepSeek API call ────────────────────────────────

def call_deepseek_llm_judge(prompt: str, config: LLMJudgeConfig) -> dict:
    import requests
    api_key = os.environ.get(config.api_key_env, "")
    base_url = os.environ.get(config.base_url_env, "https://api.deepseek.com")
    model = os.environ.get("DEEPSEEK_MODEL", config.model or config.default_model)
    if not api_key:
        return {"_error": f"{config.api_key_env} not configured"}
    if not model:
        return {"_error": "DEEPSEEK_MODEL not configured"}
    try:
        resp = requests.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "max_tokens": 2000,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            return {"_error": f"API error {resp.status_code}: {resp.text[:200]}"}
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return {"_content": content}
    except Exception as e:
        return {"_error": str(e)[:500]}


# ─── LLM Judge: response parser ─────────────────────────────────

def parse_llm_judge_response(raw: str) -> tuple[LLMJudgeDecision | None, str]:
    text = raw.strip()
    if "```json" in text:
        parts = text.split("```json")
        if len(parts) >= 2:
            text = parts[1].split("```")[0].strip()
    elif "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1].strip()
            if text.startswith("json"):
                text = text[4:].strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return None, f"JSON decode error: {e}"
    if not isinstance(data, dict):
        return None, "response is not a dict"
    try:
        dec = LLMJudgeDecision(
            keep=data.get("keep", True),
            action=data.get("action", "keep") or "keep",
            target_match=data.get("target_match", True),
            event_is_about_target=data.get("event_is_about_target", True),
            event_subject_brand=data.get("event_subject_brand", ""),
            event_subject_model=data.get("event_subject_model", ""),
            corrected_brand=data.get("corrected_brand", ""),
            corrected_model=data.get("corrected_model", ""),
            event_type=data.get("event_type", ""),
            event_status=data.get("event_status", ""),
            confidence=data.get("confidence", "中"),
            event_date=data.get("event_date", ""),
            source_publish_date=data.get("source_publish_date", ""),
            date_basis=data.get("date_basis", ""),
            date_confidence=data.get("date_confidence", "medium"),
            source_context_type=data.get("source_context_type", "unknown"),
            polluted_snippet=bool(data.get("polluted_snippet", False)),
            conflict=bool(data.get("conflict", False)),
            conflict_reason=data.get("conflict_reason", ""),
            evidence_quality=data.get("evidence_quality", "medium") or "medium",
            reason=data.get("reason", ""),
        )
        return dec, ""
    except Exception as e:
        return None, f"parse error: {e}"


# ─── LLM Judge: cache ───────────────────────────────────────────

def build_llm_judge_cache_key(event: dict, target: WatchTarget) -> str:
    import hashlib
    ev_text = (event.get("evidence", "") or "")[:100]
    ev_hash = hashlib.md5(ev_text.encode("utf-8")).hexdigest()[:16]
    is_polluted, _ = is_polluted_evidence_snippet(event.get("evidence", "") or "")
    raw = "|".join([
        LLM_JUDGE_PROMPT_VERSION,
        LLM_JUDGE_SCHEMA_VERSION,
        LLM_JUDGE_GUARD_VERSION,
        target.target_id,
        event.get("source_url", ""),
        event.get("event_type", ""),
        event.get("date", ""),
        ev_hash,
        (event.get("source_title", "") or "")[:50],
        event.get("date_basis", ""),
        event.get("brand", ""),
        event.get("model", ""),
        event.get("confidence", ""),
        event.get("event_status", ""),
        str(int(is_polluted)),
    ])
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def load_llm_judge_cache(path: Path) -> dict:
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_llm_judge_cache(path: Path, cache: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


# ─── LLM Judge: apply decision ──────────────────────────────────

def apply_llm_judge_decision(event: dict, decision: LLMJudgeDecision,
                               diagnostics: CrawlDiagnostics | None = None) -> tuple[dict | None, str]:
    if not decision.keep or decision.action == "discard":
        return None, f"llm_discard:{decision.reason}"
    event["llm_judged"] = True
    event["llm_action"] = decision.action
    event["llm_reason"] = decision.reason
    event["llm_evidence_quality"] = decision.evidence_quality
    event["llm_source_context_type"] = decision.source_context_type
    if decision.corrected_brand:
        event["brand"] = decision.corrected_brand
    if decision.corrected_model:
        event["model"] = decision.corrected_model
    if decision.event_status:
        event["event_status"] = decision.event_status
    if decision.confidence:
        event["confidence"] = decision.confidence
    if decision.event_date:
        event["event_date"] = decision.event_date
        event["date_basis"] = "event_date"
        event["date_confidence"] = decision.date_confidence or "medium"
    if decision.date_basis:
        event["date_basis"] = decision.date_basis
    if decision.date_confidence:
        event["date_confidence"] = decision.date_confidence
    st = event.get("source_type", "")
    urls = event.get("source_urls", [])
    has_official = "official" in st
    has_cross = len(urls) >= 2 if urls else False
    if decision.confidence == "高" and not has_official and not has_cross:
        event["confidence"] = "中"
    if decision.confidence == "高" and not has_official and decision.evidence_quality in ("weak", "medium"):
        event["confidence"] = "中"
    if decision.confidence == "高" and not has_official and decision.source_context_type == "related_news":
        event["confidence"] = "中"
    evidence_text = event.get("evidence", "") or ""
    ev_polluted, _ = is_polluted_evidence_snippet(evidence_text)
    if ev_polluted:
        event["confidence"] = "低"
        event["event_status"] = "待确认"
    return event, ""


# ─── v0.5.4: Event scope classification ─────────────────────────

def classify_event_scope(
    evidence: str,
    title: str = "",
    source_url: str = "",
    event_type: str = "",
) -> str:
    text = " ".join(filter(None, [evidence, title]))
    # dealer patterns
    dealer_pats = ["门店上市", "经销商上市", "到店", "到店实拍", "门店品鉴", "品鉴会", "交付中心", "体验中心"]
    for dp in dealer_pats:
        if dp in text:
            return EVENT_SCOPE_DEALER
    # media patterns
    media_pats = ["媒体预热", "媒体试驾", "抢先体验", "静态体验", "实拍", "图解", "导购", "配置解析"]
    for mp in media_pats:
        if mp in text:
            return EVENT_SCOPE_MEDIA
    # auto_show patterns (non-上市 event types)
    show_pats = ["车展亮相", "车展首发", "车展发布"]
    for sp in show_pats:
        if sp in text:
            return EVENT_SCOPE_AUTO_SHOW
    # regional patterns: city_name + 上市/city_name + 车展上市
    for city in SCOPE_CITY_NAMES:
        if city in text:
            if f"{city}车展上市" in text and event_type == "上市":
                return EVENT_SCOPE_REGIONAL
            if f"{city}区域上市" in text or f"{city}区域正式上市" in text:
                return EVENT_SCOPE_REGIONAL
            if f"{city}上市" in text:
                return EVENT_SCOPE_REGIONAL
            if f"{city}车展" in text:
                return EVENT_SCOPE_AUTO_SHOW
    regional_generic = ["区域上市", "区域正式上市", "地方上市", "地方车展上市", "巡展上市"]
    for rg in regional_generic:
        if rg in text:
            return EVENT_SCOPE_REGIONAL
    # national patterns
    national_pats = ["正式上市", "全国上市", "全球上市", "官方上市", "品牌发布会",
                     "官方发布", "上市发布会", "全系上市", "新车上市"]
    for np in national_pats:
        if np in text:
            return EVENT_SCOPE_NATIONAL
    # auto_show by event_type
    show_event_pats = ["重庆车展", "上海车展", "北京车展", "成都车展", "广州车展"]
    for sep in show_event_pats:
        if sep in text:
            return EVENT_SCOPE_AUTO_SHOW
    # media by event_type
    if event_type == "媒体预热":
        return EVENT_SCOPE_MEDIA
    return EVENT_SCOPE_UNKNOWN


# ─── Search query construction ───────────────────────────────────

def build_search_queries(start, end, market, filters: MonitorFilters, max_results, targets=None):
    date_range = f"{start} 到 {end}"

    if targets:
        queries = []
        for t in targets:
            if t.priority == "high":
                q = f"{date_range} {market} {t.display_name} {' '.join(filters.keywords[:2])}"
                queries.append((q, t.target_id))
                for alias in t.model_aliases[:1]:
                    q = f"{date_range} {market} {alias} {filters.keywords[0]}"
                    if q not in [x[0] for x in queries]:
                        queries.append((q, t.target_id))
            else:
                q = f"{date_range} {market} {t.display_name} {filters.keywords[0]}"
                queries.append((q, t.target_id))
        return queries

    queries = []
    if filters.brands:
        for brand in filters.brands:
            for kw in filters.keywords:
                q = f"{date_range} {market} {brand} {kw}"
                queries.append((q, kw))
    else:
        for kw in filters.keywords:
            q = f"{date_range} {market} {kw}"
            queries.append((q, kw))

    if not queries:
        default_topics = ["新车发布会", "新车上市", "新车预售", "新车亮相", "开启交付", "新车发布"]
        for t in default_topics:
            q = f"{date_range} {market} {t}"
            queries.append((q, t))

    return queries


# ─── Search / scrape ─────────────────────────────────────────────

def tavily_search(client, query, max_results):
    try:
        response = client.search(query=query, search_depth="advanced", max_results=max_results)
        return response.get("results", [])
    except Exception as e:
        print(f"[WARN] Tavily search error: {e}", file=sys.stderr)
        return []


def dedup_urls(results):
    seen = set()
    deduped = []
    for r in results:
        url = r.get("url", "")
        if url and url not in seen:
            seen.add(url)
            deduped.append(r)
    return deduped


# ─── Domain classification ───────────────────────────────────────

def classify_domain(url):
    domain = urlparse(url).netloc.lower()
    path = urlparse(url).path.lower()

    for sd in SOCIAL_MEDIA_DOMAINS:
        if sd in domain:
            return "social"

    for ad in AGGREGATOR_DOMAINS:
        if ad in domain:
            return "aggregator"

    for ud in UGC_DOMAINS:
        if ud in domain or (ud.split("/")[0] in domain and ud.split("/")[1] in path):
            return "ugc_media"

    for od in OFFICIAL_DOMAINS:
        if od in domain:
            return "official"
    for md in MAINSTREAM_DOMAINS:
        if md in domain:
            return "mainstream"
    for ind in INDUSTRY_DOMAINS:
        if ind in domain:
            return "industry_media"
    for ld in LOW_QUALITY_DOMAINS:
        if ld in domain:
            return "low"
    return "normal"


def map_source_type(raw: str) -> str:
    return SOURCE_TYPE_MAP.get(raw, "unknown")


def has_exclude_keywords(text, exclude_keywords):
    for ek in exclude_keywords:
        if ek in text:
            return True
    return False


# ─── URL pre-filter ──────────────────────────────────────────────

def should_skip_url_before_crawl(url: str, source_types: list[str]) -> tuple[bool, str]:
    raw_type = classify_domain(url)
    st = map_source_type(raw_type)

    if st in LOW_QUALITY_SOURCE_TYPES and st not in source_types:
        return True, f"source_type '{st}' not in allowed list"

    return False, ""


# ─── Event extraction ────────────────────────────────────────────

def try_parse_event_date(text: str) -> tuple[str, str, str]:
    patterns = [
        (r"于\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", "high"),
        (r"(\d{4})年(\d{1,2})月(\d{1,2})日", "high"),
        (r"(\d{1,2})月(\d{1,2})日.*?(?:上市|发布|预售|亮相|交付)", "medium"),
    ]
    for pat, conf in patterns:
        m = re.search(pat, text)
        if m:
            groups = m.groups()
            if len(groups) == 2:
                month, day = int(groups[0]), int(groups[1])
                now = datetime.now()
                year = now.year
                if month < 1 or month > 12 or day < 1 or day > 31:
                    continue
                return f"{year:04d}-{month:02d}-{day:02d}", "event_date", conf
            elif len(groups) == 3:
                return f"{int(groups[0]):04d}-{int(groups[1]):02d}-{int(groups[2]):02d}", "event_date", conf
    return "", "", ""


def extract_events_from_markdown(markdown_text, url, source_title,
                                  start_date=None, end_date=None,
                                  exclude_keywords=None,
                                  source_publish_date=None):
    events = []
    text = markdown_text
    exclude_keywords = exclude_keywords or []

    event_keywords = {
        "发布会": ["发布会", "正式发布"],
        "上市": ["上市", "正式上市"],
        "预售": ["预售", "开启预售"],
        "首发亮相": ["首秀", "首发亮相", "首发"],
        "开启交付": ["开启交付", "首批交付"],
        "官图发布": ["官图", "官宣图"],
        "媒体预热": ["预热", "预告"],
    }

    source_type_raw = classify_domain(url)

    for date_matched in re.finditer(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text):
        ev_date = f"{int(date_matched.group(1)):04d}-{int(date_matched.group(2)):02d}-{int(date_matched.group(3)):02d}"
        if start_date and ev_date < start_date:
            continue
        if end_date and ev_date > end_date:
            continue

        ctx_start = max(0, date_matched.start() - 100)
        ctx_end = min(len(text), date_matched.end() + 200)
        context = text[ctx_start:ctx_end]

        for ev_type, keywords in event_keywords.items():
            for kw in keywords:
                if kw in context:
                    ev_start = max(0, context.find(kw) - 40)
                    ev_end = min(len(context), context.find(kw) + 60)
                    evidence = context[ev_start:ev_end].replace("\n", " ").strip()
                    brand, model = extract_brand_model(context)

                    is_excluded = has_exclude_keywords(context, exclude_keywords)
                    has_irrelevant = any(ik in context for ik in IRRELEVANT_KEYWORDS)
                    has_brand_model = bool(brand) or bool(model)

                    if is_excluded and source_type_raw not in ("official",):
                        event_status = "待确认"
                        confidence = "低"
                    elif has_irrelevant:
                        event_status = "待确认"
                        confidence = "低"
                    elif not has_brand_model and source_type_raw not in ("official",):
                        event_status = "待确认"
                        confidence = "低"
                    else:
                        event_status = "待确认" if ev_type == "媒体预热" else "已确认"
                        confidence = "高"

                    event_date, date_basis, date_confidence = try_parse_event_date(context)
                    if not event_date:
                        event_date = ev_date
                        date_basis = "source_publish_date"
                        date_confidence = "low"

                    events.append({
                        "date": event_date,
                        "event_date": event_date if date_basis == "event_date" else "",
                        "source_publish_date": source_publish_date or ev_date,
                        "date_basis": date_basis,
                        "date_confidence": date_confidence,
                        "brand": brand,
                        "model": model,
                        "event_type": ev_type,
                        "event_status": event_status,
                        "source_title": source_title,
                        "source_url": url,
                        "source_type": map_source_type(source_type_raw),
                        "confidence": confidence,
                        "evidence": evidence[:120],
                        "_has_excluded": is_excluded or has_irrelevant,
                    })
                    break

    for date_matched in re.finditer(r"(\d{4})-(\d{2})-(\d{2})", text):
        ev_date = f"{date_matched.group(1)}-{date_matched.group(2)}-{date_matched.group(3)}"
        if start_date and ev_date < start_date:
            continue
        if end_date and ev_date > end_date:
            continue
        try:
            datetime.strptime(ev_date, "%Y-%m-%d")
        except ValueError:
            continue

        ctx_start = max(0, date_matched.start() - 100)
        ctx_end = min(len(text), date_matched.end() + 200)
        context = text[ctx_start:ctx_end]

        for ev_type, keywords in event_keywords.items():
            for kw in keywords:
                if kw in context:
                    ev_start = max(0, context.find(kw) - 40)
                    ev_end = min(len(context), context.find(kw) + 60)
                    evidence = context[ev_start:ev_end].replace("\n", " ").strip()
                    brand, model = extract_brand_model(context)

                    is_excluded = has_exclude_keywords(context, exclude_keywords)
                    has_irrelevant = any(ik in context for ik in IRRELEVANT_KEYWORDS)
                    has_brand_model = bool(brand) or bool(model)

                    if is_excluded and source_type_raw not in ("official",):
                        event_status = "待确认"
                        confidence = "低"
                    elif has_irrelevant:
                        event_status = "待确认"
                        confidence = "低"
                    elif not has_brand_model and source_type_raw not in ("official",):
                        event_status = "待确认"
                        confidence = "低"
                    else:
                        event_status = "待确认" if ev_type == "媒体预热" else "已确认"
                        confidence = "高"

                    event_date, date_basis, date_confidence = try_parse_event_date(context)
                    if not event_date:
                        event_date = ev_date
                        date_basis = "source_publish_date"
                        date_confidence = "low"

                    events.append({
                        "date": event_date,
                        "event_date": event_date if date_basis == "event_date" else "",
                        "source_publish_date": source_publish_date or ev_date,
                        "date_basis": date_basis,
                        "date_confidence": date_confidence,
                        "brand": brand,
                        "model": model,
                        "event_type": ev_type,
                        "event_status": event_status,
                        "source_title": source_title,
                        "source_url": url,
                        "source_type": map_source_type(source_type_raw),
                        "confidence": confidence,
                        "evidence": evidence[:120],
                        "_has_excluded": is_excluded or has_irrelevant,
                    })
                    break

    return events


def extract_brand_model(text):
    known_brands = [
        "比亚迪", "特斯拉", "理想", "蔚来", "小鹏", "问界", "小米", "零跑",
        "极氪", "深蓝", "阿维塔", "智己", "飞凡", "埃安", "昊铂", "腾势",
        "仰望", "方程豹", "长城", "哈弗", "魏牌", "欧拉", "坦克",
        "吉利", "领克", "极星", "smart", "Smart", "奔驰", "宝马", "奥迪",
        "大众", "丰田", "本田", "日产", "福特", "通用", "别克", "雪佛兰",
        "凯迪拉克", "五菱", "宝骏", "捷途", "星途", "奇瑞", "东风",
        "长安", "一汽", "上汽", "广汽", "北汽", "江汽", "江淮",
        "捷豹", "路虎", "沃尔沃", "林肯", "猛士", "岚图", "神骐", "福田",
        "启源", "启境", "华境", "奕派", "奕境", "远航", "大运",
        "哪吒", "天际", "爱驰", "高合", "极狐", "创维",
    ]
    for brand in known_brands:
        if brand in text:
            idx = text.index(brand)
            after = text[idx + len(brand):].strip()
            model = ""
            for m in re.finditer(r"[\u4e00-\u9fffA-Z][\u4e00-\u9fffA-Z0-9\u00b7#\+\-]{0,15}", after):
                candidate = m.group().strip("-")
                if candidate and len(candidate) >= 1:
                    model = candidate
                    break
            return brand, model
    return "", ""


def scrape_url_with_retry(firecrawl_app, url, max_retries=2):
    for attempt in range(1 + max_retries):
        try:
            resp = firecrawl_app.scrape_url(url, formats=["markdown"])
            title = ""
            if hasattr(resp, "metadata") and resp.metadata is not None:
                meta = resp.metadata
                title = getattr(meta, "title", None) or getattr(meta, "ogTitle", "") or ""
            md = getattr(resp, "markdown", None) or ""
            if md:
                return {"url": url, "title": title or url, "markdown": md, "success": True}
            return {"url": url, "success": False, "error": "empty_markdown", "retries": attempt}
        except Exception as e:
            if attempt < max_retries:
                time.sleep(1.0 * (attempt + 1))
            last_error = e
    return {"url": url, "success": False,
            "error": str(last_error)[:200] if last_error else "unknown",
            "retries": max_retries}


def scrape_urls(firecrawl_app, urls, diagnostics: CrawlDiagnostics | None = None):
    results = []
    for url in urls:
        r = scrape_url_with_retry(firecrawl_app, url)
        if r["success"]:
            results.append(r)
            if diagnostics:
                diagnostics.crawled_page_count += 1
        else:
            if diagnostics:
                diagnostics.failed_crawl_count += 1
                diagnostics.failed_urls.append({
                    "url": url,
                    "error": r.get("error", "unknown"),
                })
            print(f"[WARN] Firecrawl scrape failed: {url} - {r.get('error', '')}", file=sys.stderr)
    return results


def normalize_date(d):
    return d.isoformat() if isinstance(d, date) else d


# ─── Target matching ─────────────────────────────────────────────

def match_event_to_target(event, targets: list[WatchTarget]) -> Optional[WatchTarget]:
    text_pool = " ".join([
        event.get("brand", ""),
        event.get("model", ""),
        event.get("source_title", ""),
        event.get("evidence", ""),
    ])

    for t in targets:
        brand_hit = has_target_brand_signal(text_pool, t)
        if not brand_hit:
            continue

        model_hit = has_target_model_signal(text_pool, t)
        if model_hit:
            model_strong = is_strong_model_match(text_pool, t)
            if model_strong:
                return t
            if any(alias in text_pool for alias in t.model_aliases):
                return t

    for t in targets:
        brand_hit = has_target_brand_signal(text_pool, t)
        if brand_hit:
            if is_strong_model_match(text_pool, t):
                return t

    return None


def match_events_to_targets(events, targets: list[WatchTarget]):
    matched = []
    for e in events:
        t = match_event_to_target(e, targets)
        if t:
            e["target_id"] = t.target_id
            e["target_display_name"] = t.display_name
            e["target_group"] = t.group
            e["target_priority"] = t.priority
            matched.append(e)
    return matched


# ─── Filtering ───────────────────────────────────────────────────

def apply_event_filters(events, filters: MonitorFilters):
    filtered = []
    for e in events:
        if filters.event_types and e.get("event_type") not in filters.event_types:
            continue
        if filters.brands and e.get("brand") not in filters.brands:
            continue
        if filters.source_types and e.get("source_type") not in filters.source_types:
            continue
        filtered.append(e)
    return filtered


# ─── Aggregation ─────────────────────────────────────────────────

def aggregate_events(events):
    buckets = {}
    for e in events:
        if e.get("target_id"):
            key = (e["target_id"], e["date"], e["event_type"])
        else:
            key = (e["date"], e["brand"], e["model"], e["event_type"])

        if key not in buckets:
            buckets[key] = {
                "date": e["date"],
                "brand": e["brand"],
                "model": e["model"],
                "event_type": e["event_type"],
                "event_status": e["event_status"],
                "source_urls": [],
                "source_titles": [],
                "source_types_raw": set(),
                "evidence": e["evidence"],
                "confidences": [],
                "_has_excluded": False,
                "target_id": e.get("target_id"),
                "target_display_name": e.get("target_display_name"),
                "target_group": e.get("target_group"),
                "target_priority": e.get("target_priority"),
                "event_date": e.get("event_date", ""),
                "source_publish_date": e.get("source_publish_date", ""),
                "date_basis": e.get("date_basis", ""),
                "date_confidence": e.get("date_confidence", ""),
            }
        b = buckets[key]
        if e["source_url"] not in b["source_urls"]:
            b["source_urls"].append(e["source_url"])
            b["source_titles"].append(e["source_title"])
        b["source_types_raw"].add(e.get("source_type", "unknown"))
        if len(e.get("evidence", "")) > len(b["evidence"]):
            b["evidence"] = e["evidence"]
        b["confidences"].append(e.get("confidence", "中"))
        if e.get("_has_excluded"):
            b["_has_excluded"] = True

    aggregated = []
    for key, b in buckets.items():
        has_official = "official" in b["source_types_raw"]
        mainstream_cnt = sum(1 for st in b["source_types_raw"] if st == "mainstream_media")
        unique_urls = b["source_urls"]

        if has_official:
            confidence = "高"
        elif len(unique_urls) >= 2:
            confidence = "高"
        elif mainstream_cnt >= 1:
            confidence = "中"
        else:
            confidence = "低"

        if b["_has_excluded"] and not has_official and len(unique_urls) < 2:
            confidence = "低"

        if not b["brand"] and not b["model"] and not b.get("target_id"):
            continue

        event_status = b["event_status"]
        if b["_has_excluded"] and event_status == "已确认":
            if not has_official and len(unique_urls) < 2:
                event_status = "待确认"

        row = {
            "date": b["date"],
            "brand": b["brand"],
            "model": b["model"],
            "event_type": b["event_type"],
            "event_status": event_status,
            "source_title": b["source_titles"][0],
            "source_url": b["source_urls"][0],
            "source_urls": b["source_urls"],
            "source_type": "|".join(sorted(b["source_types_raw"])),
            "confidence": confidence,
            "evidence": b["evidence"],
            "event_date": b.get("event_date", ""),
            "source_publish_date": b.get("source_publish_date", ""),
            "date_basis": b.get("date_basis", ""),
            "date_confidence": b.get("date_confidence", ""),
        }
        if b.get("target_id"):
            row.update({
                "target_id": b["target_id"],
                "target_display_name": b["target_display_name"],
                "target_group": b["target_group"],
                "target_priority": b["target_priority"],
            })
        aggregated.append(row)

    aggregated.sort(key=lambda e: e["date"])
    return aggregated


def build_event_summary(events, topic):
    total = len(events)
    confirmed = sum(1 for e in events if e.get("event_status") == "已确认")
    pending = sum(1 for e in events if e.get("event_status") == "待确认")
    type_counts = Counter(e.get("event_type", "其他") for e in events)
    high_conf = sum(1 for e in events if e.get("confidence") == "高")
    med_conf = sum(1 for e in events if e.get("confidence") == "中")
    low_conf = sum(1 for e in events if e.get("confidence") == "低")

    summary = {
        "total_events": total,
        "confirmed_events": confirmed,
        "pending_events": pending,
        "event_type_counts": dict(type_counts),
        "high_confidence_count": high_conf,
        "medium_confidence_count": med_conf,
        "low_confidence_count": low_conf,
    }

    if topic == "新车发布会" and type_counts.get("发布会", 0) == 0:
        summary["topic_note"] = "未发现明确发布会事件，但发现相关新车事件。"
    else:
        summary["topic_note"] = None

    return summary


# ─── Target hit/miss overview ───────────────────────────────────

def build_target_overview(targets: list[WatchTarget], events):
    hit_rows = []
    miss_rows = []
    hit_target_ids = set(e.get("target_id") for e in events if e.get("target_id"))

    for t in targets:
        matched_events = [e for e in events if e.get("target_id") == t.target_id]
        hit_count = len(matched_events)
        if hit_count > 0:
            best_conf = max(e.get("confidence", "低") for e in matched_events)
            latest = max(matched_events, key=lambda e: e.get("date", ""))
            latest_str = f"{latest['date']} {latest['event_type']}"
            hit_rows.append({
                "target_id": t.target_id,
                "display_name": t.display_name,
                "group": t.group,
                "priority": t.priority,
                "hit_count": hit_count,
                "best_confidence": best_conf,
                "latest_event": latest_str,
            })

    for t in targets:
        if t.target_id not in hit_target_ids:
            miss_rows.append({
                "target_id": t.target_id,
                "display_name": t.display_name,
                "group": t.group,
                "priority": t.priority,
            })

    hit_rows.sort(key=lambda r: (-r["hit_count"], r["target_id"]))
    miss_rows.sort(key=lambda r: r["target_id"])
    return hit_rows, miss_rows


# ─── main ────────────────────────────────────────────────────────

def main():
    args = parse_args()
    check_env()

    start_str = normalize_date(args.start)
    end_str = normalize_date(args.end)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    filters = build_filters(args)
    targets = None
    if args.targets_file:
        targets = load_watch_targets(args.targets_file)

    from tavily import TavilyClient
    from firecrawl import FirecrawlApp

    tavily_client = TavilyClient()
    firecrawl_app = FirecrawlApp()

    queries = build_search_queries(start_str, end_str, args.market, filters, args.max_results, targets=targets)
    diagnostics = CrawlDiagnostics(generated_query_count=len(queries))

    all_results = []
    for query, tag in queries:
        print(f"[INFO] 搜索: {query}", file=sys.stderr)
        results = tavily_search(tavily_client, query, args.max_results)
        for r in results:
            r["query_tag"] = tag
        all_results.extend(results)

    deduped = dedup_urls(all_results)
    diagnostics.dedup_url_count = len(deduped)

    def _priority(url):
        rt = classify_domain(url)
        if rt in ("official", "mainstream", "industry_media"):
            return 0
        return 1

    deduped.sort(key=lambda x: (_priority(x.get("url", "")), -x.get("score", 0)))

    pre_skip = []
    keep = []
    for r in deduped:
        url = r.get("url", "")
        skip, reason = should_skip_url_before_crawl(url, filters.source_types)
        if skip:
            pre_skip.append({"url": url, "reason": reason})
        else:
            keep.append(r)

    diagnostics.pre_crawl_skipped_count = len(pre_skip)
    diagnostics.pre_crawl_skipped_urls = pre_skip[:10]

    candidates = keep[:args.max_results]

    scrape_targets_list = [r["url"] for r in candidates if r.get("url")]
    diagnostics.planned_crawl_count = len(scrape_targets_list)
    print(f"[INFO] 候选 URL 去重后: {len(deduped)}，预过滤跳过: {len(pre_skip)}，将抓取: {len(scrape_targets_list)}", file=sys.stderr)

    scraped_pages = scrape_urls(firecrawl_app, scrape_targets_list, diagnostics=diagnostics)

    raw_events = []
    for page in scraped_pages:
        source_title = page["title"]
        events = extract_events_from_markdown(
            page["markdown"], page["url"], source_title,
            start_date=start_str, end_date=end_str,
            exclude_keywords=filters.exclude_keywords,
            source_publish_date=None,
        )
        raw_events.extend(events)

    diagnostics.raw_extracted_event_count = len(raw_events)

    raw_events = apply_event_filters(raw_events, filters)
    diagnostics.source_filtered_count = diagnostics.raw_extracted_event_count - len(raw_events)

    if targets:
        raw_events = match_events_to_targets(raw_events, targets)
        diagnostics.target_matched_event_count = len(raw_events)

        conflict_filtered = []
        for e in raw_events:
            tid = e.get("target_id")
            if not tid:
                conflict_filtered.append(e)
                continue
            t = next((t for t in targets if t.target_id == tid), None)
            if not t:
                conflict_filtered.append(e)
                continue
            conflict, reason = detect_target_conflict(e, t, targets)
            if conflict:
                diagnostics.conflict_filtered_count += 1
                diagnostics.conflict_filtered_events.append({
                    "target_id": tid,
                    "event_brand": e.get("brand", ""),
                    "event_model": e.get("model", ""),
                    "reason": reason,
                })
                continue
            conflict_filtered.append(e)
        raw_events = conflict_filtered

    llm_judge_config = LLMJudgeConfig(
        enabled=args.llm_judge,
        mode=args.llm_judge_mode,
        max_candidates=args.llm_judge_max,
        cache_enabled=not args.no_llm_judge_cache,
    )
    if llm_judge_config.enabled:
        diagnostics.llm_judge_enabled = True
        diagnostics.llm_judge_mode = llm_judge_config.mode
        ak = os.environ.get(llm_judge_config.api_key_env, "")
        if not ak:
            print(f"[ERROR] LLM Judge enabled but {llm_judge_config.api_key_env} is not configured",
                  file=sys.stderr)
            sys.exit(1)
        mdl = os.environ.get("DEEPSEEK_MODEL", "")
        if not mdl:
            mdl = llm_judge_config.default_model
            print(f"[WARN] DEEPSEEK_MODEL not set, defaulting to '{mdl}'", file=sys.stderr)
        llm_judge_config.model = mdl
        llm_cache = {}
        if llm_judge_config.cache_enabled:
            llm_cache = load_llm_judge_cache(LLM_JUDGE_CACHE_PATH)
        candidates_for_llm = []
        for e in raw_events:
            tid = e.get("target_id")
            if not tid:
                continue
            t = next((t for t in targets if t.target_id == tid), None) if targets else None
            if not t:
                continue
            send, reason = should_send_to_llm_judge(
                e, t, mode=llm_judge_config.mode,
                start_date=start_str, end_date=end_str,
            )
            if send:
                candidates_for_llm.append((e, t, reason))
        diagnostics.llm_judge_candidate_count = len(candidates_for_llm)
        selected = candidates_for_llm[:llm_judge_config.max_candidates]
        kept_events = []
        for event, tgt, sel_reason in selected:
            ck = build_llm_judge_cache_key(event, tgt)
            cached = llm_cache.get(ck) if llm_judge_config.cache_enabled else None
            cache_hit_valid = False
            if cached is not None:
                if isinstance(cached, dict) and cached.get("prompt_version"):
                    cache_hit_valid = True
                elif isinstance(cached, str):
                    pass
            if cached and cache_hit_valid:
                diagnostics.llm_judge_cache_hit_count += 1
                raw_text = cached.get("decision", cached) if isinstance(cached, dict) else cached
                dec, parse_err = parse_llm_judge_response(raw_text)
            elif cached and not cache_hit_valid and llm_judge_config.cache_enabled:
                diagnostics.llm_judge_cache_stale_count += 1
                diagnostics.llm_judge_cache_miss_count += 1
                diagnostics.llm_judge_cache_miss_count += 1
                diagnostics.llm_judge_called_count += 1
                prompt = build_llm_judge_prompt(event, tgt, start_date=start_str, end_date=end_str)
                ev_text = event.get("evidence", "") or ""
                p_polluted, _ = is_polluted_evidence_snippet(ev_text)
                if p_polluted:
                    diagnostics.polluted_evidence_llm_prompt_count += 1
                llm_resp = call_deepseek_llm_judge(prompt, llm_judge_config)
                if "_error" in llm_resp:
                    diagnostics.llm_judge_error_count += 1
                    kept_events.append(event)
                    continue
                raw_text = llm_resp.get("_content", "")
                if llm_judge_config.cache_enabled:
                    llm_cache[ck] = {
                        "prompt_version": LLM_JUDGE_PROMPT_VERSION,
                        "schema_version": LLM_JUDGE_SCHEMA_VERSION,
                        "guard_version": LLM_JUDGE_GUARD_VERSION,
                        "created_at": datetime.now().isoformat(),
                        "decision": raw_text,
                    }
                    save_llm_judge_cache(LLM_JUDGE_CACHE_PATH, llm_cache)
                dec, parse_err = parse_llm_judge_response(raw_text)
            if dec is None:
                diagnostics.llm_judge_error_count += 1
                kept_events.append(event)
                continue
            if dec.action == "downgrade" and has_reject_intent(dec.reason):
                dec.action = "discard"
                diagnostics.llm_reject_intent_discard_count += 1
            result_event, apply_err = apply_llm_judge_decision(event, dec, diagnostics=diagnostics)
            if result_event is None:
                diagnostics.llm_judge_discard_count += 1
            elif dec.action == "downgrade":
                diagnostics.llm_judge_downgrade_count += 1
                kept_events.append(result_event)
            else:
                diagnostics.llm_judge_keep_count += 1
                kept_events.append(result_event)
            if len(diagnostics.llm_judge_samples) < 10:
                diagnostics.llm_judge_samples.append({
                    "target_id": tgt.target_id,
                    "action": dec.action,
                    "evidence_quality": dec.evidence_quality,
                    "source_context_type": dec.source_context_type,
                    "reason": dec.reason,
                    "evidence": (event.get("evidence") or "")[:60],
                })
        non_candidate_events = []
        for e in raw_events:
            tid = e.get("target_id")
            if not tid:
                non_candidate_events.append(e)
                continue
            t = next((t for t in targets if t.target_id == tid), None) if targets else None
            if not t:
                non_candidate_events.append(e)
                continue
            send, _ = should_send_to_llm_judge(
                e, t, mode=llm_judge_config.mode,
                start_date=start_str, end_date=end_str,
            )
            if not send:
                non_candidate_events.append(e)
        raw_events = kept_events + non_candidate_events

    raw_events = apply_final_event_guard(
        raw_events, targets,
        start_date=start_str, end_date=end_str,
        diagnostics=diagnostics,
    )

    events = aggregate_events(raw_events)

    events = post_aggregate_normalize(events, diagnostics=diagnostics)
    diagnostics.final_event_count = len(events)

    summary = build_event_summary(events, args.topic)

    watchlist_info = None
    target_overview_hits = []
    target_overview_misses = []
    if targets:
        watchlist_info = {
            "targets_file": args.targets_file,
            "watchlist_name": targets[0].watchlist_name if targets else "",
            "active_target_count": len(targets),
        }
        target_overview_hits, target_overview_misses = build_target_overview(targets, events)

    base_name = f"auto_launch_monitor_{start_str}_{end_str}"

    if args.format == "json":
        output = {
            "filters": filters.to_dict(),
            "watchlist": watchlist_info,
            "target_summary": target_overview_hits,
            "missed_targets": target_overview_misses,
            "diagnostics": {
                "generated_query_count": diagnostics.generated_query_count,
                "dedup_url_count": diagnostics.dedup_url_count,
                "pre_crawl_skipped_count": diagnostics.pre_crawl_skipped_count,
                "planned_crawl_count": diagnostics.planned_crawl_count,
                "crawled_page_count": diagnostics.crawled_page_count,
                "failed_crawl_count": diagnostics.failed_crawl_count,
                "raw_extracted_event_count": diagnostics.raw_extracted_event_count,
                "source_filtered_count": diagnostics.source_filtered_count,
                "target_matched_event_count": diagnostics.target_matched_event_count,
                "conflict_filtered_count": diagnostics.conflict_filtered_count,
                "final_guard_filtered_count": diagnostics.final_guard_filtered_count,
                "out_of_range_event_count": diagnostics.out_of_range_event_count,
                "brand_model_conflict_count": diagnostics.brand_model_conflict_count,
                "evidence_irrelevant_count": diagnostics.evidence_irrelevant_count,
                "date_basis_downgraded_count": diagnostics.date_basis_downgraded_count,
                "polluted_snippet_count": diagnostics.polluted_snippet_count,
                "confidence_downgraded_count": diagnostics.confidence_downgraded_count,
                "status_downgraded_count": diagnostics.status_downgraded_count,
                "final_event_count": diagnostics.final_event_count,
                "llm_judge_enabled": diagnostics.llm_judge_enabled,
                "llm_judge_mode": diagnostics.llm_judge_mode,
                "llm_judge_candidate_count": diagnostics.llm_judge_candidate_count,
                "llm_judge_called_count": diagnostics.llm_judge_called_count,
                "llm_judge_cache_hit_count": diagnostics.llm_judge_cache_hit_count,
                "llm_judge_cache_miss_count": diagnostics.llm_judge_cache_miss_count,
                "llm_judge_keep_count": diagnostics.llm_judge_keep_count,
                "llm_judge_discard_count": diagnostics.llm_judge_discard_count,
                "llm_judge_downgrade_count": diagnostics.llm_judge_downgrade_count,
                "llm_judge_error_count": diagnostics.llm_judge_error_count,
                "historical_downgraded_count": diagnostics.historical_downgraded_count,
                "source_pub_empty_brand_model_count": diagnostics.source_pub_empty_brand_model_count,
                "source_publish_date_guard_count": diagnostics.source_publish_date_guard_count,
                "historical_event_filtered_count": diagnostics.historical_event_filtered_count,
                "missing_core_entity_filtered_count": diagnostics.missing_core_entity_filtered_count,
                "polluted_evidence_llm_prompt_count": diagnostics.polluted_evidence_llm_prompt_count,
                "llm_reject_intent_discard_count": diagnostics.llm_reject_intent_discard_count,
                "low_confidence_polluted_filtered_count": diagnostics.low_confidence_polluted_filtered_count,
                "llm_judge_cache_version": LLM_JUDGE_PROMPT_VERSION,
                "llm_judge_cache_stale_count": diagnostics.llm_judge_cache_stale_count,
                "llm_judge_cache_bypass_count": diagnostics.llm_judge_cache_bypass_count,
                "event_scope_classified_count": diagnostics.event_scope_classified_count,
                "national_event_count": diagnostics.national_event_count,
                "regional_event_count": diagnostics.regional_event_count,
                "dealer_event_count": diagnostics.dealer_event_count,
                "auto_show_event_count": diagnostics.auto_show_event_count,
                "media_event_count": diagnostics.media_event_count,
                "unknown_event_scope_count": diagnostics.unknown_event_scope_count,
                "non_national_event_filtered_count": diagnostics.non_national_event_filtered_count,
                "related_event_count": diagnostics.related_event_count,
                "failed_urls": diagnostics.failed_urls[:10],
            },
            "summary": summary,
            "events": events,
        }
        out_path = out_dir / f"{base_name}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(json.dumps(output, ensure_ascii=False, indent=2))

    elif args.format == "csv":
        out_path = out_dir / f"{base_name}.csv"
        flat = []
        for e in events:
            row = dict(e)
            row.pop("source_urls", None)
            flat.append(row)
        if flat:
            fieldnames = ["target_id", "target_display_name", "target_group", "target_priority",
                          "date", "event_date", "source_publish_date", "date_basis", "date_confidence",
                          "brand", "model", "event_type", "event_status",
                          "confidence", "source_type", "source_url", "evidence",
                          "llm_judged", "llm_action", "llm_reason", "llm_evidence_quality",
                          "llm_source_context_type"]
            with open(out_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(flat)
        else:
            out_path.write_text("target_id,target_display_name,date,brand,model,event_type,event_status,confidence,source_url,evidence\n")
        print(f"[Output] CSV: {out_path}")

    else:
        out_path = out_dir / f"{base_name}.md"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(format_markdown(events, summary, start_str, end_str, args.topic, filters,
                                    watchlist_info, target_overview_hits, target_overview_misses,
                                    diagnostics=diagnostics))
        print(format_markdown(events, summary, start_str, end_str, args.topic, filters,
                              watchlist_info, target_overview_hits, target_overview_misses,
                              diagnostics=diagnostics))

    print(f"\n[Summary] 共找到 {len(events)} 个事件", file=sys.stderr)
    print(f"[Output] {out_path}", file=sys.stderr)


# ─── Markdown output ─────────────────────────────────────────────

def format_markdown(events, summary, start_str, end_str, topic,
                    filters: Optional[MonitorFilters] = None,
                    watchlist_info=None, target_overview_hits=None,
                    target_overview_misses=None,
                    diagnostics: Optional[CrawlDiagnostics] = None):
    lines = []
    lines.append("# 汽车新车事件监测报告")
    lines.append("")
    lines.append(f"**查询时间范围**: {start_str} 至 {end_str}")
    lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**查询主题**: {topic}")
    lines.append(f"**事件总数**: {summary['total_events']}")
    lines.append("")

    lines.append("## 过滤条件")
    lines.append("")
    if watchlist_info:
        lines.append(f"| 维度 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 关注文件 | `{watchlist_info['targets_file']}` |")
        lines.append(f"| 关注列表 | `{watchlist_info['watchlist_name']}` |")
        lines.append(f"| 目标数量 | {watchlist_info['active_target_count']} 个 |")
        lines.append(f"| 事件类型 | {', '.join(filters.event_types) if filters else '-'} |")
        lines.append(f"| 来源类型 | {', '.join(filters.source_types) if filters else '-'} |")
        lines.append(f"| 排除关键词 | {', '.join(filters.exclude_keywords) if filters else '-'} |")
    elif filters:
        lines.append(f"| 维度 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 品牌 | {', '.join(filters.brands) if filters.brands else '不限'} |")
        lines.append(f"| 事件类型 | {', '.join(filters.event_types)} |")
        lines.append(f"| 来源类型 | {', '.join(filters.source_types)} |")
        lines.append(f"| 正向关键词 | {', '.join(filters.keywords)} |")
        lines.append(f"| 排除关键词 | {', '.join(filters.exclude_keywords)} |")
    lines.append("")

    topic_note = summary.get("topic_note")
    if topic_note:
        lines.append(f"> {topic_note}")
        lines.append("")

    if target_overview_hits is not None:
        lines.append("## 关注车型命中概览")
        lines.append("")
        lines.append("| target_id | 车型 | 分组 | 优先级 | 命中数 | 最高可信度 | 最新事件 |")
        lines.append("|-----------|------|------|--------|--------|-----------|----------|")
        seen_ids = set()
        if target_overview_hits:
            for r in target_overview_hits:
                seen_ids.add(r["target_id"])
                lines.append(f"| {r['target_id']} | {r['display_name']} | {r['group']} | "
                             f"{r['priority']} | {r['hit_count']} | {r['best_confidence']} | {r['latest_event']} |")
        for r in (target_overview_misses or []):
            if r["target_id"] not in seen_ids:
                lines.append(f"| {r['target_id']} | {r['display_name']} | {r['group']} | "
                             f"{r['priority']} | 0 | - | 未发现明确新车事件 |")
        lines.append("")

    if target_overview_misses:
        lines.append("## 未命中关注车型")
        lines.append("")
        lines.append("| target_id | 车型 | 分组 | 优先级 | 说明 |")
        lines.append("|-----------|------|------|--------|------|")
        for r in target_overview_misses:
            lines.append(f"| {r['target_id']} | {r['display_name']} | {r['group']} | "
                         f"{r['priority']} | 本次时间范围内未发现符合过滤条件的明确新车事件 |")
        lines.append("")

    if not events:
        lines.append("> 未找到符合条件的事件。")
        lines.append("")
        if not target_overview_hits and not target_overview_misses:
            lines.extend(_build_diagnostics_section(diagnostics))
            return "\n".join(lines)

    lines.append("## 事件统计")
    lines.append("")
    lines.append(f"| 指标 | 数值 |")
    lines.append(f"|------|------|")
    lines.append(f"| 总事件数 | {summary['total_events']} |")
    lines.append(f"| 已确认事件 | {summary['confirmed_events']} |")
    lines.append(f"| 待确认事件 | {summary['pending_events']} |")
    lines.append(f"| 高可信度 | {summary['high_confidence_count']} |")
    lines.append(f"| 中可信度 | {summary['medium_confidence_count']} |")
    lines.append(f"| 低可信度 | {summary['low_confidence_count']} |")
    lines.append("")

    if summary["event_type_counts"]:
        lines.append("| 事件类型 | 数量 |")
        lines.append("|----------|------|")
        for etype, count in sorted(summary["event_type_counts"].items()):
            lines.append(f"| {etype} | {count} |")
        lines.append("")

    lines.append("## 事件列表")
    lines.append("")
    if any(e.get("target_id") for e in events):
        lines.append("| target_id | 关注车型 | 日期 | 日期依据 | 品牌 | 车型 | 事件类型 | 状态 | 可信度 | 来源 | 证据 |")
        lines.append("|-----------|---------|------|---------|------|------|----------|------|--------|------|------|")
        for e in events:
            tid = e.get("target_id", "-")
            tdn = e.get("target_display_name", "-")
            source_link = f"[{e['source_title'][:25]}]({e['source_url']})" if e['source_url'] else e['source_title'][:25]
            brand = e.get("brand", "") or "-"
            model = e.get("model", "") or "-"
            evidence = e.get("evidence", "")[:40]
            db = e.get("date_basis", "-")
            lines.append(f"| {tid} | {tdn} | {e['date']} | {db} | {brand} | {model} | {e['event_type']} | {e['event_status']} | {e['confidence']} | {source_link} | {evidence} |")
    else:
        lines.append("| 日期 | 日期依据 | 品牌 | 车型 | 事件类型 | 状态 | 可信度 | 来源 | 证据 |")
        lines.append("|------|---------|------|------|----------|------|--------|------|------|")
        for e in events:
            source_link = f"[{e['source_title'][:25]}]({e['source_url']})" if e['source_url'] else e['source_title'][:25]
            brand = e.get("brand", "") or "-"
            model = e.get("model", "") or "-"
            evidence = e.get("evidence", "")[:50]
            db = e.get("date_basis", "-")
            lines.append(f"| {e['date']} | {db} | {brand} | {model} | {e['event_type']} | {e['event_status']} | {e['confidence']} | {source_link} | {evidence} |")

    lines.append("")
    lines.append("## 可信度规则")
    lines.append("")
    lines.append("| 等级 | 说明 |")
    lines.append("|------|------|")
    lines.append("| **高** | 官方来源（品牌官网）/ 2 个及以上主流汽车媒体交叉验证 |")
    lines.append("| **中** | 单一主流汽车媒体报道 |")
    lines.append("| **低** | 自媒体、论坛、聚合页、二次转载、无明确日期 / 命中排除关键词且非官方单来源 |")
    lines.append("")

    lines.append("## 事件状态说明")
    lines.append("")
    lines.append("| 状态 | 含义 |")
    lines.append("|------|------|")
    lines.append("| **已确认** | 有明确的官方发布、上市、交付信息 |")
    lines.append("| **待确认** | 媒体预热、推测、预告 / 命中排除关键词且非官方单来源 |")
    lines.append("")

    lines.append("## 数据源")
    lines.append("")
    lines.append("- 搜索引擎: Tavily (AI-powered web search)")
    lines.append("- 网页抓取: Firecrawl")
    lines.append("- 优先来源: 品牌官网、汽车之家、懂车帝、易车、太平洋汽车、盖世汽车、新出行、网通社等")
    lines.append("")

    if diagnostics:
        lines.extend(_build_diagnostics_section(diagnostics))

    return "\n".join(lines)


def _build_diagnostics_section(diagnostics: CrawlDiagnostics) -> list[str]:
    lines = []
    lines.append("## 监测质量诊断")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("|------|-----:|")
    lines.append(f"| generated_query_count | {diagnostics.generated_query_count} |")
    lines.append(f"| dedup_url_count | {diagnostics.dedup_url_count} |")
    lines.append(f"| pre_crawl_skipped_count | {diagnostics.pre_crawl_skipped_count} |")
    lines.append(f"| planned_crawl_count | {diagnostics.planned_crawl_count} |")
    lines.append(f"| crawled_page_count | {diagnostics.crawled_page_count} |")
    lines.append(f"| failed_crawl_count | {diagnostics.failed_crawl_count} |")
    lines.append(f"| raw_extracted_event_count | {diagnostics.raw_extracted_event_count} |")
    lines.append(f"| source_filtered_count | {diagnostics.source_filtered_count} |")
    lines.append(f"| target_matched_event_count | {diagnostics.target_matched_event_count} |")
    lines.append(f"| conflict_filtered_count | {diagnostics.conflict_filtered_count} |")
    lines.append(f"| final_guard_filtered_count | {diagnostics.final_guard_filtered_count} |")
    lines.append(f"| out_of_range_event_count | {diagnostics.out_of_range_event_count} |")
    lines.append(f"| brand_model_conflict_count | {diagnostics.brand_model_conflict_count} |")
    lines.append(f"| evidence_irrelevant_count | {diagnostics.evidence_irrelevant_count} |")
    lines.append(f"| date_basis_downgraded_count | {diagnostics.date_basis_downgraded_count} |")
    lines.append(f"| polluted_snippet_count | {diagnostics.polluted_snippet_count} |")
    lines.append(f"| confidence_downgraded_count | {diagnostics.confidence_downgraded_count} |")
    lines.append(f"| status_downgraded_count | {diagnostics.status_downgraded_count} |")
    lines.append(f"| final_event_count | {diagnostics.final_event_count} |")
    lines.append(f"| llm_judge_enabled | {diagnostics.llm_judge_enabled} |")
    lines.append(f"| llm_judge_mode | {diagnostics.llm_judge_mode} |")
    lines.append(f"| llm_judge_candidate_count | {diagnostics.llm_judge_candidate_count} |")
    lines.append(f"| llm_judge_called_count | {diagnostics.llm_judge_called_count} |")
    lines.append(f"| llm_judge_cache_hit_count | {diagnostics.llm_judge_cache_hit_count} |")
    lines.append(f"| llm_judge_cache_miss_count | {diagnostics.llm_judge_cache_miss_count} |")
    lines.append(f"| llm_judge_keep_count | {diagnostics.llm_judge_keep_count} |")
    lines.append(f"| llm_judge_discard_count | {diagnostics.llm_judge_discard_count} |")
    lines.append(f"| llm_judge_downgrade_count | {diagnostics.llm_judge_downgrade_count} |")
    lines.append(f"| llm_judge_error_count | {diagnostics.llm_judge_error_count} |")
    lines.append(f"| source_publish_date_guard_count | {diagnostics.source_publish_date_guard_count} |")
    lines.append(f"| historical_event_filtered_count | {diagnostics.historical_event_filtered_count} |")
    lines.append(f"| missing_core_entity_filtered_count | {diagnostics.missing_core_entity_filtered_count} |")
    lines.append(f"| polluted_evidence_llm_prompt_count | {diagnostics.polluted_evidence_llm_prompt_count} |")
    lines.append(f"| llm_reject_intent_discard_count | {diagnostics.llm_reject_intent_discard_count} |")
    lines.append(f"| low_confidence_polluted_filtered_count | {diagnostics.low_confidence_polluted_filtered_count} |")
    lines.append(f"| llm_judge_cache_version | {LLM_JUDGE_PROMPT_VERSION} |")
    lines.append(f"| llm_judge_cache_stale_count | {diagnostics.llm_judge_cache_stale_count} |")
    lines.append(f"| llm_judge_cache_bypass_count | {diagnostics.llm_judge_cache_bypass_count} |")
    lines.append(f"| event_scope_classified_count | {diagnostics.event_scope_classified_count} |")
    lines.append(f"| national_event_count | {diagnostics.national_event_count} |")
    lines.append(f"| regional_event_count | {diagnostics.regional_event_count} |")
    lines.append(f"| dealer_event_count | {diagnostics.dealer_event_count} |")
    lines.append(f"| auto_show_event_count | {diagnostics.auto_show_event_count} |")
    lines.append(f"| media_event_count | {diagnostics.media_event_count} |")
    lines.append(f"| unknown_event_scope_count | {diagnostics.unknown_event_scope_count} |")
    lines.append(f"| non_national_event_filtered_count | {diagnostics.non_national_event_filtered_count} |")
    lines.append(f"| related_event_count | {diagnostics.related_event_count} |")
    lines.append(f"| historical_downgraded_count | {diagnostics.historical_downgraded_count} |")
    lines.append(f"| source_pub_empty_brand_model_count | {diagnostics.source_pub_empty_brand_model_count} |")
    lines.append("")

    if diagnostics.pre_crawl_skipped_count > 0:
        lines.append("### 抓取前跳过 URL 样例")
        lines.append("")
        lines.append("| url | reason |")
        lines.append("|-----|--------|")
        for fu in diagnostics.pre_crawl_skipped_urls[:10]:
            lines.append(f"| {fu.get('url', '')} | {fu.get('reason', '')} |")
        lines.append("")

    if diagnostics.failed_crawl_count > 0:
        lines.append("### 抓取失败 URL 样例")
        lines.append("")
        lines.append("| url | error |")
        lines.append("|-----|-------|")
        for fu in diagnostics.failed_urls[:10]:
            err = fu.get("error", "")[:60]
            lines.append(f"| {fu['url']} | {err} |")
        lines.append("")
        lines.append("> 注意：未命中表示在当前时间范围、目标车型池、信源类型、事件类型和成功抓取页面范围内未发现明确事件；"
                     "如果 failed_crawl_count 较高，需复核抓取覆盖度。")
        lines.append("")

    if diagnostics.conflict_filtered_count > 0:
        lines.append("### 冲突过滤事件样例")
        lines.append("")
        lines.append("| target_id | event_brand | event_model | reason |")
        lines.append("|-----------|-------------|-------------|--------|")
        for ce in diagnostics.conflict_filtered_events[:10]:
            lines.append(f"| {ce.get('target_id', '')} | {ce.get('event_brand', '')} | {ce.get('event_model', '')} | {ce.get('reason', '')} |")
        lines.append("")

    if diagnostics.final_guard_filtered_count > 0:
        lines.append("### Final Guard 过滤样例")
        lines.append("")
        lines.append("| target_id | brand | model | event_date | reason | evidence |")
        lines.append("|-----------|-------|-------|------------|--------|----------|")
        for fe in diagnostics.final_guard_filtered_events[:10]:
            ev_snippet = fe.get("evidence_snippet", "")[:50]
            lines.append(f"| {fe.get('target_id', '')} | {fe.get('brand', '')} | {fe.get('model', '')} | {fe.get('event_date', '')} | {fe.get('reason', '')} | {ev_snippet} |")
        lines.append("")

    if diagnostics.degrade_samples:
        lines.append("### Final Guard 降级样例")
        lines.append("")
        lines.append("| target_id | reason | before_status | after_status | before_confidence | after_confidence | evidence |")
        lines.append("|-----------|--------|---------------|--------------|-------------------|------------------|----------|")
        for ds in diagnostics.degrade_samples[:10]:
            ev_snippet = ds.get("evidence_snippet", "")[:50]
            lines.append(f"| {ds.get('target_id', '')} | {ds.get('reason', '')} | {ds.get('before_status', '')} | {ds.get('after_status', '')} | {ds.get('before_confidence', '')} | {ds.get('after_confidence', '')} | {ev_snippet} |")
        lines.append("")

    if diagnostics.related_event_samples:
        lines.append("### 相关但非全国级事件")
        lines.append("")
        lines.append("| target_id | brand | model | event_date | event_type | scope | evidence |")
        lines.append("|-----------|-------|-------|------------|------------|-------|----------|")
        for s in diagnostics.related_event_samples[:10]:
            ev = s.get("evidence_snippet", "")[:50]
            lines.append(f"| {s.get('target_id', '')} | {s.get('brand', '')} | {s.get('model', '')} | {s.get('event_date', '')} | {s.get('event_type', '')} | {s.get('scope', '')} | {ev} |")
        lines.append("")

    if diagnostics.llm_judge_samples:
        lines.append("### LLM Judge 样例")
        lines.append("")
        lines.append("| target_id | action | evidence_quality | source_context_type | reason | evidence |")
        lines.append("|-----------|--------|-----------------|---------------------|--------|----------|")
        for s in diagnostics.llm_judge_samples[:10]:
            ev = s.get("evidence", "")[:50]
            lines.append(f"| {s.get('target_id', '')} | {s.get('action', '')} | {s.get('evidence_quality', '')} | {s.get('source_context_type', '')} | {s.get('reason', '')} | {ev} |")
        lines.append("")

    return lines


if __name__ == "__main__":
    main()
