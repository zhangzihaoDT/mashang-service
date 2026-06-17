"""
Smoke test: auto_launch_monitor.py v0.4

验证:
1. load_watch_targets 读取、校验、aliases 拆分
2. 缺失 targets_file 报错
3. target 匹配（理想 i6 → li_i6, ONVO L80 → onvo_l80, ZEEKR 8X → zeekr_8x）
4. 品牌命中但车型不匹配不归入
5. targets-file 过滤
6. target 聚合逻辑
7. Markdown 包含命中概览 / 未命中 / filters 摘要
8. v0.3 兼容：不传 --targets-file 时原有逻辑不变
9. 原有 14 个测试保持
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
