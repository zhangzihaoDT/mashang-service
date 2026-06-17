"""
Smoke test: auto_launch_monitor.py v0.2

验证:
1. --help 正常输出
2. 无 API Key 时给出清晰错误提示
3. 单一主流媒体 → confidence="中"
4. 2+ 来源交叉验证 → confidence="高"
5. 官方来源 → confidence="高"
6. markdown 输出包含 source_url 和 evidence
"""

import json
import os
import subprocess
import sys
from pathlib import Path

_WS_DIR = Path(__file__).resolve().parents[2]
SCRIPT = _WS_DIR / "research_scripts" / "auto_launch_monitor.py"


def _run(args: list[str], env_override: dict | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    if env_override:
        env.update(env_override)
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + args,
        capture_output=True, text=True, timeout=30,
        env=env,
    )


_SCRIPT_DIR = _WS_DIR / "research_scripts"


def _extract_py(env, code):
    """Run Python code snippet in subprocess with env."""
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=30,
        env=env,
    )


# ─── Confidence rule tests (unit tests on aggregate_events) ────────────

def test_single_mainstream_confidence_is_medium():
    code = """
import sys, json
sys.path.insert(0, r"${SD}")
from auto_launch_monitor import aggregate_events

events = [
    {
        "date": "2026-06-05", "brand": "本田", "model": "CR-V",
        "event_type": "上市", "event_status": "已确认",
        "source_title": "太平洋汽车", "source_url": "https://price.pcauto.com.cn/cars/6",
        "source_type": "mainstream", "confidence": "高", "evidence": "test",
    },
]
result = aggregate_events(events)
print(json.dumps([{"confidence": e["confidence"]} for e in result], ensure_ascii=False))
""".replace("${SD}", str(_SCRIPT_DIR))
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"
    data = json.loads(result.stdout)
    assert len(data) == 1
    assert data[0]["confidence"] == "中", f"expected 中, got {data[0]['confidence']}"


def test_two_sources_cross_verify_confidence_is_high():
    code = """
import sys, json
sys.path.insert(0, r"${SD}")
from auto_launch_monitor import aggregate_events

events = [
    {
        "date": "2026-06-05", "brand": "本田", "model": "CR-V",
        "event_type": "上市", "event_status": "已确认",
        "source_title": "太平洋汽车", "source_url": "https://price.pcauto.com.cn/cars/6",
        "source_type": "mainstream", "confidence": "高", "evidence": "test1",
    },
    {
        "date": "2026-06-05", "brand": "本田", "model": "CR-V",
        "event_type": "上市", "event_status": "已确认",
        "source_title": "新浪汽车", "source_url": "https://auto.sina.com.cn/newcar/",
        "source_type": "mainstream", "confidence": "高", "evidence": "test2",
    },
]
result = aggregate_events(events)
print(json.dumps([{"confidence": e["confidence"], "source_urls": e.get("source_urls", [])} for e in result], ensure_ascii=False))
""".replace("${SD}", str(_SCRIPT_DIR))
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"
    data = json.loads(result.stdout)
    assert len(data) == 1
    assert data[0]["confidence"] == "高", f"expected 高, got {data[0]['confidence']}"
    assert len(data[0]["source_urls"]) == 2


def test_official_source_confidence_is_high():
    code = """
import sys, json
sys.path.insert(0, r"${SD}")
from auto_launch_monitor import aggregate_events

events = [
    {
        "date": "2026-06-05", "brand": "理想", "model": "L8",
        "event_type": "发布", "event_status": "已确认",
        "source_title": "理想汽车官网", "source_url": "https://www.lixiang.com/help/support/5433/5439.html",
        "source_type": "official", "confidence": "高", "evidence": "test",
    },
]
result = aggregate_events(events)
print(json.dumps([{"confidence": e["confidence"]} for e in result], ensure_ascii=False))
""".replace("${SD}", str(_SCRIPT_DIR))
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"
    data = json.loads(result.stdout)
    assert len(data) == 1
    assert data[0]["confidence"] == "高", f"expected 高, got {data[0]['confidence']}"


# ─── Markdown content tests ────────────────────────────────────────

def test_markdown_contains_source_url_and_evidence():
    code = """
import sys
sys.path.insert(0, r"${SD}")
from auto_launch_monitor import format_markdown, build_event_summary

events = [
    {
        "date": "2026-06-05", "brand": "本田", "model": "CR-V",
        "event_type": "上市", "event_status": "已确认",
        "source_title": "太平洋汽车", "source_url": "https://price.pcauto.com.cn/cars/6",
        "source_urls": ["https://price.pcauto.com.cn/cars/6"],
        "source_type": "mainstream", "confidence": "中", "evidence": "2026年06月05日上市",
    },
]
summary = build_event_summary(events, "新车发布会")
md = format_markdown(events, summary, "2026-06-05", "2026-06-07", "新车发布会")
assert "source_url" not in md, "source_url column should be '来源'"
assert "证据" in md, "markdown should contain 证据 column"
assert "https://price.pcauto.com.cn/cars/6" in md, "markdown should contain source URL"
assert "2026年06月05日上市" in md, "markdown should contain evidence"
assert "汽车新车事件监测报告" in md, "markdown title should be 汽车新车事件监测报告"
print(md)
""".replace("${SD}", str(_SCRIPT_DIR))
    result = _extract_py(os.environ.copy(), code)
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ─── Original smoke tests ───────────────────────────────────────────

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
    assert "--format" in result.stdout or "--format" in result.stderr
