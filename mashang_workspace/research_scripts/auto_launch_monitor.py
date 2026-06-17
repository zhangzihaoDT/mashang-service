#!/usr/bin/env python3
"""
汽车新车事件监测器 — Auto Launch Monitor (v0.4)

Market Intelligence / New Vehicle Event Monitor

查询指定日期范围内中国市场的汽车新车上市、预售、发布会、首发亮相、
开启交付等产品投放事件，输出可追溯的结构化市场情报报告。

当前范围: 新车事件（发布会/上市/预售/首发亮相/开启交付/官图发布/媒体预热/其他）
未覆盖: 价格变化、权益变化、销量异动、舆情热点、政策信息、渠道动作等

体系位置:
  市场情报 Market Intelligence
  ├── 新车事件监测 auto_launch_monitor.py     <- 当前 v0.4
  ├── 价格/权益监测 price_incentive_monitor.py
  ├── 销量/订单异动监测 sales_signal_monitor.py
  ├── 舆情热点监测 public_opinion_monitor.py
  ├── 政策/法规监测 policy_monitor.py
  └── 竞品动作周报 competitor_weekly_digest.py

阶段定义:
  v0.1 新车事件查询链路跑通
  v0.2 新车事件质量规则增强
  v0.3 可配置情报源 + 品牌/关键词过滤
  v0.4 关注车型池监测 (当前)

v0.4 新增功能:
  - --targets-file: 读取关注车型列表 CSV，按 target_id 做搜索扩展、结果过滤、车型归一化
  - 关注车型命中概览：展示每个目标车型的命中数、最高可信度、最新事件
  - 未命中关注车型列表：展示没有事件的车型
  - WatchTarget 数据结构 + match_event_to_target 匹配逻辑
  - 聚合 key 升级为 target_id + date + event_type

用法:
    python mashang_workspace/research_scripts/auto_launch_monitor.py \\
        --start 2026-06-05 --end 2026-06-07 \\
        --targets-file mashang_workspace/configs/ls8_competitor_watchlist.csv \\
        --source-types official,mainstream_media,industry_media \\
        --format markdown --output mashang_workspace/outputs/reports/

    # 未传 --targets-file 时保持 v0.3 行为不变
    python mashang_workspace/research_scripts/auto_launch_monitor.py \\
        --start 2026-06-05 --end 2026-06-07 \\
        --brands "智己,理想,小米" \\
        --event-types "发布会,上市,预售" \\
        --source-types "official,mainstream_media,industry_media"

环境变量:
    TAVILY_API_KEY      (必填) Tavily 搜索 API Key
    FIRECRAWL_API_KEY   (必填) Firecrawl 网页抓取 API Key

可信度规则:
    - 官方来源（品牌官网）= 高
    - 2 个及以上主流汽车媒体交叉验证同一事件 = 高
    - 单一主流汽车媒体 = 中
    - 自媒体、论坛、二次转载、无明确日期 = 低
"""

import argparse
import csv
import json
import os
import re
import sys
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

SOURCE_TYPE_MAP = {
    "official": "official",
    "mainstream": "mainstream_media",
    "industry_media": "industry_media",
    "social": "social_media",
    "social_media": "social_media",
    "forum": "forum",
    "low": "social_media",
    "normal": "unknown",
}

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
    "k.sina.com.cn", "sohu.com/a", "weibo.com",
]

SOCIAL_MEDIA_DOMAINS = [
    "chejiahao.autohome.com.cn",
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
    planned_crawl_count: int = 0
    crawled_page_count: int = 0
    failed_crawl_count: int = 0
    failed_urls: list[dict[str, str]] = field(default_factory=list)


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


# ─── Target matching ─────────────────────────────────────────────

def match_event_to_target(event, targets: list[WatchTarget]) -> Optional[WatchTarget]:
    text_pool = " ".join([
        event.get("brand", ""),
        event.get("model", ""),
        event.get("title", ""),
        event.get("source_title", ""),
        event.get("evidence", ""),
    ])

    for t in targets:
        brand_hit = any(alias in text_pool for alias in t.brand_aliases)
        if not brand_hit:
            continue
        model_hit = any(alias in text_pool for alias in t.model_aliases)
        if model_hit:
            return t

    for t in targets:
        brand_hit = any(alias in text_pool for alias in t.brand_aliases)
        if brand_hit:
            model_strong = any(
                alias in event.get("model", "") or alias in event.get("source_title", "")
                for alias in t.model_aliases
            )
            if model_strong:
                return t

    return None


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


def classify_domain(url):
    domain = urlparse(url).netloc.lower()
    for sd in SOCIAL_MEDIA_DOMAINS:
        if sd in domain:
            return "social"
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


# ─── Event extraction ────────────────────────────────────────────

def extract_events_from_markdown(markdown_text, url, source_title,
                                  start_date=None, end_date=None,
                                  exclude_keywords=None):
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

                    if is_excluded and source_type_raw not in ("official",):
                        event_status = "待确认"
                        confidence = "低"
                    else:
                        event_status = "待确认" if ev_type == "媒体预热" else "已确认"
                        confidence = "高"

                    events.append({
                        "date": ev_date,
                        "brand": brand,
                        "model": model,
                        "event_type": ev_type,
                        "event_status": event_status,
                        "source_title": source_title,
                        "source_url": url,
                        "source_type": map_source_type(source_type_raw),
                        "confidence": confidence,
                        "evidence": evidence[:120],
                        "_has_excluded": is_excluded,
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

                    if is_excluded and source_type_raw not in ("official",):
                        event_status = "待确认"
                        confidence = "低"
                    else:
                        event_status = "待确认" if ev_type == "媒体预热" else "已确认"
                        confidence = "高"

                    events.append({
                        "date": ev_date,
                        "brand": brand,
                        "model": model,
                        "event_type": ev_type,
                        "event_status": event_status,
                        "source_title": source_title,
                        "source_url": url,
                        "source_type": map_source_type(source_type_raw),
                        "confidence": confidence,
                        "evidence": evidence[:120],
                        "_has_excluded": is_excluded,
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
                __import__("time").sleep(1.0 * (attempt + 1))
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


# ─── Filtering ───────────────────────────────────────────────────

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
        else:
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
    candidates = deduped[:args.max_results]

    scrape_targets_list = [r["url"] for r in candidates if r.get("url")]
    diagnostics.planned_crawl_count = len(scrape_targets_list)
    print(f"[INFO] 候选 URL 去重后: {len(deduped)}，将抓取: {len(scrape_targets_list)}", file=sys.stderr)

    scraped_pages = scrape_urls(firecrawl_app, scrape_targets_list, diagnostics=diagnostics)

    raw_events = []
    for page in scraped_pages:
        source_title = page["title"]
        events = extract_events_from_markdown(
            page["markdown"], page["url"], source_title,
            start_date=start_str, end_date=end_str,
            exclude_keywords=filters.exclude_keywords,
        )
        raw_events.extend(events)

    raw_events = apply_event_filters(raw_events, filters)

    if targets:
        raw_events = match_events_to_targets(raw_events, targets)

    events = aggregate_events(raw_events)
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
                "planned_crawl_count": diagnostics.planned_crawl_count,
                "crawled_page_count": diagnostics.crawled_page_count,
                "failed_crawl_count": diagnostics.failed_crawl_count,
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
                          "date", "brand", "model", "event_type", "event_status",
                          "confidence", "source_type", "source_url", "evidence"]
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
        lines.append("| target_id | 关注车型 | 日期 | 品牌 | 车型 | 事件类型 | 状态 | 可信度 | 来源 | 证据 |")
        lines.append("|-----------|---------|------|------|------|----------|------|--------|------|------|")
        for e in events:
            tid = e.get("target_id", "-")
            tdn = e.get("target_display_name", "-")
            source_link = f"[{e['source_title'][:30]}]({e['source_url']})" if e['source_url'] else e['source_title'][:30]
            brand = e.get("brand", "") or "-"
            model = e.get("model", "") or "-"
            evidence = e.get("evidence", "")[:50]
            lines.append(f"| {tid} | {tdn} | {e['date']} | {brand} | {model} | {e['event_type']} | {e['event_status']} | {e['confidence']} | {source_link} | {evidence} |")
    else:
        lines.append("| 日期 | 品牌 | 车型 | 事件类型 | 状态 | 可信度 | 来源 | 证据 |")
        lines.append("|------|------|------|----------|------|--------|------|------|")
        for e in events:
            source_link = f"[{e['source_title'][:30]}]({e['source_url']})" if e['source_url'] else e['source_title'][:30]
            brand = e.get("brand", "") or "-"
            model = e.get("model", "") or "-"
            evidence = e.get("evidence", "")[:60]
            lines.append(f"| {e['date']} | {brand} | {model} | {e['event_type']} | {e['event_status']} | {e['confidence']} | {source_link} | {evidence} |")

    lines.append("")
    lines.append("## 可信度规则")
    lines.append("")
    lines.append("| 等级 | 说明 |")
    lines.append("|------|------|")
    lines.append("| **高** | 官方来源（品牌官网）/ 2 个及以上主流汽车媒体交叉验证 |")
    lines.append("| **中** | 单一主流汽车媒体报道 |")
    lines.append("| **低** | 自媒体、论坛、二次转载、无明确日期 / 命中排除关键词且非官方单来源 |")
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
    lines.append(f"| planned_crawl_count | {diagnostics.planned_crawl_count} |")
    lines.append(f"| crawled_page_count | {diagnostics.crawled_page_count} |")
    lines.append(f"| failed_crawl_count | {diagnostics.failed_crawl_count} |")
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

    return lines


if __name__ == "__main__":
    main()
