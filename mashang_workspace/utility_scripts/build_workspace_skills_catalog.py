#!/usr/bin/env python
"""
build_workspace_skills_catalog.py — 生成 workspace skills catalog

扫描 mashang_workspace/.opencode/skills/ 下的所有 SKILL.md，
输出 JSON / Markdown / HTML 三种格式的 skills catalog 页面。

用法:
    python utility_scripts/build_workspace_skills_catalog.py
"""

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

WS_ROOT = REPO_ROOT / "mashang_workspace"
SKILLS_DIR = WS_ROOT / ".opencode" / "skills"
OUTPUT_DIR = WS_ROOT / "outputs" / "reports"
REPO_SKILLS_DIR = REPO_ROOT / ".opencode" / "skills"
ASSETS_DIR = WS_ROOT / "assets" / "brand"
TEMPLATES_DIR = WS_ROOT / "templates"

TODAY = date.today().isoformat()


def parse_skill(path: Path) -> dict:
    skill_dir = path.name
    skill_md = path / "SKILL.md"
    if not skill_md.exists():
        return None

    text = skill_md.read_text(encoding="utf-8")

    # Parse YAML frontmatter
    frontmatter = {}
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if fm_match:
        try:
            frontmatter = yaml.safe_load(fm_match.group(1)) or {}
        except Exception:
            frontmatter = {}
        text = text[fm_match.end():]

    name = frontmatter.get("name", skill_dir)
    description = frontmatter.get("description", "")

    # Parse sections
    sections = {}
    current_section = None
    current_lines = []

    def flush_section():
        nonlocal current_section, current_lines
        if current_section:
            sections[current_section] = "\n".join(current_lines).strip()
        current_lines = []

    for line in text.split("\n"):
        h_match = re.match(r"^##\s+(.+)$", line.strip())
        if h_match:
            flush_section()
            current_section = h_match.group(1).strip()
        else:
            current_lines.append(line)
    flush_section()

    # Helpers
    def list_items(keywords):
        items = []
        content = sections.get(keywords[0] if isinstance(keywords, str) else "", "")
        if not content and isinstance(keywords, list):
            for kw in keywords:
                content = sections.get(kw, "")
                if content:
                    break
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("- "):
                items.append(stripped[2:].strip())
        return items

    positioning = ""
    for kw in ["能力定位"]:
        if kw in sections:
            positioning = sections[kw].split("\n")[0].strip()
            break

    scenarios = list_items(["适用场景"])
    not_for = list_items(["不适用场景"])

    # Entrypoints
    entrypoints = []
    for kw in ["核心命令", "核心入口", "使用步骤"]:
        content = sections.get(kw, "")
        if content:
            for line in content.split("\n"):
                if line.strip().startswith("```"):
                    continue
                if line.strip().startswith("python") or line.strip().startswith("make "):
                    entrypoints.append(line.strip().strip("$").strip())
            if entrypoints:
                break
    # Fallback: extract code blocks
    if not entrypoints:
        for kw in ["渲染脚本", "核心命令", "核心入口", "使用步骤"]:
            content = sections.get(kw, "")
            in_code = False
            for line in content.split("\n"):
                if line.strip().startswith("```"):
                    in_code = not in_code
                    continue
                if in_code and (line.strip().startswith("python") or line.strip().startswith("make ")):
                    entrypoints.append(line.strip())

    # Outputs
    outputs = []
    for kw in ["默认输出位置", "默认输出"]:
        content = sections.get(kw, "")
        for line in content.split("\n"):
            stripped = line.strip().strip("`")
            if stripped and not stripped.startswith("#") and not stripped.startswith("- "):
                if "outputs" in stripped or "/" in stripped:
                    outputs.append(stripped)
                    break

    constraints = list_items(["重要约束", "不涉及的行为", "Constraints"])

    return {
        "name": name,
        "directory": f".opencode/skills/{skill_dir}/",
        "description": description,
        "positioning": positioning,
        "scenarios": scenarios,
        "not_for": not_for,
        "entrypoints": entrypoints if entrypoints else [f"OpenCode Agent 自动匹配 — SKILL.md 位于 .opencode/skills/{skill_dir}/"],
        "outputs": outputs,
        "constraints": constraints,
        "level": "workspace",
    }


def scan_workspace_skills() -> list[dict]:
    skills = []
    if not SKILLS_DIR.exists():
        return skills
    for entry in sorted(SKILLS_DIR.iterdir()):
        if entry.is_dir() and (entry / "SKILL.md").exists():
            skill = parse_skill(entry)
            if skill:
                skills.append(skill)
    return skills


# ─── Promptbuilder scan ────────────────────────────────────────

PROMPTBUILDER_CAPABILITIES = {
    "auto_launch": {
        "name": "auto_launch",
        "type": "Standalone Service (research_apps/auto_launch/)",
        "directory": "research_apps/auto_launch/",
        "description": "汽车上市/营销事件独立监控服务；搜索意图编译 → query plan → Volc Search API → 信源分级 → URL 去重 → 事件聚类 → candidate gate → Markdown 简报。",
        "entrypoints": [
            "PYTHONPATH=research_apps python -m auto_launch.cli report --type brand-daily --brand 智己",
            "PYTHONPATH=research_apps python -m auto_launch.cli search --request '看看极氪最近 7 天都有什么动作'",
            "make auto-launch-owned-brand-daily",
        ],
        "outputs": [
            "research_apps/auto_launch/outputs/search/{date}/{mode}/",
            "research_apps/auto_launch/outputs/owned_brand_daily/{date}/",
        ],
        "docs": [
            "research_apps/auto_launch/README.md",
            "research_apps/auto_launch/docs/workflow.md",
        ],
        "scenarios": [
            "本品品牌每日营销事件监控",
            "竞品车型动态追踪",
            "搜索意图编译 → Volc Search 执行",
            "搜索结果标准化 + 信源分级",
            "事件聚类 + candidate gate 分桶",
        ],
        "not_for": [
            "生成长篇竞品分析报告",
            "替代完整爬虫/ETL 系统",
            "非汽车行业的通用事件监测",
        ],
    },
    "miit_new_car": {
        "name": "miit_new_car",
        "type": "Promptbuilder / MIIT Workflow",
        "directory": "promptbuilders/miit_new_car/",
        "description": "MIIT 新车公告全链路情报分析：批次管理、图片 OCR、结构化解析、6 信号双车对比。",
        "scenarios": [
            "MIIT 批次发现/抓取/附件文本抽取/产品清单解析",
            "公告详情页截图 OCR（document_parse + general_ocr）",
            "OCR 结果 → 结构化车辆 records JSON（43 字段）",
            "双车对比 → 6 个关键信号框架 HTML 报告",
        ],
        "not_for": [
            "非 MIIT 公告来源的图片 OCR",
            "批次粒度的跨厂家汇总分析",
            "带市场威胁强度的竞争分析",
        ],
        "entrypoints": [
            "python mashang_workspace/promptbuilders/miit_new_car/miit_vehicle_publicity_image_parser.py --ocr-result <path> --fallback-ocr-result <path> --force",
            "python mashang_workspace/promptbuilders/miit_new_car/vehicle_compare.py --record-a <path> --record-b <path> --output <path>",
            "make miit-fetch-batch BATCH=N",
        ],
        "outputs": [
            "mashang_workspace/outputs/miit_new_car/promptbuilder_runs/",
            "mashang_workspace/outputs/miit_new_car/vehicle_publicity_detail/records/",
            "mashang_workspace/outputs/reports/",
            "outputs/ocr/",
        ],
        "depends_on": [
            "capabilities/ocr/（火山引擎 OCR base capability）",
            "miit_vehicle_publicity_image_parser.py（OCR → records）",
            "vehicle_compare.py（records → 6 信号报告）",
            "research_apps/MIIT/data/eidc/（历史数据归档）",
        ],
        "status": "deprecated",
        "status_note": "实现已随 workspace miit_new_car 移除；历史数据成果归档于 research_apps/MIIT/data/eidc/，能力在 research_apps/MIIT/scripts 重新实现中",
    },
}


def scan_promptbuilders() -> list[dict]:
    """Scan promptbuilders/ directory for registered capabilities."""
    promptbuilders_dir = WS_ROOT / "promptbuilders"
    if not promptbuilders_dir.exists():
        return []

    found = []
    for entry in sorted(promptbuilders_dir.iterdir()):
        if entry.is_dir() and (entry / "README.md").exists():
            name = entry.name
            cap = PROMPTBUILDER_CAPABILITIES.get(name)
            if cap:
                found.append(cap)
            else:
                # Auto-detect from README
                readme = (entry / "README.md").read_text(encoding="utf-8")
                first_line = readme.strip().split("\n")[0].lstrip("#").strip()
                found.append({
                    "name": name,
                    "type": "Promptbuilder",
                    "directory": f"promptbuilders/{name}/",
                    "description": first_line or f"Promptbuilder module at promptbuilders/{name}/",
                    "entrypoints": [f"promptbuilders/{name}/"],
                    "outputs": "",
                })
    return found


def build_json(skills: list[dict]) -> dict:
    return {
        "workspace": "mashang_workspace",
        "generated_at": TODAY,
        "skills": skills,
    }


def write_json(data: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  ✓ JSON: {path}")


def write_markdown(data: dict, skills: list[dict], path: Path):
    ws_count = len([s for s in skills if s.get("type", "").startswith("workspace") or "type" not in s])
    pb_count = len([s for s in skills if "Promptbuilder" in s.get("type", "")])
    all_count = len(skills)
    def _md_out(s):
        o = s.get("outputs", "")
        if isinstance(o, list):
            return o[0] if o else ""
        return str(o)
    output_dirs = ", ".join(set(_md_out(s) for s in skills if _md_out(s)))

    lines = [
        "# Mashang Workspace Skills Catalog",
        "",
        "Agent Harness 能力目录",
        "",
        f"生成日期：{TODAY}",
        "",
        "本页面展示 mashang_workspace 中可被 OpenCode Agent 调用的 workspace 级 skills。",
        "",
        "---",
        "",
        "## 概览",
        "",
        "| 指标 | 数值 |",
        "|------|------|",
        f"| Workspace Skills | {ws_count} |",
        f"| Skills 输出目录 | {output_dirs} |",
        f"| 最近更新 | {TODAY} |",
        "",
        "## Skills Overview",
        "",
        "| Skill | 类型 | 能力定位 | 入口文件 | 默认输出 |",
        "|-------|------|---------|---------|---------|",
    ]

    for s in skills:
        ep = s["entrypoints"][0] if s["entrypoints"] else "—"
        out = s.get("outputs", "") if s.get("outputs") else "—"
        stype = s.get("type", "workspace")
        positioning = s.get("positioning", s.get("description", ""))[:40]
        lines.append(f"| {s['name']} | {stype} | {positioning} | `{ep}` | {out} |")

    lines += [
        "",
        "## Workspace Skills 详情",
        "",
    ]

    for s in skills:
        stype = s.get("type", "workspace")
        positioning = s.get("positioning", s.get("description", ""))
        ep_display = s["entrypoints"][0] if s["entrypoints"] else "—"
        if "Promptbuilder" in stype:
            # Promptbuilder format
            lines += [
                f"### {s['name']} ({stype})",
                "",
                "| 字段 | 内容 |",
                "|------|------|",
                f"| 目录 | `{s['directory']}` |",
                f"| 类型 | {stype} |",
                f"| 能力定位 | {positioning} |",
                f"| 入口命令 | `{ep_display}` |",
                "",
            ]
        else:
            lines += [
                f"### {s['name']}",
                "",
                "| 字段 | 内容 |",
                "|------|------|",
                f"| 目录 | `{s['directory']}` |",
                "| 层级 | workspace |",
                f"| 能力定位 | {positioning} |",
                f"| 适用场景 | {'、'.join(s['scenarios'][:6]) if s['scenarios'] else '—'} |",
                f"| 不适用场景 | {'、'.join(s['not_for'][:4]) if s['not_for'] else '—'} |",
                f"| 入口命令 | `{ep_display}` |",
                f"| 默认输出 | {s.get('outputs', '—') if s.get('outputs') else '—'} |",
                "",
            ]

    lines += [
        "## 文件结构说明",
        "",
    ]
    for s in skills:
        stype = s.get("type", "workspace skill")
        lines += [
            f"- `{s['directory']}` — {s['name']} ({stype})",
        ]
    lines += [
        "- `utility_scripts/build_workspace_skills_catalog.py` — 本页生成脚本",
        "- `utility_scripts/render_html_report.py` — 品牌化报告渲染脚本",
        "- `templates/` — Jinja2 报告模板 + CSS",
        "- `assets/brand/` — Raccoon Research 品牌资产",
        "",
    ]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  ✓ Markdown: {path}")


def _ep_display(ep: str) -> str:
    """Shorten entrypoint to a human-readable label."""
    if "render_html_report.py" in ep:
        return "utility_scripts/render_html_report.py"
    if "eval_report.json" in ep or "eval" in ep:
        return "eval/eval_report.json"
    return ep.split(" --")[0].strip("$ ").strip() if ep else "—"


def write_html(data: dict, skills: list[dict], path: Path):
    ws_skills = [s for s in skills if "Promptbuilder" not in s.get("type", "")]
    pb_skills = [s for s in skills if "Promptbuilder" in s.get("type", "")]
    ws_count = len(ws_skills)
    pb_count = len(pb_skills)
    all_count = len(skills)
    skill_names_joined = " + ".join(s["name"] for s in skills)
    def _html_out(s):
        o = s.get("outputs", "")
        if isinstance(o, list):
            return o[0] if o else ""
        return str(o)
    output_dirs = ", ".join(set(_html_out(s) for s in skills if _html_out(s)))

    # Build overview table rows
    overview_rows = []
    for s in skills:
        ep = _ep_display(s["entrypoints"][0]) if s["entrypoints"] else "—"
        out = s.get("outputs", "") if s.get("outputs") else "—"
        stype = s.get("type", "workspace")
        badge_class = "badge-pb" if "Promptbuilder" in stype else "badge-ws"
        overview_rows.append(f"""
            <tr>
              <td><strong>{s['name']}</strong></td>
              <td><span class="badge {badge_class}">{stype}</span></td>
              <td>{s.get('positioning', s.get('description', ''))[:40]}</td>
              <td><code>{ep}</code></td>
              <td><code>{out}</code></td>
            </tr>""")

    # Build skill cards
    skill_cards = []
    for s in skills:
        stype = s.get("type", "workspace")
        is_pb = "Promptbuilder" in stype
        tags = []
        if is_pb:
            tags.append('            <span class="skill-tag gold">Promptbuilder</span>')
            tags.append('            <span class="skill-tag blue">Workflow</span>')
        else:
            for word in ["HTML", "品牌", "Jinja2", "Eval", "诊断", "Runtime", "报告", "模板", "预测", "回测", "质量保障", "Raccoon Research"]:
                desc = s.get("description", "")
                scens = s.get("scenarios", [])
                if word in desc or any(word in sc for sc in scens):
                    css = "gold" if word in ("预测", "回测", "质量保障") else "blue"
                    tags.append(f'            <span class="skill-tag {css}">{word}</span>')

        scenarios_li = "\n".join(f"                  <li>{sc}</li>" for sc in s.get("scenarios", [])[:8]) if not is_pb else ""
        not_for_li = "\n".join(f"                  <li>{nf}</li>" for nf in s.get("not_for", [])[:6]) if not is_pb else ""

        # Entrypoints: promptbuilder entries use full list
        ep_display = _ep_display(s["entrypoints"][0]) if s["entrypoints"] else "—"
        ep_lines = "\n".join(f'                  <code>{ep}</code><br/>' for ep in s["entrypoints"][:4]) if is_pb else f'                  <code>{ep_display}</code>'

        badge_class = "badge-pb" if is_pb else "badge-ws"
        positioning = s.get("positioning", s.get("description", ""))

        skill_cards.append(f"""
        <div class="skill-card">
          <div class="skill-card-header">
            <div class="skill-name">{s['name']}</div>
            <span class="skill-badge {badge_class}">{stype}</span>
          </div>
          <div class="skill-desc">{positioning}</div>
          <div class="skill-meta">
{chr(10).join(tags)}
          </div>
          <div class="skill-section">
            <div class="skill-section-label">目录</div>
            <div class="skill-section-value"><code>{s['directory']}</code></div>
          </div>""" +
          (f"""          <div style="margin-top:10px;display:grid;grid-template-columns:1fr 1fr;gap:12px">
            <div class="skill-section">
              <div class="skill-section-label">适用场景</div>
              <div class="skill-section-value">
                <ul>
{scenarios_li}
                </ul>
              </div>
            </div>
            <div class="skill-section">
              <div class="skill-section-label">不适用场景</div>
              <div class="skill-section-value">
                <ul>
{not_for_li}
                </ul>
              </div>
            </div>
          </div>""" if not is_pb else "") +
          f"""          <div class="skill-section" style="margin-top:10px">
            <div class="skill-section-label">入口命令</div>
            <div class="skill-section-value">
{ep_lines}
            </div>
          </div>
        </div>""")

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Mashang Workspace Skills Catalog</title>
  <link rel="stylesheet" href="../../templates/report_style.css" />
  <style>
    .skill-grid {{ display: grid; gap: 20px; margin-bottom: 32px; }}
    .skill-card {{ background: var(--zh-card); border-radius: 12px; padding: 28px 28px; box-shadow: 0 1px 4px rgba(6,33,61,.06); border: 1px solid rgba(23,74,124,.06); }}
    .skill-card:hover {{ box-shadow: 0 4px 24px rgba(6,33,61,.10); border-color: rgba(23,74,124,.15); }}
    .skill-card-header {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 12px; }}
    .skill-name {{ font-size: 20px; font-weight: 700; color: var(--zh-deep-blue); letter-spacing: .3px; }}
    .skill-badge {{ font-size: 11px; font-weight: 600; padding: 3px 12px; border-radius: 20px; white-space: nowrap; flex-shrink: 0; margin-top: 4px; }}
    .badge-ws {{ background: rgba(23,74,124,.08); color: var(--zh-blue); border: 1px solid rgba(23,74,124,.2); font-weight: 600; border-radius: 20px; padding: 2px 10px; font-size: 12px; }}
    .badge-pb {{ background: var(--zh-gold-100); color: var(--zh-gold-700); border: 1px solid rgba(215,154,54,.35); font-weight: 700; border-radius: 20px; padding: 2px 10px; font-size: 12px; }}

    .skill-desc {{ font-size: 14px; line-height: 1.7; color: var(--zh-text); margin-bottom: 12px; }}
    .skill-meta {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }}
    .skill-tag {{ font-size: 12px; color: var(--zh-muted); background: var(--zh-panel); padding: 3px 10px; border-radius: 8px; border: 1px solid var(--zh-border); }}
    .skill-tag.blue {{ color: var(--zh-blue); background: var(--zh-panel); border-color: var(--zh-border); }}
    .skill-tag.gold {{ color: var(--zh-brown); background: rgba(215,154,54,.08); border-color: rgba(215,154,54,.2); }}
    .skill-section {{ margin-bottom: 6px; }}
    .skill-section-label {{ font-size: 12px; font-weight: 600; color: var(--zh-muted); text-transform: uppercase; letter-spacing: .4px; margin-bottom: 4px; }}
    .skill-section-value {{ font-size: 13px; color: var(--zh-text); line-height: 1.6; }}
    .skill-section-value code {{ background: var(--zh-panel); padding: 1px 6px; border-radius: 4px; font-size: 12px; font-family: "SF Mono","Fira Code",monospace; }}
    .skill-section-value ul {{ list-style: none; padding: 0; }}
    .skill-section-value ul li::before {{ content: "· "; color: var(--zh-muted); }}
    .skill-section-value ul li {{ font-size: 13px; color: var(--zh-text); line-height: 1.7; }}
    .arch-section {{ margin-bottom: 32px; }}
    .arch-card {{ background: var(--zh-card); border-radius: 12px; padding: 24px 28px; box-shadow: 0 1px 4px rgba(6,33,61,.06); }}
    .arch-card h2 {{ font-size: 16px; font-weight: 600; color: var(--zh-deep-blue); margin-bottom: 12px; }}
    .arch-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
    @media (max-width: 768px) {{ .arch-grid {{ grid-template-columns: 1fr; }} }}
    .arch-item h3 {{ font-size: 14px; font-weight: 600; color: var(--zh-deep-blue); margin-bottom: 6px; }}
    .arch-item ul {{ list-style: none; padding: 0; }}
    .arch-item ul li {{ font-size: 13px; color: var(--zh-muted); line-height: 1.8; padding-left: 12px; position: relative; }}
    .arch-item ul li::before {{ content: "—"; position: absolute; left: 0; color: var(--zh-cyan); }}
    .note-card {{ background: var(--zh-panel); border-radius: 12px; padding: 16px 24px; margin-bottom: 32px; font-size: 13px; color: var(--zh-muted); line-height: 1.6; }}
    .note-card strong {{ color: var(--zh-blue); }}
  </style>
</head>
<body>

  <header>
    <div class="container">
      <div class="brand">
        <img class="brand-avatar" src="../../assets/brand/raccoon_avatar_light.png" alt="" />
        <span class="brand-name">Raccoon Research</span>
      </div>
      <span class="header-meta">workspace_skills_catalog | {TODAY}</span>
    </div>
  </header>

  <main class="container">

    <section class="hero">
      <h1>Mashang Workspace Skills Catalog</h1>
      <p>Agent Harness 能力目录 · mashang_workspace 中可被 OpenCode Agent 调用的 workspace 级 skills 清单</p>
    </section>

    <section class="kpi-grid">
      <div class="kpi-card">
        <div class="label">Workspace Skills</div>
        <div class="value">{ws_count}</div>
        <div class="change neutral">OpenCode Agent 自动匹配</div>
      </div>
      <div class="kpi-card">
        <div class="label">Promptbuilder Workflows</div>
        <div class="value">{pb_count}</div>
        <div class="change neutral">Intelligence Workflow</div>
      </div>
      <div class="kpi-card">
        <div class="label">总能力数</div>
        <div class="value">{all_count}</div>
        <div class="change neutral">{TODAY}</div>
      </div>
    </section>

    <section class="card">
      <h2>Skills Overview</h2>
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>Skill</th>
              <th>层级</th>
              <th style="min-width:360px">能力定位</th>
              <th>入口文件</th>
              <th>默认输出</th>
            </tr>
          </thead>
          <tbody>
{''.join(overview_rows)}
          </tbody>
        </table>
      </div>
    </section>

    <section>
      <h2 style="font-size:18px;font-weight:600;color:var(--zh-deep-blue);margin-bottom:16px">Workspace Skills 详情</h2>
      <div class="skill-grid">
{''.join(skill_cards)}
      </div>
    </section>

    {f'''<section>
      <h2 style="font-size:18px;font-weight:600;color:var(--zh-deep-blue);margin-bottom:16px">Promptbuilders / Intelligence Workflows</h2>
      <p style="color:var(--zh-muted);font-size:13px;margin-bottom:16px">
        Promptbuilder 是结构化 AI 提示词模块，用于执行特定情报分析任务。
        它们不是 OpenCode SKILL.md，而是可独立复制到 DeepSeek/ChatGPT 的 Prompt Pack。
      </p>
      {''.join(skill_cards[i] for i, s in enumerate(skills) if "Promptbuilder" in s.get("type", ""))}
    </section>''' if any("Promptbuilder" in s.get("type", "") for s in skills) else ''}

    <section class="arch-section">
      <h2 style="font-size:18px;font-weight:600;color:var(--zh-deep-blue);margin-bottom:16px">Agent Harness 分层说明</h2>
      <div class="arch-card">
        <div class="arch-grid">
          <div class="arch-item">
            <h3>workspace skills</h3>
            <ul>
              <li>业务场景能力</li>
{chr(10).join('              <li>' + s['name'] + ' — ' + (s.get('positioning', s.get('description', ''))[:40] if s.get('positioning', s.get('description', '')) else '') + '</li>' for s in ws_skills)}
              <li>位于 <code>mashang_workspace/.opencode/skills/</code></li>
            </ul>
          </div>
          <div class="arch-item">
            <h3>promptbuilder workflows</h3>
            <ul>
{chr(10).join('              <li>' + s['name'] + ' — ' + (s.get('description', '')[:50]) + '</li>' for s in pb_skills)}
              <li>位于 <code>mashang_workspace/promptbuilders/</code></li>
            </ul>
          </div>
          <div class="arch-item">
            <h3>workspace tools</h3>
            <ul>
              <li><code>utility_scripts/</code> — 渲染入口脚本</li>
              <li><code>templates/</code> — Jinja2 报告模板</li>
              <li><code>assets/brand/</code> — 品牌资产</li>
              <li><code>outputs/reports/</code> — 报告输出</li>
            </ul>
          </div>
        </div>
      </div>
    </section>

  </main>

  <footer>
    <img class="brand-sig" src="../../assets/brand/zihao_signature_transparent.png" alt="Raccoon Research" />
    <div class="brand-sentence">用数据、AI 和一点点常识，研究复杂世界。</div>
    <div style="font-size:11px;color:var(--zh-muted);margin-top:8px">mashang_workspace/outputs/reports/workspace_skills_catalog.html</div>
  </footer>

</body>
</html>"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    print(f"  ✓ HTML: {path}")


def main():
    print("=" * 60)
    print("  Build Workspace Skills Catalog")
    print("=" * 60)
    print()
    print(f"  Scannning: {SKILLS_DIR}")
    print()

    skills = scan_workspace_skills()
    promptbuilders = scan_promptbuilders()
    all_capabilities = skills + promptbuilders

    print(f"  Found {len(skills)} workspace skills:")
    for s in skills:
        print(f"    - {s['name']} ({s['directory']})")
    print(f"  Found {len(promptbuilders)} promptbuilder capabilities:")
    for p in promptbuilders:
        print(f"    - {p['name']} ({p['type']})")
    print()

    data_combined = build_json(all_capabilities)

    json_path = OUTPUT_DIR / "workspace_skills_catalog.json"
    md_path = OUTPUT_DIR / "workspace_skills_catalog.md"
    html_path = OUTPUT_DIR / "workspace_skills_catalog.html"

    write_json(data_combined, json_path)
    write_markdown(data_combined, all_capabilities, md_path)
    write_html(data_combined, all_capabilities, html_path)

    print()
    print("=" * 60)
    print("  Catalog generated successfully")
    print("=" * 60)
    print(f"  JSON:    {json_path}")
    print(f"  Markdown: {md_path}")
    print(f"  HTML:    {html_path}")
    print()


if __name__ == "__main__":
    main()
