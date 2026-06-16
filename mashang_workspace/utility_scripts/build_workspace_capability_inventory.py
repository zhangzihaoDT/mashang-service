#!/usr/bin/env python
"""
build_workspace_capability_inventory.py — 生成 Workspace 级能力总览

扫描 mashang_workspace 中的能力资产，生成 capability inventory：
  - Skills: Agent 会什么（从 workspace_skills_catalog.json 或 SKILL.md 目录）
  - Scripts: Agent 能调用什么（从 runtime/research/utility/legacy scripts）
  - Data Assets: Agent 能查什么（从 docs / configs / shared）
  - Outputs / Reports: Agent 已沉淀什么（从 outputs/reports/ / monthly_market_report/）
  - Evaluation / Quality: Agent 是否可靠（从 eval/ / tests/）

JSON 为唯一事实源，Markdown / HTML 从 JSON 渲染。
"""

import json
import os
import re
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

WS_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = WS_ROOT.parent
OUTPUT_DIR = WS_ROOT / "outputs" / "reports"
ASSETS_DIR = WS_ROOT / "assets" / "brand"

NOW = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
TODAY = NOW[:10]

SCRIPT_DIRS = {
    "runtime_scripts": WS_ROOT / "runtime_scripts",
    "research_scripts": WS_ROOT / "research_scripts",
    "utility_scripts": WS_ROOT / "utility_scripts",
    "legacy_scripts": WS_ROOT / "legacy_scripts",
}

EVAL_DIR = WS_ROOT / "eval"
TESTS_DIR = WS_ROOT / "tests"

SKILLS_CATALOG_JSON = OUTPUT_DIR / "workspace_skills_catalog.json"
SKILLS_DIR = WS_ROOT / ".opencode" / "skills"
CONFIGS_DIR = WS_ROOT / "configs"
DOCS_DIR = WS_ROOT / "docs"
UTILS_DIR = WS_ROOT / "utils"

MONTHLY_OUTPUT_DIR = WS_ROOT / "outputs" / "monthly_market_report"

GROUP_LABELS = {
    "skills": ("Skills", "Agent 会什么"),
    "scripts": ("Scripts", "Agent 能调用什么"),
    "data_assets": ("Data Assets", "Agent 能查什么"),
    "outputs": ("Outputs / Reports", "Agent 已沉淀什么"),
    "evaluation": ("Evaluation / Quality", "Agent 是否可靠"),
}

RECOMMENDED_WORKFLOW = [
    "1. 用户提出业务问题",
    "2. Agent 根据 Skill 判断任务类型",
    "3. Skill 调度对应 scripts",
    "4. scripts 消费 data assets",
    "5. outputs 沉淀报告 / JSON / Markdown / HTML",
    "6. tests / eval 验证能力稳定性",
]


# ── Helpers ──────────────────────────────────────────────────────


def extract_docstring(path: Path, max_len: int = 0) -> str:
    """Extract first docstring paragraph from a Python file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    m = re.match(
        r'(?:"""|\'\'\')\s*(.*?)\s*(?:"""|\'\'\')', text, re.DOTALL
    )
    if not m:
        return ""
    doc = m.group(1).strip()
    first = doc.split("\n\n")[0].strip()
    if max_len and len(first) > max_len:
        for punct in "。！？.?!\n":
            idx = first.rfind(punct, 0, max_len)
            if idx >= max_len * 0.3:
                return first[: idx + 1]
        idx = first.rfind(" ", 0, max_len)
        if idx >= max_len * 0.3:
            return first[:idx]
        return first[:max_len]
    return first


def has_cli(path: Path) -> bool:
    """Detect if a Python script has CLI capability."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False
    patterns = [
        r"argparse",
        r"import click",
        r'if\s+__name__\s*==\s*["\']__main__["\']',
        r"parser\.add_argument",
    ]
    return any(re.search(p, text) for p in patterns)


def likely_outputs(path: Path) -> list[str]:
    """Infer likely output types from a script's name and content."""
    outputs = set()
    name = path.stem.lower()
    if any(kw in name for kw in ["report", "catalog", "forecast", "analysis"]):
        outputs.add("html_report")
    if "chart" in name or "plot" in name:
        outputs.add("chart")
    if any(kw in name for kw in ["json", "contract"]):
        outputs.add("json_contract")
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        if '--format json' in text or '--output' in text:
            outputs.add("structured_data")
    except Exception:
        pass
    return sorted(outputs) if outputs else ["unknown"]


def make_short_description(text: str, max_chars: int = 80) -> str:
    if not text or len(text) <= max_chars:
        return text or ""
    truncated = text[:max_chars]
    for punct in "。！？.?!\n":
        idx = truncated.rfind(punct)
        if idx >= max_chars * 0.4:
            return truncated[: idx + 1]
    idx = truncated.rfind(" ")
    if idx >= max_chars * 0.3:
        return truncated[:idx]
    for punct in "，、,":
        idx = truncated.rfind(punct)
        if idx >= max_chars * 0.4:
            return truncated[: idx + 1]
    return truncated


def rel_path(p: Path) -> str:
    """Return workspace-relative path string."""
    try:
        r = p.relative_to(WS_ROOT)
        return f"mashang_workspace/{r}"
    except ValueError:
        try:
            r = p.relative_to(REPO_ROOT)
            return str(r)
        except ValueError:
            return str(p)


def status_from_path(p: Path) -> str:
    """Infer status from script location."""
    parent_name = p.parent.name
    if parent_name == "legacy_scripts":
        return "legacy"
    return "active"


# ── 1. Skills ────────────────────────────────────────────────────


def load_skills() -> list[dict]:
    """Load skills from existing catalog JSON, fallback to SKILL.md scan."""
    if SKILLS_CATALOG_JSON.exists():
        try:
            data = json.loads(SKILLS_CATALOG_JSON.read_text(encoding="utf-8"))
            skills = data.get("skills", [])
            result = []
            for s in skills:
                result.append(
                    {
                        "name": s.get("name", "?"),
                        "path": s.get("skill_path", f".opencode/skills/{s.get('name', '?')}/"),
                        "description": s.get("description", ""),
                        "short_description": s.get("short_description", ""),
                        "group": s.get("group", "other"),
                        "entrypoint": s.get("entrypoint", ""),
                        "related_scripts": s.get("related_scripts", []),
                        "output_paths": s.get("output_paths", []),
                        "status": s.get("status", "active"),
                    }
                )
            return result
        except Exception:
            pass

    # Fallback: scan SKILL.md directories
    result = []
    if SKILLS_DIR.exists():
        for entry in sorted(SKILLS_DIR.iterdir()):
            smd = entry / "SKILL.md"
            if entry.is_dir() and smd.exists():
                text = smd.read_text(encoding="utf-8")
                import yaml
                fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
                desc = ""
                name = entry.name
                if fm_match:
                    try:
                        fm = yaml.safe_load(fm_match.group(1)) or {}
                        name = fm.get("name", name)
                        desc = fm.get("description", "")
                    except Exception:
                        pass
                result.append(
                    {
                        "name": name,
                        "path": f".opencode/skills/{entry.name}/",
                        "description": desc,
                        "short_description": make_short_description(desc, 80),
                        "group": "other",
                        "entrypoint": f".opencode/skills/{entry.name}/SKILL.md",
                        "related_scripts": [],
                        "output_paths": [],
                        "status": "active",
                    }
                )
    return result


# ── 2. Scripts ───────────────────────────────────────────────────


def scan_scripts() -> list[dict]:
    """Scan all script directories for Python files."""
    result = []
    for category, dir_path in SCRIPT_DIRS.items():
        if not dir_path.exists():
            continue
        for f in sorted(dir_path.rglob("*.py")):
            if f.name == "__init__.py":
                continue
            desc = extract_docstring(f)
            result.append(
                {
                    "name": f.relative_to(dir_path).as_posix(),
                    "path": rel_path(f),
                    "category": category,
                    "description": desc,
                    "short_description": make_short_description(desc, 80),
                    "has_cli": has_cli(f),
                    "likely_outputs": likely_outputs(f),
                    "status": status_from_path(f),
                }
            )
    return result


# ── 3. Data Assets ───────────────────────────────────────────────


def scan_data_assets() -> list[dict]:
    """Scan for known data assets from docs, configs, and shared references."""
    assets = []

    # passenger_insurance (shared data asset)
    assets.append(
        {
            "name": "passenger_insurance",
            "path": "dataset/passenger_insurance/",
            "type": "shared_service_data",
            "description": "service 级共享乘用车上险数据资产。6 张 Parquet 表（market_energy_monthly, brand_monthly, model_monthly, geo_monthly, price_segment_monthly, product_segment_monthly）。workspace 仅通过 shared loader 消费聚合结果，不直接读取 raw_csv。",
            "short_description": "乘用车上险数据（6 张 Parquet 表），workspace 通过 shared loaders 消费。",
            "tables_or_files": [
                "market_energy_monthly", "brand_monthly", "model_monthly",
                "geo_monthly", "price_segment_monthly", "product_segment_monthly",
                "registry/passenger_insurance_tables.json",
                "quality/data_quality_report.json",
            ],
            "grain": "date_month × fuel_type / brand / model / geo / price_segment / product_segment",
            "allowed_usage": "通过 shared.loaders.passenger_insurance_loader 读取；用于市场总量、品牌排名、车型结构、区域分布、价格带、细分市场分析",
            "forbidden_usage": "workspace 不直接读取 raw_csv；不修改 registry；不复制 parquet 到 workspace 内；不维护另一份 loader",
            "related_scripts": [
                "research_scripts/market_report/run_monthly_market_report.py",
            ],
            "status": "active",
        }
    )

    # order_data
    assets.append(
        {
            "name": "order_data",
            "path": "dataset/order_data.parquet",
            "type": "raw_dataset",
            "description": "订单主表（含锁单、交付、开票、退订等时间戳），445,915 行。",
            "short_description": "订单主表，含锁单/交付/开票/退订时间戳。",
            "tables_or_files": ["order_data.parquet"],
            "grain": "单笔订单",
            "allowed_usage": "锁单统计、车型分布、城市分布、时间趋势分析",
            "forbidden_usage": "不修改原始数据",
            "related_scripts": [
                "runtime_scripts/daily_lock_count.py",
                "runtime_scripts/lock_by_model.py",
                "runtime_scripts/lock_city_distribution.py",
            ],
            "status": "active",
        }
    )

    # assign_data
    assets.append(
        {
            "name": "assign_data",
            "path": "dataset/assign_data.csv",
            "type": "raw_dataset",
            "description": "下发线索表（含渠道拆解、7/30日转化），1,184 行。",
            "short_description": "下发线索表，含渠道拆解和转化分析。",
            "tables_or_files": ["assign_data.csv"],
            "grain": "单条线索",
            "allowed_usage": "线索转化率分析、渠道拆解",
            "forbidden_usage": "不修改原始数据",
            "related_scripts": [
                "runtime_scripts/assign_conversion_analysis.py",
                "research_scripts/lock_predict_backtest.py",
            ],
            "status": "active",
        }
    )

    # config_attribute
    assets.append(
        {
            "name": "config_attribute",
            "path": "dataset/config_attribute.parquet",
            "type": "raw_dataset",
            "description": "选配属性表（配置渗透率分析），2,196,954 行。",
            "short_description": "选配属性表，用于配置渗透率分析。",
            "tables_or_files": ["config_attribute.parquet"],
            "grain": "单车 × 选配项",
            "allowed_usage": "选装率分析、属性分布、配置渗透率报告",
            "forbidden_usage": "不修改原始数据",
            "related_scripts": [
                "runtime_scripts/attribute_penetration_report.py",
            ],
            "status": "active",
        }
    )

    # monthly_market_report_queries (config yaml)
    yaml_path = CONFIGS_DIR / "monthly_market_report_queries.yaml"
    if yaml_path.exists():
        assets.append(
            {
                "name": "monthly_market_report_queries",
                "path": rel_path(yaml_path),
                "type": "config_yaml",
                "description": "24 个固定市场月报查询问题定义（YAML 规范），供 run_monthly_market_report.py 使用。",
                "short_description": "24 个固定月报查询的 YAML 规范。",
                "tables_or_files": ["monthly_market_report_queries.yaml"],
                "grain": "24 个查询问题 × 时间参数",
                "allowed_usage": "run_monthly_market_report.py 读取并执行查询",
                "forbidden_usage": "不直接修改（通过 Query Spec 迭代）",
                "related_scripts": [
                    "research_scripts/market_report/run_monthly_market_report.py",
                ],
                "status": "active",
            }
        )

    # wechat_sync (VOC)
    assets.append(
        {
            "name": "wechat_sync",
            "path": "dataset/wechat/销售全员群.parquet",
            "type": "raw_dataset",
            "description": "微信群消息数据，用于 VOC 主题分析和情感挖掘。",
            "short_description": "微信群消息，VOC 情感/主题挖掘。",
            "tables_or_files": ["销售全员群.parquet"],
            "grain": "单条消息",
            "allowed_usage": "VOC 主题分析、情感挖掘",
            "forbidden_usage": "不修改原始数据；不展示原始消息内容",
            "related_scripts": [
                "utility_scripts/voc_theme_analysis.py",
            ],
            "status": "active",
        }
    )

    return assets


# ── 4. Outputs / Reports ────────────────────────────────────────


def scan_outputs() -> list[dict]:
    """Scan outputs/reports/ and outputs/monthly_market_report/ for generated files."""
    result = []

    reports_dir = WS_ROOT / "outputs" / "reports"
    if reports_dir.exists():
        for f in sorted(reports_dir.iterdir()):
            if f.is_file() and f.name != ".gitkeep":
                try:
                    mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                except Exception:
                    mtime = datetime.now(timezone.utc)
                try:
                    size_kb = round(f.stat().st_size / 1024, 1)
                except Exception:
                    size_kb = 0
                ext = f.suffix.lower()
                if ext == ".html":
                    ftype = "html_report"
                elif ext == ".md":
                    ftype = "markdown_report"
                elif ext == ".json":
                    ftype = "json_contract"
                elif ext == ".csv":
                    ftype = "structured_data"
                else:
                    ftype = "other"
                cap = _infer_capability(f.name)
                result.append(
                    {
                        "name": f.name,
                        "path": rel_path(f),
                        "description": f"生成报告，{size_kb} KB，{ftype.replace('_', ' ')}，关联能力：{cap}",
                        "short_description": f"{ftype.replace('_', ' ')} · {size_kb} KB",
                        "type": ftype,
                        "modified_at": mtime.strftime("%Y-%m-%d %H:%M"),
                        "size_kb": size_kb,
                        "related_capability": cap,
                        "status": "generated",
                    }
                )

    if MONTHLY_OUTPUT_DIR.exists():
        for month_dir in sorted(MONTHLY_OUTPUT_DIR.iterdir()):
            if not month_dir.is_dir():
                continue
            for f in sorted(month_dir.iterdir()):
                if f.is_file():
                    try:
                        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                    except Exception:
                        mtime = datetime.now(timezone.utc)
                    try:
                        size_kb = round(f.stat().st_size / 1024, 1)
                    except Exception:
                        size_kb = 0
                    ext = f.suffix.lower()
                    if ext == ".json":
                        ftype = "monthly_market_output"
                    elif ext == ".md":
                        ftype = "monthly_market_output"
                    else:
                        ftype = "monthly_market_output"
                    fname = f"{month_dir.name}/{f.name}"
                    desc_suffix = {".json": "JSON results", ".md": "report draft", ".yaml": "metadata"}.get(f.suffix.lower(), "monthly output")
                    result.append(
                        {
                            "name": fname,
                            "path": rel_path(f),
                            "description": f"{month_dir.name} 月报{desc_suffix}，{size_kb} KB",
                            "short_description": f"月报 · {month_dir.name} · {size_kb} KB",
                            "type": ftype,
                            "modified_at": mtime.strftime("%Y-%m-%d %H:%M"),
                            "size_kb": size_kb,
                            "related_capability": "monthly_market_report",
                            "status": "generated",
                        }
                    )

    return result


def _infer_capability(filename: str) -> str:
    low = filename.lower()
    if "workspace_skills_catalog" in low or "capability_inventory" in low:
        return "capability_catalog"
    if "lock_release" in low or "release_curve" in low:
        return "release_curve"
    if "backtest" in low or "forecast" in low or "predict" in low:
        return "prediction"
    if "atp" in low:
        return "atp_price"
    if "lock" in low or "city_distribution" in low:
        return "lock_analysis"
    if "weekly" in low or "competition" in low or "pk_" in low:
        return "competitive_analysis"
    if "daily_msg" in low or "voc" in low:
        return "voc_analysis"
    if "passenger_insurance" in low or "smoke" in low:
        return "data_quality"
    if "agent_execution" in low or "followup" in low:
        return "agent_trace"
    return "general_report"


# ── 5. Evaluation / Quality ──────────────────────────────────────


def scan_evaluation() -> list[dict]:
    """Scan eval/ and tests/ for quality assets."""
    result = []

    # Eval files
    if EVAL_DIR.exists():
        eval_files = sorted(
            EVAL_DIR.rglob("*.py")
        ) + sorted(EVAL_DIR.rglob("*.json")) + sorted(EVAL_DIR.rglob("*.jsonl")) + sorted(EVAL_DIR.rglob("*.md"))
        py_count = sum(1 for f in eval_files if f.suffix == ".py")
        json_count = sum(1 for f in eval_files if f.suffix in (".json", ".jsonl"))
        md_count = sum(1 for f in eval_files if f.suffix == ".md")

        # Detect eval suites from run_eval.py
        suites = ["core", "research", "parser", "followup", "numeric", "reference"]
        result.append(
            {
                "name": "eval_suites",
                "path": rel_path(EVAL_DIR / "run_eval.py"),
                "type": "eval_framework",
                "description": f"统一 Eval 框架，支持 {len(suites)} 个 suite（{', '.join(suites)}）。",
                "short_description": f"统一 Eval 框架，{len(suites)} suites。",
                "eval_files": py_count,
                "config_or_case_files": json_count,
                "doc_files": md_count,
                "suites": suites,
                "status": "active",
            }
        )

        # Context parser
        if (EVAL_DIR / "context_parser.py").exists():
            result.append(
                {
                    "name": "context_parser",
                    "path": rel_path(EVAL_DIR / "context_parser.py"),
                    "type": "nlp_parser",
                    "description": "自然语言上下文解析器。将用户自然语言解析为结构化 context（metric/time_window/series/city/group_by/filters）。",
                    "short_description": "自然语言 → 结构化 context。",
                    "eval_files": 1,
                    "config_or_case_files": 0,
                    "suites": ["parser"],
                    "status": "active",
                }
            )

        # Follow-up runner
        if (EVAL_DIR / "run_followup_eval.py").exists():
            result.append(
                {
                    "name": "followup_runner",
                    "path": rel_path(EVAL_DIR / "run_followup_eval.py"),
                    "type": "multi_turn_eval",
                    "description": "多轮追问评测工具。读取 followup_cases.json，逐轮解析 expected_context → 推荐脚本 + CLI 参数，支持上下文继承。",
                    "short_description": "多轮追问评测。",
                    "eval_files": 1,
                    "config_or_case_files": 1,
                    "suites": ["followup"],
                    "status": "active",
                }
            )

    # Test files
    if TESTS_DIR.exists():
        test_files = sorted(TESTS_DIR.rglob("test_*.py"))
        test_count = len(test_files)
        result.append(
            {
                "name": "pytest_tests",
                "path": rel_path(TESTS_DIR),
                "type": "test_suite",
                "description": f"pytest 测试套件，共 {test_count} 个测试文件。覆盖：脚本 smoke test、eval 测试、数据流水线测试、根目录清理验证、脚本分层验证。",
                "short_description": f"{test_count} 个测试文件的 pytest 套件。",
                "eval_files": test_count,
                "config_or_case_files": 0,
                "suites": [],
                "status": "active",
            }
        )

    # Cached eval report
    eval_report = EVAL_DIR / "eval_report.json"
    if eval_report.exists():
        try:
            report_data = json.loads(eval_report.read_text(encoding="utf-8"))
            suites_count = len(report_data.get("results", []))
            pass_rate = None
            if "pass" in report_data and "total" in report_data and report_data["total"]:
                pass_rate = round(report_data["pass"] / report_data["total"] * 100, 1)
        except Exception:
            suites_count = 0
            pass_rate = None
        result.append(
            {
                "name": "cached_eval_report",
                "path": rel_path(eval_report),
                "type": "eval_result",
                "description": f"最后一次 Eval 运行报告。suites: {suites_count}，通过率: {f'{pass_rate}%' if pass_rate is not None else 'N/A'}。",
                "short_description": f"缓存的 Eval 报告（{suites_count} suites, {f'{pass_rate}%' if pass_rate is not None else 'N/A'}）",
                "eval_files": suites_count,
                "config_or_case_files": 0,
                "suites": [],
                "status": "generated",
            }
        )

    # Regression notes
    reg_notes = EVAL_DIR / "regression_notes.md"
    if reg_notes.exists():
        result.append(
            {
                "name": "regression_notes",
                "path": rel_path(reg_notes),
                "type": "documentation",
                "description": "Regression 测试说明文档。",
                "short_description": "Regression 测试文档。",
                "eval_files": 0,
                "config_or_case_files": 0,
                "suites": [],
                "status": "generated",
            }
        )

    if not result:
        result.append(
            {
                "name": "no_eval_detected",
                "path": "eval/",
                "type": "empty",
                "description": "未检测到 eval 或 test 资产。",
                "short_description": "未检测到质量资产。",
                "eval_files": 0,
                "config_or_case_files": 0,
                "suites": [],
                "status": "missing",
            }
        )

    return result


# ── Build JSON ───────────────────────────────────────────────────


def build_inventory() -> dict:
    skills = load_skills()
    scripts = scan_scripts()
    data_assets = scan_data_assets()
    outputs = scan_outputs()
    evaluation = scan_evaluation()

    groups = [
        {
            "id": "skills",
            "title": GROUP_LABELS["skills"][0],
            "subtitle": GROUP_LABELS["skills"][1],
            "description": "Agent 可以通过 skill 匹配识别任务类型、选择执行方式、调用对应脚本和模板。每个 skill 包含 SKILL.md 指令文件，指导 Agent 如何响应特定场景。",
            "items": skills,
        },
        {
            "id": "scripts",
            "title": GROUP_LABELS["scripts"][0],
            "subtitle": GROUP_LABELS["scripts"][1],
            "description": "Agent 可直接调用的 Python 脚本，按功能分为 runtime（稳定运行入口）、research（研究分析）、utility（工具/渲染/验证）和 legacy（历史保留）四类。",
            "items": scripts,
        },
        {
            "id": "data_assets",
            "title": GROUP_LABELS["data_assets"][0],
            "subtitle": GROUP_LABELS["data_assets"][1],
            "description": "Agent 可查询的数据来源，包括 dataset/ 下的原始数据文件、shared loader 接入的 service 级数据资产、以及 config 目录下的配置规范。",
            "items": data_assets,
        },
        {
            "id": "outputs",
            "title": GROUP_LABELS["outputs"][0],
            "subtitle": GROUP_LABELS["outputs"][1],
            "description": "Agent 执行后沉淀的输出成果，包括 reports/ 下的品牌化 HTML 报告、Markdown 分析和 JSON 数据契约，以及 monthly_market_report/ 下的月报数据底稿。",
            "items": outputs,
        },
        {
            "id": "evaluation",
            "title": GROUP_LABELS["evaluation"][0],
            "subtitle": GROUP_LABELS["evaluation"][1],
            "description": "Agent 能力的质量保障体系，包括统一 Eval 框架、上下文解析评测、多轮追问评测、数值校验、pytest 测试套件和回归测试记录。",
            "items": evaluation,
        },
    ]

    return {
        "inventory_name": "workspace_capability_inventory",
        "version": "0.1",
        "generated_at": NOW,
        "workspace": "mashang_workspace",
        "summary": {
            "skills": len(skills),
            "script_categories": len([d for d in SCRIPT_DIRS if (WS_ROOT / d).exists()]),
            "scripts": len(scripts),
            "data_assets": len(data_assets),
            "outputs": len(outputs),
            "quality_assets": len(evaluation),
        },
        "groups": groups,
        "recommended_workflow": RECOMMENDED_WORKFLOW,
        "notes": [
            "JSON 为唯一事实源（Single Source of Truth），Markdown 与 HTML 从 JSON 渲染。",
            "outputs/ 下的文件仅展示文件名、类型、大小和生成时间，不读取文件内容。",
            "dataset/ 下的数据资产仅展示逻辑路径和元信息，不读取原始数据文件。",
            "本 inventory 由脚本自动生成，对应脚本路径：mashang_workspace/utility_scripts/build_workspace_capability_inventory.py",
        ],
    }


# ── Write JSON ───────────────────────────────────────────────────


def write_json(data: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  ✓ JSON: {path}")


# ── Write Markdown (from JSON only) ──────────────────────────────


def write_markdown(data: dict, path: Path):
    summary = data["summary"]
    groups = data["groups"]
    lines = [
        "# Mashang Workspace Capability Inventory",
        "",
        "Workspace 能力总览：skills / scripts / data assets / outputs / evaluation",
        "",
        f"生成时间：{data['generated_at']}",
        f"Workspace：{data['workspace']}",
        "",
        "---",
        "",
        "## Summary",
        "",
        "| 能力类型 | 数量 |",
        "|---------|------|",
        f"| Skills（Agent 会什么） | {summary['skills']} |",
        f"| Scripts（Agent 能调用什么） | {summary['scripts']} |",
        f"| Data Assets（Agent 能查什么） | {summary['data_assets']} |",
        f"| Outputs / Reports（Agent 已沉淀什么） | {summary['outputs']} |",
        f"| Evaluation / Quality（Agent 是否可靠） | {summary['quality_assets']} |",
        "",
        "---",
        "",
    ]

    for g in groups:
        lines += [
            f"## {g['id']}. {g['title']}：{g['subtitle']}",
            "",
            g["description"],
            "",
        ]
        items = g["items"]
        if not items:
            lines += ["（未检测到资产）", "", "---", "", ""]
            continue

        lines += ["| # | 名称 | 描述 | 状态 |", "|---|------|------|------|"]
        for idx, item in enumerate(items, 1):
            desc = item.get("short_description") or item.get("description", "")
            desc_short = desc[:72] + "..." if len(desc) > 75 else desc
            st = item.get("status", "—")
            lines.append(f"| {idx} | {item['name']} | {desc_short} | {st} |")

        lines += ["", "---", ""]

    lines += [
        "## Recommended Workflow",
        "",
    ]
    for step in RECOMMENDED_WORKFLOW:
        lines += [f"- {step}"]
    lines += ["", "## Notes", ""]
    for note in data.get("notes", []):
        lines += [f"- {note}"]
    lines += [""]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  ✓ Markdown: {path}")


# ── Write HTML (from JSON only) ──────────────────────────────────


def write_html(data: dict, path: Path):
    summary = data["summary"]
    groups = data["groups"]

    def esc(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # KPI cards
    kpi_items = [
        ("Workspace Skills", str(summary["skills"]), "mashang_workspace"),
        ("Callable Scripts", str(summary["scripts"]), f"{summary['script_categories']} categories"),
        ("Data Assets", str(summary["data_assets"]), "read-only"),
        ("Generated Outputs", str(summary["outputs"]), "reports / data / charts"),
        ("Quality Assets", str(summary["quality_assets"]), "eval / tests"),
    ]
    kpi_cards = "\n".join(
        f"""
      <div class="kpi-card">
        <div class="label">{label}</div>
        <div class="value">{value}</div>
        <div class="change neutral">{sub}</div>
      </div>"""
        for label, value, sub in kpi_items
    )

    # Capability Map
    cap_map_items = [
        ("Skills", "Agent 会什么", summary["skills"]),
        ("Scripts", "Agent 能调用什么", summary["scripts"]),
        ("Data", "Agent 能查什么", summary["data_assets"]),
        ("Outputs", "Agent 已沉淀什么", summary["outputs"]),
        ("Evaluation", "Agent 如何自检", summary["quality_assets"]),
    ]
    cap_map = "\n".join(
        f"""
        <div class="cap-item">
          <div class="cap-icon">{idx + 1}</div>
          <div>
            <div class="cap-label">{label}</div>
            <div class="cap-sub">{sub}</div>
            <div class="cap-count">{count} 项资产</div>
          </div>
        </div>"""
        for idx, (label, sub, count) in enumerate(cap_map_items)
    )

    # Group sections
    group_sections = []
    for g in groups:
        items_html = ""
        items = g["items"]
        if not items:
            items_html = '<div class="empty-section">未检测到资产</div>'
        elif len(items) <= 8:
            # Card layout for few items
            cards = []
            for item in items:
                desc = esc(item.get("short_description") or item.get("description", "") or "未声明")
                st = item.get("status", "—")
                badge_cls = {"active": "green", "generated": "blue", "legacy": "gold", "missing": "gray"}.get(st, "blue")
                fields = []
                if "path" in item and item["path"]:
                    fields.append(f'<div class="inv-field"><span class="inv-field-label">Path</span><code>{esc(item["path"])}</code></div>')
                if "category" in item:
                    fields.append(f'<div class="inv-field"><span class="inv-field-label">Category</span>{esc(item["category"])}</div>')
                if "entrypoint" in item and item["entrypoint"]:
                    fields.append(f'<div class="inv-field"><span class="inv-field-label">Entry</span><code>{esc(item["entrypoint"])}</code></div>')
                if "related_scripts" in item and item["related_scripts"]:
                    scripts_str = ", ".join(f'<code>{esc(s)}</code>' for s in item["related_scripts"][:3])
                    if len(item["related_scripts"]) > 3:
                        scripts_str += f" +{len(item['related_scripts']) - 3} more"
                    fields.append(f'<div class="inv-field"><span class="inv-field-label">Scripts</span>{scripts_str}</div>')
                if "grain" in item and item["grain"]:
                    fields.append(f'<div class="inv-field"><span class="inv-field-label">Grain</span>{esc(item["grain"])}</div>')
                if "has_cli" in item:
                    fields.append(f'<div class="inv-field"><span class="inv-field-label">CLI</span>{"✅" if item["has_cli"] else "—"}</div>')
                if "likely_outputs" in item and item["likely_outputs"]:
                    out_str = ", ".join(item["likely_outputs"])
                    fields.append(f'<div class="inv-field"><span class="inv-field-label">Outputs</span>{out_str}</div>')
                if "eval_files" in item:
                    fields.append(f'<div class="inv-field"><span class="inv-field-label">Files</span>{item["eval_files"]}</div>')

                cards.append(f"""
          <div class="inv-card">
            <div class="inv-card-header">
              <div class="inv-card-name">{esc(item['name'])}</div>
              <span class="skill-badge badge-{badge_cls}">{esc(st)}</span>
            </div>
            <div class="inv-card-desc">{desc}</div>
            <div class="inv-card-fields">
              {''.join(fields)}
            </div>
          </div>""")
            items_html = "\n".join(cards)
        else:
            # Table layout for many items
            rows = []
            for item in items:
                desc = esc(item.get("short_description") or item.get("description", "") or "未声明")[:60]
                st = item.get("status", "—")
                rows.append(f"""
            <tr>
              <td><strong>{esc(item['name'])}</strong></td>
              <td>{desc}</td>
              <td><span class="badge-tag">{esc(st)}</span></td>
            </tr>""")
            items_html = f"""
          <div class="table-wrap">
            <table class="data-table">
              <thead><tr><th>Name</th><th>Description</th><th>Status</th></tr></thead>
              <tbody>{''.join(rows)}</tbody>
            </table>
          </div>"""

        group_sections.append(f"""
    <section class="card">
      <h2>{esc(g['title'])} <span class="group-subtitle">{esc(g['subtitle'])}</span></h2>
      <p class="group-desc">{esc(g['description'])}</p>
      <div class="inv-grid">
{items_html}
      </div>
    </section>""")

    # Workflow
    workflow_steps = "\n".join(
        f'          <div class="wf-step">{step}</div>' for step in RECOMMENDED_WORKFLOW
    )

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Mashang Workspace Capability Inventory</title>
  <link rel="stylesheet" href="../../templates/report_style.css" />
  <style>
    .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin-bottom: 32px; }}
    .kpi-card {{ background: var(--zh-card); border-radius: 12px; padding: 20px 20px; box-shadow: 0 1px 4px rgba(6,33,61,.06); border: 1px solid rgba(23,74,124,.06); }}
    .kpi-card .label {{ font-size: 11px; font-weight: 600; color: var(--zh-muted); text-transform: uppercase; letter-spacing: .4px; margin-bottom: 6px; }}
    .kpi-card .value {{ font-size: 28px; font-weight: 800; color: var(--zh-deep-blue); }}
    .kpi-card .change {{ font-size: 11px; color: var(--zh-muted); margin-top: 4px; }}

    .cap-map {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 32px; }}
    .cap-item {{ background: var(--zh-card); border-radius: 12px; padding: 16px 18px; display: flex; align-items: flex-start; gap: 12px; box-shadow: 0 1px 4px rgba(6,33,61,.06); border: 1px solid rgba(23,74,124,.06); }}
    .cap-icon {{ width: 28px; height: 28px; border-radius: 8px; background: var(--zh-blue); color: white; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700; flex-shrink: 0; }}
    .cap-label {{ font-size: 14px; font-weight: 700; color: var(--zh-deep-blue); }}
    .cap-sub {{ font-size: 11px; color: var(--zh-muted); }}
    .cap-count {{ font-size: 11px; color: var(--zh-blue); font-weight: 600; margin-top: 2px; }}

    .group-subtitle {{ font-size: 13px; font-weight: 400; color: var(--zh-muted); margin-left: 8px; }}
    .group-desc {{ font-size: 13px; color: var(--zh-muted); line-height: 1.6; margin-bottom: 16px; }}

    .inv-grid {{ display: grid; gap: 16px; }}
    .inv-card {{ background: var(--zh-card); border-radius: 12px; padding: 20px 22px; box-shadow: 0 1px 4px rgba(6,33,61,.06); border: 1px solid rgba(23,74,124,.06); }}
    .inv-card:hover {{ box-shadow: 0 4px 24px rgba(6,33,61,.10); border-color: rgba(23,74,124,.15); }}
    .inv-card-header {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }}
    .inv-card-name {{ font-size: 15px; font-weight: 700; color: var(--zh-deep-blue); word-break: break-all; }}
    .inv-card-desc {{ font-size: 13px; line-height: 1.6; color: var(--zh-text); margin-bottom: 10px; }}
    .inv-card-fields {{ display: flex; flex-direction: column; gap: 5px; }}
    .inv-field {{ font-size: 12px; color: var(--zh-text); line-height: 1.5; }}
    .inv-field code {{ background: var(--zh-cream); padding: 1px 5px; border-radius: 3px; font-size: 11px; word-break: break-all; }}
    .inv-field-label {{ font-size: 10px; font-weight: 600; color: var(--zh-muted); text-transform: uppercase; letter-spacing: .3px; margin-right: 6px; display: inline-block; min-width: 60px; }}

    .skill-badge {{ font-size: 10px; font-weight: 600; padding: 2px 10px; border-radius: 12px; white-space: nowrap; }}
    .badge-green {{ background: rgba(72,187,120,.12); color: #2F855A; }}
    .badge-blue {{ background: var(--zh-light-blue); color: var(--zh-blue); }}
    .badge-gold {{ background: rgba(215,154,54,.08); color: var(--zh-brown); }}
    .badge-gray {{ background: rgba(107,124,143,.08); color: var(--zh-muted); }}
    .badge-tag {{ font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 8px; background: rgba(126,205,235,.12); color: #2A6B8A; white-space: nowrap; }}

    .wf-step {{ font-size: 13px; color: var(--zh-text); line-height: 1.8; padding: 6px 0; border-bottom: 1px solid rgba(23,74,124,.04); }}
    .wf-step:last-child {{ border-bottom: none; }}

    .empty-section {{ font-size: 13px; color: var(--zh-muted); font-style: italic; padding: 12px 0; }}

    .note-list {{ font-size: 12px; color: var(--zh-muted); line-height: 1.7; }}
    .note-list li {{ margin-bottom: 4px; }}
  </style>
</head>
<body>

  <header>
    <div class="container">
      <div class="brand">
        <img class="brand-avatar" src="../../assets/brand/raccoon_avatar_light.png" alt="" />
        <span class="brand-name">Raccoon Research</span>
      </div>
      <span class="header-meta">workspace_capability_inventory | {TODAY}</span>
    </div>
  </header>

  <main class="container">

    <section class="hero">
      <h1>Mashang Workspace Capability Inventory</h1>
      <p>Agent Harness 能力总览 · skills / scripts / data assets / outputs / evaluation</p>
    </section>

    <section class="kpi-grid">
{kpi_cards}
    </section>

    <section class="card">
      <h2>Capability Map</h2>
      <div class="cap-map">
{cap_map}
      </div>
    </section>

{''.join(group_sections)}

    <section class="card">
      <h2>Recommended Workflow</h2>
      <div class="wf-steps">
{workflow_steps}
      </div>
    </section>

    <section class="card">
      <h2>Notes</h2>
      <ul class="note-list">
{chr(10).join(f'        <li>{esc(n)}</li>' for n in data.get("notes", []))}
      </ul>
    </section>

  </main>

  <footer>
    <img class="brand-sig" src="../../assets/brand/zihao_signature_transparent.png" alt="Raccoon Research" />
    <div class="brand-sentence">用数据、AI 和一点点常识，研究复杂世界。</div>
    <div style="font-size:11px;color:var(--zh-muted);margin-top:8px">mashang_workspace/outputs/reports/workspace_capability_inventory.html</div>
  </footer>

</body>
</html>"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    print(f"  ✓ HTML: {path}")


# ── Main ─────────────────────────────────────────────────────────


def main():
    print("=" * 60)
    print("  Build Workspace Capability Inventory")
    print("=" * 60)
    print()
    print(f"  Workspace: {WS_ROOT}")
    print()

    data = build_inventory()
    summary = data["summary"]
    print(f"  Summary:")
    print(f"    Skills:          {summary['skills']}")
    print(f"    Script categories: {summary['script_categories']}")
    print(f"    Scripts:         {summary['scripts']}")
    print(f"    Data Assets:     {summary['data_assets']}")
    print(f"    Outputs:         {summary['outputs']}")
    print(f"    Quality Assets:  {summary['quality_assets']}")
    print()

    json_path = OUTPUT_DIR / "workspace_capability_inventory.json"
    md_path = OUTPUT_DIR / "workspace_capability_inventory.md"
    html_path = OUTPUT_DIR / "workspace_capability_inventory.html"

    write_json(data, json_path)

    # Re-read JSON as single source of truth for MD and HTML
    data_for_derived = json.loads(json_path.read_text(encoding="utf-8"))
    write_markdown(data_for_derived, md_path)
    write_html(data_for_derived, html_path)

    print()
    print("=" * 60)
    print("  Inventory generated successfully")
    print("=" * 60)
    print(f"  JSON:    {json_path}")
    print(f"  Markdown: {md_path}")
    print(f"  HTML:    {html_path}")
    print()


if __name__ == "__main__":
    main()
