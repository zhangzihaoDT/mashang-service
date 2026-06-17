"""
Smoke test: auto_launch_monitor.py v0.3

验证:
1. --help 正常输出
2. 无 API Key 时给出清晰错误提示
3. CLI 参数覆盖
4. parse_csv_arg 基础行为
5. 品牌过滤
6. 事件类型过滤
7. 来源类型过滤
8. 排除关键词降级
9. 官方来源为高、2+ 交叉验证为高、单一主流为中
10. markdown 包含 source_url / evidence / filters 摘要
"""

import json
import os
import subprocess
import sys
from pathlib import Path

_WS_DIR = Path(__file__).resolve().parents[2]
SCRIPT = _WS_DIR / "research_scripts" / "auto_launch_monitor.py"
_SCRIPT_DIR = _WS_DIR / "research_scripts"


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


# ─── parse_csv_arg ─────────────────────────────────────────────────

def test_parse_csv_arg_multiple():
    code = r"""
import sys
sys.path.insert(0, r"SD")
from auto_launch_monitor import parse_csv_arg
r = parse_csv_arg("智己,理想,小米")
assert r == ["智己", "理想", "小米"], f"got {r}"
print("OK")
""".replace("SD", str(_SCRIPT_DIR))
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_parse_csv_arg_empty():
    code = r"""
import sys
sys.path.insert(0, r"SD")
from auto_launch_monitor import parse_csv_arg
assert parse_csv_arg("") == []
assert parse_csv_arg(None) == []
assert parse_csv_arg("  ") == []
print("OK")
""".replace("SD", str(_SCRIPT_DIR))
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── Brand filtering ───────────────────────────────────────────────

def test_brand_filter():
    code = r"""
import sys, json
sys.path.insert(0, r"SD")
from auto_launch_monitor import apply_event_filters, MonitorFilters

events = [
    {"date":"2026-06-05","brand":"智己","model":"LS6","event_type":"上市","source_type":"mainstream_media"},
    {"date":"2026-06-05","brand":"理想","model":"L8","event_type":"预售","source_type":"mainstream_media"},
    {"date":"2026-06-05","brand":"蔚来","model":"ES8","event_type":"上市","source_type":"mainstream_media"},
]
filters = MonitorFilters(brands=["智己","理想"])
result = apply_event_filters(events, filters)
brands = [e["brand"] for e in result]
assert "智己" in brands and "理想" in brands and "蔚来" not in brands, f"got {brands}"
print("OK")
""".replace("SD", str(_SCRIPT_DIR))
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── Event type filtering ──────────────────────────────────────────

def test_event_type_filter():
    code = r"""
import sys
sys.path.insert(0, r"SD")
from auto_launch_monitor import apply_event_filters, MonitorFilters

events = [
    {"date":"2026-06-05","brand":"智己","model":"LS6","event_type":"上市","source_type":"mainstream_media"},
    {"date":"2026-06-05","brand":"理想","model":"L8","event_type":"预售","source_type":"mainstream_media"},
    {"date":"2026-06-05","brand":"蔚来","model":"ES8","event_type":"媒体预热","source_type":"mainstream_media"},
]
filters = MonitorFilters(event_types=["上市","预售"])
result = apply_event_filters(events, filters)
types = [e["event_type"] for e in result]
assert "上市" in types and "预售" in types and "媒体预热" not in types, f"got {types}"
print("OK")
""".replace("SD", str(_SCRIPT_DIR))
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── Source type filtering ─────────────────────────────────────────

def test_source_type_filter():
    code = r"""
import sys
sys.path.insert(0, r"SD")
from auto_launch_monitor import apply_event_filters, MonitorFilters

events = [
    {"date":"2026-06-05","brand":"智己","model":"LS6","event_type":"上市","source_type":"official"},
    {"date":"2026-06-05","brand":"理想","model":"L8","event_type":"上市","source_type":"mainstream_media"},
    {"date":"2026-06-05","brand":"蔚来","model":"ES8","event_type":"上市","source_type":"social_media"},
]
filters = MonitorFilters(source_types=["official","mainstream_media"])
result = apply_event_filters(events, filters)
st = [e["source_type"] for e in result]
assert "official" in st and "mainstream_media" in st and "social_media" not in st, f"got {st}"
print("OK")
""".replace("SD", str(_SCRIPT_DIR))
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── Exclude keyword downgrade ─────────────────────────────────────

def test_exclude_keyword_downgrades_confidence():
    code = r"""
import sys, json
sys.path.insert(0, r"SD")
from auto_launch_monitor import extract_events_from_markdown

text = "2026年06月05日 疑似 智己LS6上市 价格猜测"
events = extract_events_from_markdown(text, "https://auto.sina.com.cn/abc", "test",
                                       start_date="2026-06-05", end_date="2026-06-07",
                                       exclude_keywords=["疑似","价格猜测"])
# Should find an event with low confidence and pending status due to exclude keywords
low_events = [e for e in events if e["confidence"] == "低" and e["event_status"] == "待确认"]
assert low_events, f"expected low/pending event, got {json.dumps(events, ensure_ascii=False)}"
print("OK")
""".replace("SD", str(_SCRIPT_DIR))
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_exclude_keyword_does_not_downgrade_official():
    code = r"""
import sys, json
sys.path.insert(0, r"SD")
from auto_launch_monitor import extract_events_from_markdown

text = "2026年06月05日 理想L8上市 疑似交付"
events = extract_events_from_markdown(text, "https://www.lixiang.com/news/123", "test",
                                       start_date="2026-06-05", end_date="2026-06-07",
                                       exclude_keywords=["疑似"])
# Official source should not be downgraded
high = [e for e in events if e["confidence"] == "高"]
assert high, f"expected high confidence for official source, got {json.dumps(events, ensure_ascii=False)}"
print("OK")
""".replace("SD", str(_SCRIPT_DIR))
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── Confidence rules (kept from v0.2) ────────────────────────────

def test_single_mainstream_confidence_is_medium():
    code = r"""
import sys, json
sys.path.insert(0, r"SD")
from auto_launch_monitor import aggregate_events

events = [
    {"date":"2026-06-05","brand":"本田","model":"CR-V","event_type":"上市","event_status":"已确认",
     "source_title":"太平洋汽车","source_url":"https://price.pcauto.com.cn/cars/6",
     "source_type":"mainstream_media","confidence":"高","evidence":"test","_has_excluded":False},
]
result = aggregate_events(events)
assert len(result) == 1
assert result[0]["confidence"] == "中", f"expected 中, got {result[0]['confidence']}"
print("OK")
""".replace("SD", str(_SCRIPT_DIR))
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_two_sources_cross_verify_confidence_is_high():
    code = r"""
import sys, json
sys.path.insert(0, r"SD")
from auto_launch_monitor import aggregate_events

events = [
    {"date":"2026-06-05","brand":"本田","model":"CR-V","event_type":"上市","event_status":"已确认",
     "source_title":"太平洋汽车","source_url":"https://price.pcauto.com.cn/cars/6",
     "source_type":"mainstream_media","confidence":"高","evidence":"test1","_has_excluded":False},
    {"date":"2026-06-05","brand":"本田","model":"CR-V","event_type":"上市","event_status":"已确认",
     "source_title":"新浪汽车","source_url":"https://auto.sina.com.cn/newcar/",
     "source_type":"mainstream_media","confidence":"高","evidence":"test2","_has_excluded":False},
]
result = aggregate_events(events)
assert len(result) == 1
assert result[0]["confidence"] == "高", f"expected 高, got {result[0]['confidence']}"
assert len(result[0]["source_urls"]) == 2
print("OK")
""".replace("SD", str(_SCRIPT_DIR))
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_official_source_confidence_is_high():
    code = r"""
import sys, json
sys.path.insert(0, r"SD")
from auto_launch_monitor import aggregate_events

events = [
    {"date":"2026-06-05","brand":"理想","model":"L8","event_type":"发布","event_status":"已确认",
     "source_title":"理想官网","source_url":"https://www.lixiang.com/news/123",
     "source_type":"official","confidence":"高","evidence":"test","_has_excluded":False},
]
result = aggregate_events(events)
assert len(result) == 1
assert result[0]["confidence"] == "高", f"expected 高, got {result[0]['confidence']}"
print("OK")
""".replace("SD", str(_SCRIPT_DIR))
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── Markdown output ──────────────────────────────────────────────

def test_markdown_contains_source_url_evidence_and_filters():
    code = r"""
import sys
sys.path.insert(0, r"SD")
from auto_launch_monitor import format_markdown, build_event_summary, MonitorFilters

events = [
    {"date":"2026-06-05","brand":"本田","model":"CR-V","event_type":"上市","event_status":"已确认",
     "source_title":"太平洋汽车","source_url":"https://price.pcauto.com.cn/cars/6",
     "source_urls":["https://price.pcauto.com.cn/cars/6"],
     "source_type":"mainstream_media","confidence":"中","evidence":"2026年06月05日上市"},
]
summary = build_event_summary(events, "新车发布会")
filters = MonitorFilters(brands=["本田"], event_types=["上市"], source_types=["mainstream_media"])
md = format_markdown(events, summary, "2026-06-05", "2026-06-07", "新车发布会", filters)

assert "汽车新车事件监测报告" in md, "title"
assert "https://price.pcauto.com.cn/cars/6" in md, "source URL"
assert "2026年06月05日上市" in md, "evidence"
assert "过滤条件" in md, "filters section"
assert "本田" in md, "brand filter"
assert "上市" in md, "event type filter"
assert "mainstream_media" in md, "source type filter"
print("OK")
""".replace("SD", str(_SCRIPT_DIR))
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── Original smoke tests ─────────────────────────────────────────

def test_help():
    result = _run(["--help"])
    assert result.returncode == 0, f"--help 失败: {result.stderr}"
    assert "用法" in result.stdout or "usage" in result.stdout or "usage" in result.stderr


def test_missing_api_key():
    env_no_key = {k: v for k, v in os.environ.items()
                  if k not in ("TAVILY_API_KEY", "FIRECRAWL_API_KEY")}
    result = _run(["--start", "2026-06-05", "--end", "2026-06-07"], env_override=env_no_key)
    assert result.returncode != 0 or "ERROR" in result.stdout or "缺少" in result.stdout
    assert ("TAVILY_API_KEY" in result.stdout or "FIRECRAWL_API_KEY" in result.stdout
            or "缺少" in result.stdout or "ERROR" in result.stdout)


def test_help_contains_required_args():
    result = _run(["--help"])
    assert "--start" in result.stdout or "--start" in result.stderr
    assert "--end" in result.stdout or "--end" in result.stderr
    assert "--brands" in result.stdout or "--brands" in result.stderr
    assert "--event-types" in result.stdout or "--event-types" in result.stderr
    assert "--source-types" in result.stdout or "--source-types" in result.stderr
    assert "--keywords" in result.stdout or "--keywords" in result.stderr
    assert "--exclude-keywords" in result.stdout or "--exclude-keywords" in result.stderr
