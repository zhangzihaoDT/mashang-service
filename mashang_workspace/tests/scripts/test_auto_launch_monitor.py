"""
Smoke test: auto_launch_monitor.py v0.4.5

验证:
1. load_watch_targets 读取、校验、aliases 拆分
2. 缺失 targets_file 报错
3. target 匹配（品牌+车型命中才匹配，短 alias 单独不匹配）
4. 冲突检测（zeekr_8x vs 问界 M8 过滤）
5. source classification（aggregator/ugc_media/social_media/mainstream）
6. pre_crawl_skip
7. date_basis 解析
8. diagnostics 管道统计
9-10. Firecrawl 容错
11. autohome 分类
12. v0.3 兼容
13. 原有测试保持
14. v0.4.3: event_date hard filter
15. v0.4.3: brand/model conflict hard filter
16. v0.4.3: evidence relevance guard
17. v0.4.3: irrelevant keywords filter
18. v0.4.3: source_publish_date downgrade
19. v0.4.3: diagnostics final_guard 字段
20. v0.4.4: brand conflict
21. v0.4.4: model conflict
22. v0.4.4: source_publish_date 降级真实作用
23. v0.4.4: polluted snippet detection
24. v0.4.4: post_aggregate_normalize
25. v0.4.4: diagnostics 新字段 + degrade samples
26. v0.4.5: brand conflict real E2E (zeekr+沃尔沃, vw+蔚来, etc.)
27. v0.4.5: evidence-based exemption (大众+ID.ERA 9X)
28. v0.4.5: model conflict with OTHER_MODEL_PATTERN_MARKERS
29. v0.4.5: extended polluted snippet (dy_recommends, post2020, model_, etc.)
30. v0.4.5: polluted without target signal → filter
31. v0.4.5: diagnostics + final_guard interaction
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


# ─── v0.4.2: Source classification ──────────────────────────────────

def test_tags_sina_is_aggregator():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import classify_domain, map_source_type
raw = classify_domain("https://tags.sina.com.cn/culture_xinchefabu")
assert raw == "aggregator", f"got {{raw}}"
assert map_source_type(raw) == "aggregator"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_163_dy_is_ugc():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import classify_domain, map_source_type
raw = classify_domain("https://www.163.com/dy/article/abcdef.html")
assert raw == "ugc_media", f"got {{raw}}"
assert map_source_type(raw) == "ugc_media"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── v0.4.2: Strong matching ────────────────────────────────────────

def test_match_li_i6_strong():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets, match_event_to_target
targets = load_watch_targets(r"{WATCHLIST_CSV}")
event = {{"brand":"理想","model":"i6","title":"理想i6","source_title":"","evidence":"理想i6正式上市"}}
t = match_event_to_target(event, targets)
assert t is not None and t.target_id == "li_i6"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_no_match_brand_only_i6():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets, match_event_to_target
targets = load_watch_targets(r"{WATCHLIST_CSV}")
event = {{"brand":"理想","model":"L9","title":"理想L9","source_title":"","evidence":"理想L9"}}
t = match_event_to_target(event, targets)
assert t is None, f"should not match, got {{t.target_id if t else None}}"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_short_model_alias_alone_no_match():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets, match_event_to_target
targets = load_watch_targets(r"{WATCHLIST_CSV}")
event = {{"brand":"","model":"","title":"8X新车","source_title":"","evidence":"8X"}}
t = match_event_to_target(event, targets)
assert t is None, f"should not match short alias alone, got {{t.target_id if t else None}}"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_strong_alias_matches():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets, match_event_to_target
targets = load_watch_targets(r"{WATCHLIST_CSV}")
event = {{"brand":"","model":"","title":"","source_title":"","evidence":"ONVO L80开启预售"}}
t = match_event_to_target(event, targets)
assert t is not None and t.target_id == "onvo_l80", f"got {{t.target_id if t else None}}"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_m7_alone_does_not_match_aito():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets, match_event_to_target
targets = load_watch_targets(r"{WATCHLIST_CSV}")
event = {{"brand":"","model":"","title":"","source_title":"","evidence":"M7改款新车"}}
t = match_event_to_target(event, targets)
assert t is None, f"should not match short alias, got {{t.target_id if t else None}}"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── v0.4.2: Conflict detection ──────────────────────────────────────

def test_conflict_zeekr_vs_wenjie():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets, detect_target_conflict
targets = load_watch_targets(r"{WATCHLIST_CSV}")
zeekr = [t for t in targets if t.target_id == "zeekr_8x"][0]
# event brand="问界", evidence="问界M7" -> 问界M7属于aito_m7，与zeekr_8x冲突
event = {{"brand":"问界","model":"M7","source_title":"","evidence":"问界 M7"}}
conflict, reason = detect_target_conflict(event, zeekr, targets)
assert conflict, f"expected conflict, got: {{reason}}"
print("OK conflict:", reason)
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_conflict_vw_vs_volvo():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets, detect_target_conflict
targets = load_watch_targets(r"{WATCHLIST_CSV}")
vw = [t for t in targets if t.target_id == "vw_id_era_9x"][0]
# event brand="零跑", evidence="零跑D19" -> 零跑D19属于leapmotor_d19，与vw_id_era_9x冲突
event = {{"brand":"零跑","model":"D19","source_title":"","evidence":"零跑D19"}}
conflict, reason = detect_target_conflict(event, vw, targets)
assert conflict, f"expected conflict, got: {{reason}}"
print("OK conflict:", reason)
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_no_conflict_for_correct_target():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets, detect_target_conflict
targets = load_watch_targets(r"{WATCHLIST_CSV}")
li = [t for t in targets if t.target_id == "li_i6"][0]
event = {{"brand":"理想","model":"i6","source_title":"","evidence":"理想i6上市"}}
conflict, reason = detect_target_conflict(event, li, targets)
assert not conflict, f"unexpected conflict: {{reason}}"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── v0.4.2: Date basis ─────────────────────────────────────────────

def test_date_basis_event_date():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import try_parse_event_date
ed, basis, conf = try_parse_event_date("理想i6于6月10日开启预售")
assert ed == "2026-06-10", ("bad ed: " + str(ed))
assert basis == "event_date"
assert conf in ("high", "medium")
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_date_basis_fallback():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import try_parse_event_date
ed, basis, conf = try_parse_event_date("理想旗下新款车型发布")
assert ed == "", ("bad ed: " + str(ed))
assert basis == ""
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── v0.4.2: Pre-crawl skip ──────────────────────────────────────────

def test_pre_crawl_skip_tags_sina():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import should_skip_url_before_crawl
skip, reason = should_skip_url_before_crawl("https://tags.sina.com.cn/culture_xinchefabu",
                                             ["official","mainstream_media","industry_media"])
assert skip, "should skip tags.sina.com.cn"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_pre_crawl_keep_mainstream():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import should_skip_url_before_crawl
skip, reason = should_skip_url_before_crawl("https://www.autohome.com.cn/news/123.html",
                                             ["official","mainstream_media","industry_media"])
assert not skip, f"should not skip, got: {{reason}}"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── v0.4.2: Diagnostics pipeline ───────────────────────────────────

def test_diagnostics_contains_pipeline_counts():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import format_markdown, build_event_summary, MonitorFilters, CrawlDiagnostics

events = [{{"date":"2026-06-05","brand":"理想","model":"i6","event_type":"上市","event_status":"已确认",
           "source_title":"A","source_url":"https://a.com","source_urls":["https://a.com"],
           "source_type":"mainstream_media","confidence":"中","evidence":"test"}}]
summary = build_event_summary(events, "新车发布会")
diag = CrawlDiagnostics(raw_extracted_event_count=50, source_filtered_count=10,
                         target_matched_event_count=8, conflict_filtered_count=2, final_event_count=6)
md = format_markdown(events, summary, "2026-06-05", "2026-06-07", "新车发布会", diagnostics=diag)
assert "raw_extracted_event_count" in md
assert "source_filtered_count" in md
assert "target_matched_event_count" in md
assert "conflict_filtered_count" in md
assert "final_event_count" in md
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── v0.4.3: event_date hard filter ─────────────────────────────────────

def test_event_date_out_of_range_filtered():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import apply_final_event_guard, CrawlDiagnostics, WatchTarget
diag = CrawlDiagnostics()
events = [
    {{"event_date":"2026-05-20","date_basis":"event_date","brand":"小鹏","model":"GX","source_title":"","evidence":"",
      "source_publish_date":"2026-05-20","target_id":"xpeng_gx","event_type":"上市","event_status":"已确认","confidence":"高"}},
    {{"event_date":"2026-06-10","date_basis":"event_date","brand":"小鹏","model":"GX","source_title":"","evidence":"",
      "source_publish_date":"2026-06-10","target_id":"xpeng_gx","event_type":"上市","event_status":"已确认","confidence":"高"}},
    {{"event_date":"","date_basis":"source_publish_date","brand":"理想","model":"i6","source_title":"","evidence":"理想i6发布",
      "source_publish_date":"2026-06-10","target_id":"li_i6","event_type":"发布","event_status":"已确认","confidence":"高"}},
]
guarded = apply_final_event_guard(events, None, start_date="2026-06-01", end_date="2026-06-17", diagnostics=diag)
assert len(guarded) == 2, f"expected 2 kept, got {{len(guarded)}}"
assert diag.final_guard_filtered_count == 1, f"expected 1 filtered, got {{diag.final_guard_filtered_count}}"
assert diag.out_of_range_event_count == 1, f"expected 1 out_of_range, got {{diag.out_of_range_event_count}}"
filtered_ids = [e.get("target_id","") for e in guarded]
assert "xpeng_gx" in filtered_ids
print("OK filtered_count=", diag.final_guard_filtered_count)
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_event_date_in_range_kept():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import apply_final_event_guard, CrawlDiagnostics
diag = CrawlDiagnostics()
events = [
    {{"event_date":"2026-06-10","date_basis":"event_date","brand":"","model":"","source_title":"","evidence":"",
      "source_publish_date":"","target_id":"test"}},
]
guarded = apply_final_event_guard(events, None, start_date="2026-06-01", end_date="2026-06-17", diagnostics=diag)
assert len(guarded) == 1
assert diag.final_guard_filtered_count == 0
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_source_publish_date_only_downgraded():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import apply_final_event_guard, CrawlDiagnostics
diag = CrawlDiagnostics()
events = [
    {{"event_date":"","date_basis":"source_publish_date","source_publish_date":"2026-06-10",
      "brand":"","model":"","source_title":"","evidence":"相关资讯 乐道L80到店",
      "target_id":"onvo_l80","event_type":"上市","event_status":"已确认","confidence":"高",
      "date_confidence":"high"}},
]
guarded = apply_final_event_guard(events, None, start_date="2026-06-01", end_date="2026-06-17", diagnostics=diag)
assert len(guarded) == 1
assert guarded[0]["event_status"] == "待确认", f"expected 待确认, got {{guarded[0]['event_status']}}"
assert guarded[0]["date_confidence"] == "low"
assert diag.date_basis_downgraded_count == 1
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_source_publish_date_with_confirmed_verb_keeps_status():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import apply_final_event_guard, CrawlDiagnostics
diag = CrawlDiagnostics()
events = [
    {{"event_date":"","date_basis":"source_publish_date","source_publish_date":"2026-06-10",
      "brand":"乐道","model":"L80","source_title":"","evidence":"乐道L80正式上市",
      "target_id":"onvo_l80","event_type":"上市","event_status":"已确认","confidence":"高",
      "date_confidence":"high"}},
]
guarded = apply_final_event_guard(events, None, start_date="2026-06-01", end_date="2026-06-17", diagnostics=diag)
assert len(guarded) == 1
assert guarded[0]["event_status"] == "已确认", f"expected 已确认, got {{guarded[0]['event_status']}}"
assert guarded[0]["date_confidence"] == "low"
assert diag.date_basis_downgraded_count == 1
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── v0.4.3: brand/model conflict hard filter ──────────────────────────

def test_brand_model_conflict_zeekr_volvo():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets, is_brand_model_conflict
targets = load_watch_targets(r"{WATCHLIST_CSV}")
zeekr = [t for t in targets if t.target_id == "zeekr_8x"][0]
event = {{"brand":"沃尔沃","model":"EX90","source_title":"沃尔沃EX90上市","evidence":"沃尔沃EX90"}}
conflict, reason = is_brand_model_conflict(event, zeekr, targets)
assert conflict, f"expected conflict, got: {{reason}}"
print("OK conflict:", reason)
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_brand_model_conflict_zeekr_byd():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets, is_brand_model_conflict
targets = load_watch_targets(r"{WATCHLIST_CSV}")
zeekr = [t for t in targets if t.target_id == "zeekr_8x"][0]
event = {{"brand":"比亚迪","model":"宋U","source_title":"比亚迪宋U上市","evidence":"比亚迪宋U"}}
conflict, reason = is_brand_model_conflict(event, zeekr, targets)
assert conflict, f"expected conflict, got: {{reason}}"
print("OK conflict:", reason)
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_brand_model_conflict_zeekr_arcturus():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets, is_brand_model_conflict
targets = load_watch_targets(r"{WATCHLIST_CSV}")
zeekr = [t for t in targets if t.target_id == "zeekr_8x"][0]
event = {{"brand":"极狐","model":"贝塔T1","source_title":"极狐贝塔T1上市","evidence":"极狐贝塔T1"}}
conflict, reason = is_brand_model_conflict(event, zeekr, targets)
assert conflict, f"expected conflict, got: {{reason}}"
print("OK conflict:", reason)
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_brand_model_conflict_avatr_deepal():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets, is_brand_model_conflict
targets = load_watch_targets(r"{WATCHLIST_CSV}")
avatr = [t for t in targets if t.target_id == "avatr_06"][0]
event = {{"brand":"深蓝","model":"S07","source_title":"深蓝S07上市","evidence":"深蓝S07"}}
conflict, reason = is_brand_model_conflict(event, avatr, targets)
assert conflict, f"expected conflict, got: {{reason}}"
print("OK conflict:", reason)
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_brand_model_conflict_onvo_arcturus():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets, is_brand_model_conflict
targets = load_watch_targets(r"{WATCHLIST_CSV}")
onvo = [t for t in targets if t.target_id == "onvo_l80"][0]
event = {{"brand":"极狐","model":"贝塔T1","source_title":"极狐贝塔T1上市","evidence":"极狐贝塔T1"}}
conflict, reason = is_brand_model_conflict(event, onvo, targets)
assert conflict, f"expected conflict, got: {{reason}}"
print("OK conflict:", reason)
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_brand_model_no_conflict_empty_brand():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets, is_brand_model_conflict
targets = load_watch_targets(r"{WATCHLIST_CSV}")
onvo = [t for t in targets if t.target_id == "onvo_l80"][0]
event = {{"brand":"","model":"","source_title":"","evidence":"乐道L80正式上市"}}
conflict, reason = is_brand_model_conflict(event, onvo, targets)
assert not conflict, f"expected no conflict, got: {{reason}}"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── v0.4.3: evidence relevance guard ──────────────────────────────────

def test_evidence_relevant_onvo_l80_strong():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets, has_final_target_evidence
targets = load_watch_targets(r"{WATCHLIST_CSV}")
onvo = [t for t in targets if t.target_id == "onvo_l80"][0]
event = {{"evidence":"乐道L80正式上市","source_title":"","brand":"","model":""}}
assert has_final_target_evidence(event, onvo), "乐道L80 should have evidence"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_evidence_irrelevant_m7_alone():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets, has_final_target_evidence
targets = load_watch_targets(r"{WATCHLIST_CSV}")
aito = [t for t in targets if t.target_id == "aito_m7"][0]
event = {{"evidence":"M7上市","source_title":"","brand":"","model":""}}
assert not has_final_target_evidence(event, aito), "M7 alone should not have evidence"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_evidence_irrelevant_8x_alone():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets, has_final_target_evidence
targets = load_watch_targets(r"{WATCHLIST_CSV}")
zeekr = [t for t in targets if t.target_id == "zeekr_8x"][0]
event = {{"evidence":"8X上市","source_title":"","brand":"","model":""}}
assert not has_final_target_evidence(event, zeekr), "8X alone should not have evidence"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── v0.4.3: irrelevant keywords filter via guard ─────────────────────

def test_irrelevant_keywords_worldcup_filtered():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import apply_final_event_guard, CrawlDiagnostics
diag = CrawlDiagnostics()
events = [
    {{"event_date":"2026-06-10","date_basis":"event_date","brand":"","model":"",
      "source_title":"世界杯报道","evidence":"世界杯 德国队胜利","source_publish_date":"2026-06-10",
      "target_id":"test","event_type":"其他"}},
]
guarded = apply_final_event_guard(events, None, start_date="2026-06-01", end_date="2026-06-17", diagnostics=diag)
assert len(guarded) == 0, f"expected 0, got {{len(guarded)}}"
assert diag.final_guard_filtered_count >= 1
assert diag.evidence_irrelevant_count >= 1
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── v0.4.3: diagnostics final_guard fields ───────────────────────────

def test_diagnostics_final_guard_fields():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import format_markdown, build_event_summary, MonitorFilters, CrawlDiagnostics

events = [{{"date":"2026-06-05","brand":"理想","model":"i6","event_type":"上市","event_status":"已确认",
           "source_title":"A","source_url":"https://a.com","source_urls":["https://a.com"],
           "source_type":"mainstream_media","confidence":"中","evidence":"test"}}]
summary = build_event_summary(events, "新车发布会")
diag = CrawlDiagnostics(final_guard_filtered_count=3, out_of_range_event_count=1,
                         brand_model_conflict_count=1, evidence_irrelevant_count=1,
                         date_basis_downgraded_count=1, final_event_count=1)
md = format_markdown(events, summary, "2026-06-05", "2026-06-07", "新车发布会", diagnostics=diag)
assert "final_guard_filtered_count" in md
assert "out_of_range_event_count" in md
assert "brand_model_conflict_count" in md
assert "evidence_irrelevant_count" in md
assert "date_basis_downgraded_count" in md
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_diagnostics_final_guard_samples():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import format_markdown, build_event_summary, MonitorFilters, CrawlDiagnostics

events = [{{"date":"2026-06-05","brand":"理想","model":"i6","event_type":"上市","event_status":"已确认",
           "source_title":"A","source_url":"https://a.com","source_urls":["https://a.com"],
           "source_type":"mainstream_media","confidence":"中","evidence":"test"}}]
summary = build_event_summary(events, "新车发布会")
diag = CrawlDiagnostics(final_guard_filtered_count=1,
                         final_guard_filtered_events=[{{"target_id":"zeekr_8x","brand":"沃尔沃","model":"EX90",
                                                         "event_date":"","source_publish_date":"2026-06-10",
                                                         "reason":"brand_model_conflict",
                                                         "evidence_snippet":"沃尔沃EX90上市"}}])
md = format_markdown(events, summary, "2026-06-05", "2026-06-07", "新车发布会", diagnostics=diag)
assert "Final Guard 过滤样例" in md
assert "zeekr_8x" in md
assert "沃尔沃" in md
assert "brand_model_conflict" in md
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── v0.4.4: brand conflict (vw_id_era_9x + 蔚来 → filtered) ───────────

def test_brand_conflict_vw_nio():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets, is_brand_model_conflict
targets = load_watch_targets(r"{WATCHLIST_CSV}")
vw = [t for t in targets if t.target_id == "vw_id_era_9x"][0]
event = {{"brand":"蔚来","model":"","source_title":"","evidence":"蔚来新车"}}
conflict, reason = is_brand_model_conflict(event, vw, targets)
assert conflict, f"expected conflict, got: {{reason}}"
print("OK conflict:", reason)
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_brand_conflict_onvo_arcturus_v2():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets, is_brand_model_conflict
targets = load_watch_targets(r"{WATCHLIST_CSV}")
onvo = [t for t in targets if t.target_id == "onvo_l80"][0]
event = {{"brand":"极狐","model":"","source_title":"","evidence":"极狐新车"}}
conflict, reason = is_brand_model_conflict(event, onvo, targets)
assert conflict, f"expected conflict, got: {{reason}}"
print("OK conflict:", reason)
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_brand_no_conflict_vw_with_evidence():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets, is_brand_model_conflict
targets = load_watch_targets(r"{WATCHLIST_CSV}")
vw = [t for t in targets if t.target_id == "vw_id_era_9x"][0]
event = {{"brand":"大众","model":"","source_title":"","evidence":"大众ID. ERA 9X正式上市"}}
conflict, reason = is_brand_model_conflict(event, vw, targets)
assert not conflict, f"expected no conflict, got: {{reason}}"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── v0.4.4: model conflict ──────────────────────────────────────────

def test_model_conflict_vw_generic():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import load_watch_targets, is_brand_model_conflict
targets = load_watch_targets(r"{WATCHLIST_CSV}")
vw = [t for t in targets if t.target_id == "vw_id_era_9x"][0]
event = {{"brand":"","model":"插混中型SUV上市","source_title":"","evidence":"插混中型SUV上市"}}
conflict, reason = is_brand_model_conflict(event, vw, targets)
assert conflict, f"expected conflict, got: {{reason}}"
print("OK conflict:", reason)
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── v0.4.4: polluted snippet detection ──────────────────────────────

def test_polluted_snippet_related_info():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import is_polluted_snippet
polluted, marker = is_polluted_snippet({{"evidence":"相关资讯 乐道L80到店","source_title":""}})
assert polluted, "相关资讯 should be polluted"
assert marker == "相关资讯"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_polluted_snippet_recommended():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import is_polluted_snippet
polluted, marker = is_polluted_snippet({{"evidence":"推荐阅读 预售价39.98万","source_title":""}})
assert polluted, "推荐阅读 should be polluted"
print("OK marker:", marker)
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_polluted_snippet_price_quote():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import is_polluted_snippet
polluted, marker = is_polluted_snippet({{"evidence":"车型报价 对比评测 主流SUV","source_title":""}})
assert polluted, "车型报价/对比评测 should be polluted"
print("OK marker:", marker)
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_polluted_snippet_clean():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import is_polluted_snippet
polluted, marker = is_polluted_snippet({{"evidence":"乐道L80正式上市，售价xx万元","source_title":""}})
assert not polluted, "'售价' alone should not trigger pollution"
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── v0.4.4: source_publish_date downgrade effects ─────────────────────

def test_spd_downgrade_affects_status():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import apply_final_event_guard, CrawlDiagnostics
diag = CrawlDiagnostics()
events = [
    {{"event_date":"","date_basis":"source_publish_date","source_publish_date":"2026-06-10",
      "brand":"","model":"","source_title":"推荐阅读","evidence":"相关资讯 乐道L80到店",
      "target_id":"onvo_l80","event_type":"上市","event_status":"已确认","confidence":"高","date_confidence":"high"}},
]
guarded = apply_final_event_guard(events, None, start_date="2026-06-01", end_date="2026-06-17", diagnostics=diag)
assert len(guarded) == 1
assert guarded[0]["event_status"] == "待确认", f"expected 待确认, got {{guarded[0]['event_status']}}"
assert guarded[0]["date_confidence"] == "low"
assert diag.status_downgraded_count >= 1
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── v0.4.4: post_aggregate_normalize ─────────────────────────────────

def test_post_aggregate_spd_max_medium():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import post_aggregate_normalize, CrawlDiagnostics, aggregate_events
diag = CrawlDiagnostics()
raw = [
    {{"date":"2026-06-10","event_date":"","source_publish_date":"2026-06-10","date_basis":"source_publish_date","date_confidence":"low",
      "brand":"乐道","model":"L80","event_type":"上市","event_status":"已确认","confidence":"高",
      "source_title":"乐道L80上市","source_url":"https://a.com","source_type":"mainstream_media","evidence":"乐道L80正式上市",
      "target_id":"onvo_l80","target_display_name":"乐道 L80","target_group":"","target_priority":"",
      "_has_excluded":False}},
    {{"date":"2026-06-10","event_date":"","source_publish_date":"2026-06-10","date_basis":"source_publish_date","date_confidence":"low",
      "brand":"乐道","model":"L80","event_type":"上市","event_status":"已确认","confidence":"高",
      "source_title":"乐道L80上市","source_url":"https://b.com","source_type":"mainstream_media","evidence":"乐道L80正式上市",
      "target_id":"onvo_l80","target_display_name":"乐道 L80","target_group":"","target_priority":"",
      "_has_excluded":False}},
]
agg = aggregate_events(raw)
assert agg[0]["confidence"] == "高", f"agg says {{agg[0]['confidence']}} (2 mainstream URLs should give 高)"
normalized = post_aggregate_normalize(agg, diagnostics=diag)
assert normalized[0]["confidence"] == "中", f"expected 中, got {{normalized[0]['confidence']}}"
assert diag.confidence_downgraded_count >= 1
print("OK confidence:", normalized[0]["confidence"])
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_post_aggregate_polluted_max_low():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import post_aggregate_normalize, CrawlDiagnostics, aggregate_events
diag = CrawlDiagnostics()
raw = [
    {{"date":"2026-06-10","event_date":"2026-06-10","source_publish_date":"2026-06-10","date_basis":"event_date","date_confidence":"high",
      "brand":"乐道","model":"L80","event_type":"上市","event_status":"已确认","confidence":"中",
      "source_title":"相关资讯 乐道L80","source_url":"https://a.com","source_type":"mainstream_media","evidence":"相关资讯 乐道L80到店",
      "_polluted":True,"_polluted_marker":"相关资讯",
      "target_id":"onvo_l80","target_display_name":"乐道 L80","target_group":"","target_priority":"",
      "_has_excluded":False}},
]
agg = aggregate_events(raw)
normalized = post_aggregate_normalize(agg, diagnostics=diag)
assert normalized[0]["confidence"] == "低", f"expected 低, got {{normalized[0]['confidence']}}"
assert normalized[0]["event_status"] == "待确认"
print("OK confidence:", normalized[0]["confidence"], "status:", normalized[0]["event_status"])
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_post_aggregate_official_keeps_high():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import post_aggregate_normalize, CrawlDiagnostics, aggregate_events
diag = CrawlDiagnostics()
raw = [
    {{"date":"2026-06-10","event_date":"2026-06-10","source_publish_date":"2026-06-10","date_basis":"event_date","date_confidence":"high",
      "brand":"乐道","model":"L80","event_type":"上市","event_status":"已确认","confidence":"高",
      "source_title":"乐道L80上市","source_url":"https://www.onvo.com/news","source_type":"official","evidence":"乐道L80正式上市",
      "target_id":"onvo_l80","target_display_name":"乐道 L80","target_group":"","target_priority":"",
      "_has_excluded":False}},
]
agg = aggregate_events(raw)
assert agg[0]["confidence"] == "高"
normalized = post_aggregate_normalize(agg, diagnostics=diag)
assert normalized[0]["confidence"] == "高", f"expected 高, got {{normalized[0]['confidence']}}"
print("OK confidence:", normalized[0]["confidence"])
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── v0.4.4: diagnostics new fields + degrade samples ─────────────────

def test_diagnostics_v044_fields():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import format_markdown, build_event_summary, MonitorFilters, CrawlDiagnostics

events = [{{"date":"2026-06-05","brand":"理想","model":"i6","event_type":"上市","event_status":"已确认",
           "source_title":"A","source_url":"https://a.com","source_urls":["https://a.com"],
           "source_type":"mainstream_media","confidence":"中","evidence":"test"}}]
summary = build_event_summary(events, "新车发布会")
diag = CrawlDiagnostics(polluted_snippet_count=3, confidence_downgraded_count=2,
                         status_downgraded_count=1, final_event_count=1)
md = format_markdown(events, summary, "2026-06-05", "2026-06-07", "新车发布会", diagnostics=diag)
assert "polluted_snippet_count" in md
assert "confidence_downgraded_count" in md
assert "status_downgraded_count" in md
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_diagnostics_degrade_samples():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import format_markdown, build_event_summary, MonitorFilters, CrawlDiagnostics

events = [{{"date":"2026-06-05","brand":"理想","model":"i6","event_type":"上市","event_status":"已确认",
           "source_title":"A","source_url":"https://a.com","source_urls":["https://a.com"],
           "source_type":"mainstream_media","confidence":"中","evidence":"test"}}]
summary = build_event_summary(events, "新车发布会")
diag = CrawlDiagnostics(degrade_samples=[{{"target_id":"onvo_l80","reason":"date_basis_source_publish_date",
                                            "before_status":"已确认","after_status":"已确认",
                                            "before_confidence":"高","after_confidence":"中",
                                            "evidence_snippet":"乐道L80正式上市"}}])
md = format_markdown(events, summary, "2026-06-05", "2026-06-07", "新车发布会", diagnostics=diag)
assert "Final Guard 降级样例" in md
assert "date_basis_source_publish_date" in md
assert "高" in md
assert "中" in md
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── v0.4.5: brand conflict real E2E cases ───────────────────────────

def test_brand_conflict_zeekr_volvo_e2e():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import apply_final_event_guard, CrawlDiagnostics, load_watch_targets
targets = load_watch_targets(r"{WATCHLIST_CSV}")
diag = CrawlDiagnostics()
events = [
    {{"target_id":"zeekr_8x","target_display_name":"极氪 8X",
      "brand":"沃尔沃","model":"EX90",
      "evidence":"沃尔沃EX90/ES90","source_title":"与BBA高性能旗舰直接竞争，极氪8X定档4月17日",
      "source_url":"https://a.com","event_date":"2026-06-10","date_basis":"event_date",
      "source_publish_date":"","event_type":"上市","event_status":"已确认","confidence":"中"}},
]
guarded = apply_final_event_guard(events, targets, start_date="2026-06-01", end_date="2026-06-17", diagnostics=diag)
assert len(guarded) == 0, f"expected filtered, got {{len(guarded)}}"
assert diag.brand_model_conflict_count >= 1
assert diag.final_guard_filtered_count >= 1
print("OK brand_model_conflict_count=", diag.brand_model_conflict_count)
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_brand_conflict_vw_nio_e2e():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import apply_final_event_guard, CrawlDiagnostics, load_watch_targets
targets = load_watch_targets(r"{WATCHLIST_CSV}")
diag = CrawlDiagnostics()
events = [
    {{"target_id":"vw_id_era_9x","target_display_name":"大众 ID. ERA 9X",
      "brand":"蔚来","model":"系新爆款",
      "evidence":"蔚来系新爆款？乐道L60上市","source_title":"蔚来系新爆款",
      "source_url":"https://a.com","event_date":"","date_basis":"source_publish_date",
      "source_publish_date":"2026-06-10","event_type":"上市","event_status":"已确认","confidence":"中"}},
]
guarded = apply_final_event_guard(events, targets, start_date="2026-06-01", end_date="2026-06-17", diagnostics=diag)
assert len(guarded) == 0, f"expected filtered, got {{len(guarded)}}"
assert diag.brand_model_conflict_count >= 1
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_brand_conflict_zeekr_byd_e2e():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import apply_final_event_guard, CrawlDiagnostics, load_watch_targets
targets = load_watch_targets(r"{WATCHLIST_CSV}")
diag = CrawlDiagnostics()
events = [
    {{"target_id":"zeekr_8x","target_display_name":"极氪 8X",
      "brand":"比亚迪","model":"宋U",
      "evidence":"比亚迪宋U上市","source_title":"比亚迪宋U",
      "source_url":"https://a.com","event_date":"2026-06-10","date_basis":"event_date",
      "source_publish_date":"","event_type":"上市","event_status":"已确认","confidence":"中"}},
]
guarded = apply_final_event_guard(events, targets, start_date="2026-06-01", end_date="2026-06-17", diagnostics=diag)
assert len(guarded) == 0
assert diag.brand_model_conflict_count >= 1
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── v0.4.5: evidence-based exemption ─────────────────────────────────

def test_brand_exemption_volkswagen_id_era():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import apply_final_event_guard, CrawlDiagnostics, load_watch_targets
targets = load_watch_targets(r"{WATCHLIST_CSV}")
diag = CrawlDiagnostics()
events = [
    {{"target_id":"vw_id_era_9x","target_display_name":"大众 ID. ERA 9X",
      "brand":"大众","model":"ID. ERA 9X",
      "evidence":"大众 ID. ERA 9X 正式上市","source_title":"",
      "source_url":"https://a.com","event_date":"","date_basis":"source_publish_date",
      "source_publish_date":"2026-06-10","event_type":"上市","event_status":"已确认","confidence":"高"}},
]
guarded = apply_final_event_guard(events, targets, start_date="2026-06-01", end_date="2026-06-17", diagnostics=diag)
assert len(guarded) == 1, f"expected kept, got {{len(guarded)}}"
assert diag.brand_model_conflict_count == 0
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_brand_exemption_nio_onvo_evidence():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import apply_final_event_guard, CrawlDiagnostics, load_watch_targets
targets = load_watch_targets(r"{WATCHLIST_CSV}")
diag = CrawlDiagnostics()
events = [
    {{"target_id":"onvo_l80","target_display_name":"乐道 L80",
      "brand":"蔚来","model":"",
      "evidence":"乐道L80正式上市","source_title":"",
      "source_url":"https://a.com","event_date":"","date_basis":"source_publish_date",
      "source_publish_date":"2026-06-10","event_type":"上市","event_status":"已确认","confidence":"高"}},
]
guarded = apply_final_event_guard(events, targets, start_date="2026-06-01", end_date="2026-06-17", diagnostics=diag)
assert len(guarded) == 1, f"expected kept, got {{len(guarded)}}"
assert diag.brand_model_conflict_count == 0
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── v0.4.5: extended polluted snippet ───────────────────────────────

def test_polluted_snippet_dy_recommends():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import is_polluted_snippet
p, m = is_polluted_snippet({{"evidence":"st2020_dy_recommends","source_title":"","title":"","source_url":""}})
assert p, "dy_recommends should be polluted"
print("OK marker:", m)
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_polluted_snippet_post2020():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import is_polluted_snippet
p, m = is_polluted_snippet({{"evidence":"post2020_dy_recommends","source_title":"","title":"","source_url":""}})
assert p, "post2020 should be polluted"
print("OK marker:", m)
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_polluted_snippet_markdown_image():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import is_polluted_snippet
p, m = is_polluted_snippet({{"evidence":"[![蔚来系新爆款","source_title":"","title":"","source_url":""}})
assert p, "[![ should be polluted"
print("OK marker:", m)
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_polluted_snippet_guide_test():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import is_polluted_snippet
p, m = is_polluted_snippet({{"evidence":"全部新车资讯导购试驾测评","source_title":"","title":"","source_url":""}})
assert p, "导购/试驾/测评 should be polluted"
print("OK marker:", m)
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_polluted_snippet_model_page():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import is_polluted_snippet
p, m = is_polluted_snippet({{"evidence":"","source_title":"","title":"",
    "source_url":"https://db.m.auto.sohu.com/model_7811/news"}})
assert p, "model_ page should be polluted"
print("OK marker:", m)
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── v0.4.5: polluted without target signal → filter ────────────────

def test_polluted_without_target_signal_filtered():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import apply_final_event_guard, CrawlDiagnostics, load_watch_targets
targets = load_watch_targets(r"{WATCHLIST_CSV}")
diag = CrawlDiagnostics()
events = [
    {{"target_id":"vw_id_era_9x","target_display_name":"大众 ID. ERA 9X",
      "brand":"","model":"",
      "evidence":"post2020_dy_recommends 蔚来系新爆款 乐道L60",
      "source_title":"post2020_dy_recommends",
      "source_url":"https://a.com","event_date":"","date_basis":"source_publish_date",
      "source_publish_date":"2026-06-10","event_type":"上市","event_status":"已确认","confidence":"高"}},
]
guarded = apply_final_event_guard(events, targets, start_date="2026-06-01", end_date="2026-06-17", diagnostics=diag)
assert len(guarded) == 0, f"expected filtered, got {{len(guarded)}}"
assert diag.final_guard_filtered_count >= 1
assert diag.polluted_snippet_count >= 1
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_polluted_with_target_signal_kept():
    code = rf"""
import sys; sys.path.insert(0, r"{_SCRIPT_DIR}")
from auto_launch_monitor import apply_final_event_guard, CrawlDiagnostics, load_watch_targets
targets = load_watch_targets(r"{WATCHLIST_CSV}")
diag = CrawlDiagnostics()
events = [
    {{"target_id":"vw_id_era_9x","target_display_name":"大众 ID. ERA 9X",
      "brand":"大众","model":"",
      "evidence":"相关资讯 大众ID. ERA 9X正式上市",
      "source_title":"相关资讯",
      "source_url":"https://a.com","event_date":"","date_basis":"source_publish_date",
      "source_publish_date":"2026-06-10","event_type":"上市","event_status":"已确认","confidence":"高"}},
]
guarded = apply_final_event_guard(events, targets, start_date="2026-06-01", end_date="2026-06-17", diagnostics=diag)
assert len(guarded) == 1, f"expected kept, got {{len(guarded)}}"
assert guarded[0].get("_polluted") == True
assert diag.polluted_snippet_count >= 1
assert diag.final_guard_filtered_count == 0
print("OK")
"""
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"
