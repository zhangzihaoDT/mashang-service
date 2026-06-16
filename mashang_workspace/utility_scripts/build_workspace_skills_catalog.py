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


def build_json(skills: list[dict]) -> dict:
    return {
        "workspace": "mashang_workspace",
        "generated_at": TODAY,
        "skills": skills,
        "repo_level_skills_note": [
            {
                "name": "official-document-render",
                "directory": "../.opencode/skills/official_document_render/",
                "level": "repo",
                "description": "通用正式材料 Word/PDF/HTML 渲染能力，不计入 workspace skills。用于项目申报书、比赛材料、政府/机构申报附件等正式材料排版。",
            }
        ],
    }


def write_json(data: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  ✓ JSON: {path}")


def write_markdown(data: dict, skills: list[dict], path: Path):
    ws_count = len(skills)
    repo_count = len(data["repo_level_skills_note"])

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
        f"| Repo-Level Skills | {repo_count} |",
        "| Skills 输出目录 | outputs/reports/ |",
        f"| 最近更新 | {TODAY} |",
        "",
        "## Skills Overview",
        "",
        "| Skill | 层级 | 能力定位 | 入口文件 | 默认输出 |",
        "|-------|------|---------|---------|---------|",
    ]

    for s in skills:
        ep = s["entrypoints"][0] if s["entrypoints"] else "—"
        out = s["outputs"][0] if s["outputs"] else "—"
        lines.append(f"| {s['name']} | workspace | {s['positioning'][:40] if s['positioning'] else s['description'][:40]} | `{ep}` | {out} |")

    rn = data["repo_level_skills_note"][0]
    lines.append(f"| {rn['name']} | repo | {rn['description'][:40]} | `scripts/render_official_document.py` | outputs/submission/ |")

    lines += [
        "",
        "## Workspace Skills 详情",
        "",
    ]

    for s in skills:
        lines += [
            f"### {s['name']}",
            "",
            "| 字段 | 内容 |",
            "|------|------|",
            f"| 目录 | `{s['directory']}` |",
            "| 层级 | workspace |",
            f"| 能力定位 | {s['positioning'] or s['description']} |",
            f"| 适用场景 | {'、'.join(s['scenarios'][:6]) if s['scenarios'] else '—'} |",
            f"| 不适用场景 | {'、'.join(s['not_for'][:4]) if s['not_for'] else '—'} |",
            f"| 入口命令 | `{s['entrypoints'][0] if s['entrypoints'] else '—'}` |",
            f"| 默认输出 | {s['outputs'][0] if s['outputs'] else '—'} |",
            "",
        ]

    lines += [
        "## Agent Harness 分层说明",
        "",
        "### repo root skills",
        "- 通用生产能力",
        "- official-document-render — Markdown → Word/PDF/HTML 正式材料",
        "- 位于 `.opencode/skills/official_document_render/`",
        "",
        "### workspace skills",
        "- 业务场景能力",
    ]
    for s in skills:
        lines.append(f"- {s['name']} — {s['positioning'][:40] if s['positioning'] else s['description'][:40]}")
    lines += [
        f"- 位于 `mashang_workspace/.opencode/skills/`",
        "",
        "### workspace tools",
        "- utility_scripts/ — 渲染入口脚本",
        "- templates/ — Jinja2 报告模板",
        "- assets/brand/ — 品牌资产",
        "- outputs/reports/ — 报告输出",
        "",
        "### repo root tools",
        "- scripts/render_official_document.py",
        "- scripts/smoke_test_official_document_render.py",
        "- skills/official_document_render/",
        "",
        "---",
        "",
        "> 说明：repo root 的 official-document-render 是通用正式材料渲染能力（Word/PDF/HTML），不归入 workspace skills。本文件仅盘点 mashang_workspace 下的 workspace 级 skills。",
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
    ws_count = len(skills)
    repo_count = len(data["repo_level_skills_note"])
    rn = data["repo_level_skills_note"][0]

    skill_names_joined = " + ".join(s["name"] for s in skills)
    output_dirs = ", ".join(set(s["outputs"][0] for s in skills if s["outputs"]))

    # Build overview table rows
    overview_rows = []
    for s in skills:
        ep = _ep_display(s["entrypoints"][0]) if s["entrypoints"] else "—"
        out = s["outputs"][0] if s["outputs"] else "—"
        overview_rows.append(f"""
            <tr>
              <td><strong>{s['name']}</strong></td>
              <td><span class="badge blue">workspace</span></td>
              <td>{s['positioning'][:40] if s['positioning'] else s['description'][:40]}</td>
              <td><code>{ep}</code></td>
              <td><code>{out}</code></td>
            </tr>""")

    overview_rows.append(f"""
            <tr class="row-highlight">
              <td><strong>{rn['name']}</strong></td>
              <td><span class="badge gold">repo</span></td>
              <td>{rn['description'][:40]}</td>
              <td><code>scripts/render_official_document.py</code></td>
              <td><code>outputs/submission/</code></td>
            </tr>""")

    # Build skill cards
    skill_cards = []
    for s in skills:
        tags = []
        for word in ["HTML", "品牌", "Jinja2", "Eval", "诊断", "Runtime", "报告", "模板", "预测", "回测", "质量保障", "Raccoon Research"]:
            if word in s["description"] or any(word in sc for sc in s["scenarios"]):
                css = "gold" if word in ("预测", "回测", "质量保障") else "blue"
                tags.append(f'            <span class="skill-tag {css}">{word}</span>')

        scenarios_li = "\n".join(f"                  <li>{sc}</li>" for sc in s["scenarios"][:8])
        not_for_li = "\n".join(f"                  <li>{nf}</li>" for nf in s["not_for"][:6])

        ep_display = _ep_display(s["entrypoints"][0]) if s["entrypoints"] else "—"

        skill_cards.append(f"""
        <div class="skill-card">
          <div class="skill-card-header">
            <div class="skill-name">{s['name']}</div>
            <span class="skill-badge badge-ws">workspace</span>
          </div>
          <div class="skill-desc">{s['positioning'] or s['description']}</div>
          <div class="skill-meta">
{chr(10).join(tags)}
          </div>
          <div class="skill-section">
            <div class="skill-section-label">目录</div>
            <div class="skill-section-value"><code>{s['directory']}</code></div>
          </div>
          <div style="margin-top:10px;display:grid;grid-template-columns:1fr 1fr;gap:12px">
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
          </div>
          <div class="skill-section" style="margin-top:10px">
            <div class="skill-section-label">入口命令</div>
            <div class="skill-section-value">
              <code>{ep_display}</code>
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
    .badge-ws {{ background: var(--zh-light-blue); color: var(--zh-blue); }}
    .badge-repo {{ background: rgba(215,154,54,.12); color: var(--zh-brown); }}
    .skill-desc {{ font-size: 14px; line-height: 1.7; color: var(--zh-text); margin-bottom: 12px; }}
    .skill-meta {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }}
    .skill-tag {{ font-size: 12px; color: var(--zh-muted); background: var(--zh-cream); padding: 3px 10px; border-radius: 8px; border: 1px solid rgba(107,124,143,.12); }}
    .skill-tag.blue {{ color: var(--zh-blue); background: var(--zh-light-blue); border-color: rgba(126,205,235,.25); }}
    .skill-tag.gold {{ color: var(--zh-brown); background: rgba(215,154,54,.08); border-color: rgba(215,154,54,.2); }}
    .skill-section {{ margin-bottom: 6px; }}
    .skill-section-label {{ font-size: 12px; font-weight: 600; color: var(--zh-muted); text-transform: uppercase; letter-spacing: .4px; margin-bottom: 4px; }}
    .skill-section-value {{ font-size: 13px; color: var(--zh-text); line-height: 1.6; }}
    .skill-section-value code {{ background: var(--zh-cream); padding: 1px 6px; border-radius: 4px; font-size: 12px; font-family: "SF Mono","Fira Code",monospace; }}
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
    .note-card {{ background: var(--zh-light-blue); border-radius: 12px; padding: 16px 24px; margin-bottom: 32px; font-size: 13px; color: var(--zh-muted); line-height: 1.6; }}
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
        <div class="change neutral">{skill_names_joined}</div>
      </div>
      <div class="kpi-card">
        <div class="label">Repo-Level Skills</div>
        <div class="value">{repo_count}</div>
        <div class="change neutral">official-document-render</div>
      </div>
      <div class="kpi-card">
        <div class="label">Skills 输出目录</div>
        <div class="value" style="font-size:18px;line-height:1.4">{output_dirs}</div>
        <div class="change neutral">品牌化 HTML 数据报告</div>
      </div>
      <div class="kpi-card">
        <div class="label">最近更新</div>
        <div class="value">{TODAY}</div>
        <div class="change neutral">自动生成</div>
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
              <th>能力定位</th>
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

    <section class="arch-section">
      <h2 style="font-size:18px;font-weight:600;color:var(--zh-deep-blue);margin-bottom:16px">Agent Harness 分层说明</h2>
      <div class="arch-card">
        <div class="arch-grid">
          <div class="arch-item">
            <h3>repo root skills</h3>
            <ul>
              <li>通用生产能力</li>
              <li>official-document-render — Markdown → Word/PDF/HTML 正式材料</li>
              <li>位于 <code>.opencode/skills/official_document_render/</code></li>
            </ul>
          </div>
          <div class="arch-item">
            <h3>workspace skills</h3>
            <ul>
              <li>业务场景能力</li>
{chr(10).join('              <li>' + s['name'] + ' — ' + (s['positioning'][:40] if s['positioning'] else s['description'][:40]) + '</li>' for s in skills)}
              <li>位于 <code>mashang_workspace/.opencode/skills/</code></li>
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
          <div class="arch-item">
            <h3>repo root tools</h3>
            <ul>
              <li><code>scripts/render_official_document.py</code></li>
              <li><code>scripts/smoke_test_official_document_render.py</code></li>
              <li><code>skills/official_document_render/</code></li>
            </ul>
          </div>
        </div>
      </div>
    </section>

    <div class="note-card">
      <strong>说明：</strong>repo root 的 <code>official-document-render</code> 是通用正式材料渲染能力（Word/PDF/HTML），不归入 workspace skills。本页面仅盘点 <code>mashang_workspace</code> 下的 workspace 级 skills。
    </div>

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
    print(f"  Found {len(skills)} workspace skills:")
    for s in skills:
        print(f"    - {s['name']} ({s['directory']})")
    print()

    data = build_json(skills)

    json_path = OUTPUT_DIR / "workspace_skills_catalog.json"
    md_path = OUTPUT_DIR / "workspace_skills_catalog.md"
    html_path = OUTPUT_DIR / "workspace_skills_catalog.html"

    write_json(data, json_path)
    write_markdown(data, skills, md_path)
    write_html(data, skills, html_path)

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
