"""
Smoke test: auto_launch_monitor.py v0.4.1

验证:
1. load_watch_targets 读取、校验、aliases 拆分
2. 缺失 targets_file 报错
3. target 匹配（理想 i6 → li_i6, ONVO L80 → onvo_l80, ZEEKR 8X → zeekr_8x）
4. 品牌命中但车型不匹配不归入
5. targets-file 过滤
6. target 聚合逻辑
7. Markdown 包含命中概览 / 未命中 / filters 摘要
8. v0.3 兼容：不传 --targets-file 时原有逻辑不变
9. 13 个原有测试保持
10. Firecrawl 失败不抛出异常
11. retry 后成功不记失败
12. diagnostics 出现在 markdown 中
13. chejiahao.autohome.com.cn 分类为 social_media
"""

import json
import os
import subprocess
import sys
from pathlib import Path

_WS_DIR = Path(__file__).resolve().parents[2]
SCRIPT = _WS_DIR / "research_scripts" / "auto_launch_monitor.py"
_SCRIPT_DIR = _WS_DIR / "research_scripts"
CONFIGS_DIR = _WS_DIR / "configs"
WATCHLIST_CSV = CONFIGS_DIR / "ls8_competitor_watchlist.csv"


def _run(args: list[str], env_override: dict | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    if env_override:
        env.update(env_override)
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + args,
        capture_output=True, text=True, timeout=30,
        env=env,
    )


def _extract_py(env, code):
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=30,
        env=env,
    )


# ─── load_watch_targets ──────────────────────────────────────────

def test_load_watch_targets_returns_active():
    code = rf"""
import sys
sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets

targets = load_watch_targets(r"{WATCHLIST_CSV}")
assert len(targets) >= 10, f"expected >=10, got {{len(targets)}}"
for t in targets:
    assert t.active == True
print("OK count=", len(targets))
print("IDS:", [t.target_id for t in targets])
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"
    data = result.stdout
    assert "leapmotor_d19" in data
    assert "zeekr_8x" in data


def test_load_watch_targets_aliases_split():
    code = rf"""
import sys
sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets

targets = load_watch_targets(r"{WATCHLIST_CSV}")
for t in targets:
    assert len(t.brand_aliases) >= 1
    assert len(t.model_aliases) >= 1
    assert t.brand in t.brand_aliases
    assert t.model in t.model_aliases
zeekr = [t for t in targets if t.target_id == "zeekr_8x"][0]
assert "ZEEKR" in zeekr.brand_aliases
assert "Zeekr" in zeekr.brand_aliases
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_load_watch_targets_no_duplicate_ids():
    code = rf"""
import sys
sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets

targets = load_watch_targets(r"{WATCHLIST_CSV}")
ids = [t.target_id for t in targets]
assert len(ids) == len(set(ids)), "duplicate target_id found"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_load_watch_targets_file_not_found():
    code = rf"""
import sys
sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets
try:
    load_watch_targets("/nonexistent/path.csv")
except SystemExit:
    print("OK exit")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── target matching ─────────────────────────────────────────────

def test_match_li_i6():
    code = rf"""
import sys
sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets, match_event_to_target

targets = load_watch_targets(r"{WATCHLIST_CSV}")
event = {{"brand": "理想", "model": "i6", "title": "理想i6", "source_title": "", "evidence": ""}}
t = match_event_to_target(event, targets)
assert t is not None, "should match"
assert t.target_id == "li_i6", f"got {{t.target_id}}"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_match_onvo_l80():
    code = rf"""
import sys
sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets, match_event_to_target

targets = load_watch_targets(r"{WATCHLIST_CSV}")
event = {{"brand": "乐道", "model": "L80", "title": "ONVO L80", "source_title": "", "evidence": ""}}
t = match_event_to_target(event, targets)
assert t is not None, "should match"
assert t.target_id == "onvo_l80", f"got {{t.target_id}}"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_match_zeekr_8x():
    code = rf"""
import sys
sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets, match_event_to_target

targets = load_watch_targets(r"{WATCHLIST_CSV}")
event = {{"brand": "极氪", "model": "8X", "title": "ZEEKR 8X", "source_title": "", "evidence": ""}}
t = match_event_to_target(event, targets)
assert t is not None, "should match"
assert t.target_id == "zeekr_8x", f"got {{t.target_id}}"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_no_match_brand_only():
    code = rf"""
import sys
sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets, match_event_to_target

targets = load_watch_targets(r"{WATCHLIST_CSV}")
# 理想品牌但没有 i6 车型
event = {{"brand": "理想", "model": "L9", "title": "理想L9", "source_title": "", "evidence": ""}}
t = match_event_to_target(event, targets)
assert t is None, f"should NOT match li_i6, got {{t}}"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── targets-file filtering ──────────────────────────────────────

def test_targets_filter():
    code = rf"""
import sys
sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets, match_events_to_targets

targets = load_watch_targets(r"{WATCHLIST_CSV}")
events = [
    {{"brand": "理想", "model": "i6", "event_type": "上市", "source_url": "a", "source_title": "t"}},
    {{"brand": "理想", "model": "L9", "event_type": "上市", "source_url": "b", "source_title": "t"}},
    {{"brand": "乐道", "model": "L80", "event_type": "预售", "source_url": "c", "source_title": "t"}},
]
matched = match_events_to_targets(events, targets)
ids = [e.get("target_id") for e in matched]
assert "li_i6" in ids, f"li_i6 missing: {{ids}}"
assert "onvo_l80" in ids, f"onvo_l80 missing: {{ids}}"
assert len(matched) == 2, f"expected 2, got {{len(matched)}}: {{ids}}"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── target aggregation ──────────────────────────────────────────

def test_target_aggregation_same_target():
    code = rf"""
import sys, json
sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import aggregate_events

events = [
    {{"date":"2026-06-05","brand":"理想","model":"i6","event_type":"上市","event_status":"已确认",
      "source_title":"A","source_url":"url1","source_type":"mainstream_media","confidence":"高","evidence":"a","_has_excluded":False,
      "target_id":"li_i6","target_display_name":"理想 i6","target_group":"新势力SUV","target_priority":"high"}},
    {{"date":"2026-06-05","brand":"理想","model":"i6","event_type":"上市","event_status":"已确认",
      "source_title":"B","source_url":"url2","source_type":"mainstream_media","confidence":"高","evidence":"b","_has_excluded":False,
      "target_id":"li_i6","target_display_name":"理想 i6","target_group":"新势力SUV","target_priority":"high"}},
]
result = aggregate_events(events)
assert len(result) == 1, f"expected 1, got {{len(result)}}"
assert len(result[0]["source_urls"]) == 2, "urls not merged"
assert result[0]["confidence"] == "高", "2 sources should be high"
assert result[0]["target_id"] == "li_i6"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_target_aggregation_different_targets():
    code = rf"""
import sys, json
sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import aggregate_events

events = [
    {{"date":"2026-06-05","brand":"理想","model":"i6","event_type":"上市","event_status":"已确认",
      "source_title":"A","source_url":"url1","source_type":"mainstream_media","confidence":"高","evidence":"a","_has_excluded":False,
      "target_id":"li_i6","target_display_name":"理想 i6","target_group":"新势力SUV","target_priority":"high"}},
    {{"date":"2026-06-05","brand":"乐道","model":"L80","event_type":"预售","event_status":"已确认",
      "source_title":"B","source_url":"url2","source_type":"mainstream_media","confidence":"高","evidence":"b","_has_excluded":False,
      "target_id":"onvo_l80","target_display_name":"乐道 L80","target_group":"蔚来系SUV","target_priority":"high"}},
]
result = aggregate_events(events)
assert len(result) == 2, f"expected 2, got {{len(result)}}"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── markdown output ─────────────────────────────────────────────

def test_markdown_contains_target_sections():
    code = rf"""
import sys
sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import format_markdown, build_event_summary, MonitorFilters

events = [
    {{"date":"2026-06-05","brand":"理想","model":"i6","event_type":"上市","event_status":"已确认",
      "source_title":"A","source_url":"https://a.com","source_urls":["https://a.com"],
      "source_type":"mainstream_media","confidence":"中","evidence":"test",
      "target_id":"li_i6","target_display_name":"理想 i6","target_group":"新势力SUV","target_priority":"high"}},
]
summary = build_event_summary(events, "新车发布会")
filters = MonitorFilters()

wi = {{"targets_file":"ls8_competitor_watchlist.csv","watchlist_name":"LS8 竞争关注品牌-车型列表","active_target_count":10}}
hits = [{{"target_id":"li_i6","display_name":"理想 i6","group":"新势力SUV","priority":"high",
          "hit_count":1,"best_confidence":"中","latest_event":"2026-06-05 上市"}}]
misses = [{{"target_id":"zeekr_8x","display_name":"极氪 8X","group":"吉利系SUV","priority":"medium"}}]

md = format_markdown(events, summary, "2026-06-05", "2026-06-07", "新车发布会", filters, wi, hits, misses)
assert "关注车型命中概览" in md
assert "未命中关注车型" in md
assert "ls8_competitor_watchlist.csv" in md
assert "10 个" in md
assert "li_i6" in md
assert "zeekr_8x" in md
assert "0" in md  # hit_count for missed target
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_markdown_no_targets_fallback():
    """不传 watchlist 时保持 v0.3 格式"""
    code = rf"""
import sys
sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import format_markdown, build_event_summary, MonitorFilters

events = [
    {{"date":"2026-06-05","brand":"本田","model":"CR-V","event_type":"上市","event_status":"已确认",
      "source_title":"A","source_url":"https://a.com","source_urls":["https://a.com"],
      "source_type":"mainstream_media","confidence":"中","evidence":"test"}},
]
summary = build_event_summary(events, "新车发布会")
filters = MonitorFilters()
md = format_markdown(events, summary, "2026-06-05", "2026-06-07", "新车发布会", filters)
assert "关注车型命中概览" not in md
assert "未命中关注车型" not in md
assert "本田" in md
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── v0.3 compatibility ──────────────────────────────────────────

def test_no_targets_file_uses_brands_keywords():
    result = _run(["--help"])
    assert "--targets-file" in result.stdout or "--targets-file" in result.stderr
    assert "--brands" in result.stdout or "--brands" in result.stderr


# ─── v0.3 preserved tests ────────────────────────────────────────

def test_parse_csv_arg_multiple():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import parse_csv_arg
r = parse_csv_arg("智己,理想,小米")
assert r == ["智己", "理想", "小米"]
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_parse_csv_arg_empty():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import parse_csv_arg
assert parse_csv_arg("") == []
assert parse_csv_arg(None) == []
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0


def test_single_mainstream_confidence_is_medium():
    code = rf"""
import sys, json; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import aggregate_events
events = [{{"date":"2026-06-05","brand":"本田","model":"CR-V","event_type":"上市","event_status":"已确认",
     "source_title":"A","source_url":"https://a.com","source_type":"mainstream_media","confidence":"高","evidence":"t","_has_excluded":False}}]
result = aggregate_events(events)
assert len(result) == 1
assert result[0]["confidence"] == "中"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0


def test_two_sources_cross_verify_confidence_is_high():
    code = rf"""
import sys, json; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import aggregate_events
events = [
    {{"date":"2026-06-05","brand":"本田","model":"CR-V","event_type":"上市","event_status":"已确认",
      "source_title":"A","source_url":"https://a1.com","source_type":"mainstream_media","confidence":"高","evidence":"t","_has_excluded":False}},
    {{"date":"2026-06-05","brand":"本田","model":"CR-V","event_type":"上市","event_status":"已确认",
      "source_title":"B","source_url":"https://a2.com","source_type":"mainstream_media","confidence":"高","evidence":"t","_has_excluded":False}},
]
result = aggregate_events(events)
assert len(result) == 1
assert result[0]["confidence"] == "高"
assert len(result[0]["source_urls"]) == 2
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0


def test_official_source_confidence_is_high():
    code = rf"""
import sys, json; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import aggregate_events
events = [{{"date":"2026-06-05","brand":"理想","model":"L8","event_type":"发布","event_status":"已确认",
     "source_title":"A","source_url":"https://www.lixiang.com/abc","source_type":"official","confidence":"高","evidence":"t","_has_excluded":False}}]
result = aggregate_events(events)
assert len(result) == 1
assert result[0]["confidence"] == "高"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0


def test_help():
    result = _run(["--help"])
    assert result.returncode == 0
    assert "用法" in result.stdout or "usage" in result.stdout or "usage" in result.stderr


def test_missing_api_key():
    env_no_key = {k: v for k, v in os.environ.items()
                  if k not in ("TAVILY_API_KEY", "FIRECRAWL_API_KEY")}
    result = _run(["--start", "2026-06-05", "--end", "2026-06-07"], env_override=env_no_key)
    assert result.returncode != 0 or "ERROR" in result.stdout or "缺少" in result.stdout


def test_help_contains_required_args():
    result = _run(["--help"])
    for arg in ("--start", "--end", "--targets-file", "--brands", "--event-types", "--source-types"):
        assert arg in result.stdout or arg in result.stderr


# ─── v0.4.1: Firecrawl failure tolerance ──────────────────────────

def test_scrape_url_with_retry_failure_does_not_raise():
    """模拟 scrape 失败，不抛出异常到主流程。"""
    code = rf"""
import sys
sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import scrape_url_with_retry

class MockApp:
    def scrape_url(self, url, **kw):
        raise RuntimeError("mock tunnel failed")

result = scrape_url_with_retry(MockApp(), "https://example.com/fail", max_retries=1)
assert result["success"] is False
assert "error" in result
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_scrape_url_retry_succeeds_on_second_try():
    """模拟第一次失败、第二次成功，最终记成功。"""
    code = rf"""
import sys
sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import scrape_url_with_retry

class _Resp:
    markdown = "hello"
    metadata = type("M", (), {{"title": "ok", "ogTitle": ""}})()

class MockApp:
    def __init__(self):
        self.call_count = 0
    def scrape_url(self, url, **kw):
        self.call_count += 1
        if self.call_count == 1:
            raise RuntimeError("first fail")
        return _Resp()

result = scrape_url_with_retry(MockApp(), "https://example.com/retry", max_retries=2)
assert result["success"] is True
assert result["markdown"] == "hello"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_diagnostics_in_markdown():
    """markdown 输出应包含监测质量诊断和计数器。"""
    code = rf"""
import sys
sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import format_markdown, build_event_summary, MonitorFilters, CrawlDiagnostics

events = []
summary = build_event_summary(events, "新车发布会")
filters = MonitorFilters()
diag = CrawlDiagnostics(generated_query_count=17, dedup_url_count=701,
                         planned_crawl_count=50, crawled_page_count=45, failed_crawl_count=5,
                         failed_urls=[{{"url":"https://a.com","error":"timeout"}}])

md = format_markdown(events, summary, "2026-06-05", "2026-06-07", "新车发布会",
                      filters, diagnostics=diag)
assert "监测质量诊断" in md
assert "generated_query_count" in md
assert "failed_crawl_count" in md
assert "5" in md
assert "需复核抓取覆盖度" in md
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_chejiahao_classified_as_social_media():
    """chejiahao.autohome.com.cn 应分类为 social_media。"""
    code = rf"""
import sys
sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import classify_domain, map_source_type

raw = classify_domain("https://chejiahao.autohome.com.cn/info/123")
assert raw == "social", f"got {{raw}}"
st = map_source_type(raw)
assert st == "social_media", f"got {{st}}"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_autohome_main_station_is_mainstream():
    """autohome.com.cn 主站应保持 mainstream_media。"""
    code = rf"""
import sys
sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import classify_domain, map_source_type

raw = classify_domain("https://www.autohome.com.cn/news/202606/123.html")
assert raw == "mainstream", f"got {{raw}}"
st = map_source_type(raw)
assert st == "mainstream_media", f"got {{st}}"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"
