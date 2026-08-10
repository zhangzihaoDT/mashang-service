#!/usr/bin/env python
"""
render_official_document.py — 正式材料排版渲染脚本

将 Markdown 文档转换为正式通知/申报材料风格的 Word/PDF/HTML。

用法:
    python scripts/render_official_document.py \\
        --input path/to/doc.md \\
        --output-dir outputs/submission \\
        --basename 项目申报书_示例 \\
        --formats html,pdf,docx
"""

import sys, os, re, argparse, json, subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

SKILL_DIR = _REPO_ROOT / ".opencode" / "skills" / "official_document_render"
TEMPLATE_DIR = SKILL_DIR / "templates"
CSS_PATH = TEMPLATE_DIR / "official_print.css"
OUTPUTS_DIR = _REPO_ROOT / "outputs"

APPLICANT = os.environ.get("APPLICANT_NAME", "")


def parse_args():
    p = argparse.ArgumentParser(description="正式材料排版渲染 Skill")
    p.add_argument("--input", required=True, help="输入 Markdown 文件路径")
    p.add_argument("--output-dir", default=str(OUTPUTS_DIR / "submission"), help="输出目录")
    p.add_argument("--basename", default="document", help="输出文件基础名（不含后缀）")
    p.add_argument("--formats", default="html", help="输出格式，逗号分隔: html,pdf,docx")
    p.add_argument("--title", default="", help="可选，覆盖文档标题")
    p.add_argument("--insert-architecture", default="", help="可选架构图路径")
    p.add_argument("--max-pdf-mb", type=int, default=5, help="PDF 文件大小上限 MB")
    return p.parse_args()


def check_dependencies() -> dict:
    deps = {"pandoc": False, "weasyprint": False, "pillow": False}
    try:
        r = subprocess.run(["pandoc", "--version"], capture_output=True, text=True, timeout=10)
        deps["pandoc"] = r.returncode == 0
    except Exception:
        pass
    try:
        from weasyprint import HTML
        deps["weasyprint"] = True
    except Exception:
        pass
    try:
        from PIL import Image
        deps["pillow"] = True
    except Exception:
        pass
    return deps


def md_to_html(md_text: str, title: str = "", architecture_path: str = "") -> str:
    """Convert markdown to structured HTML with formal document CSS."""
    lines = md_text.split("\n")
    html_parts = []
    in_code_block = False
    in_list = False
    list_type = None
    after_title_heading = False
    has_info_block = False

    def start_list(typ):
        nonlocal in_list, list_type
        if not in_list:
            html_parts.append(f"<{typ}>")
            in_list = True
            list_type = typ

    def end_list():
        nonlocal in_list, list_type
        if in_list:
            html_parts.append(f"</{list_type}>")
            in_list = False
            list_type = None

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            end_list()
            if in_code_block:
                html_parts.append("</pre>")
                in_code_block = False
            else:
                html_parts.append("<pre>")
                in_code_block = True
            continue
        if in_code_block:
            html_parts.append(line)
            continue
        if not stripped:
            end_list()
            continue

        # Image
        img_match = re.match(r"!\[(.*?)\]\((.*?)\)", stripped)
        if img_match:
            end_list()
            alt, src = img_match.group(1), img_match.group(2)
            html_parts.append(
                f'<div class="figure"><img src="{src}" alt="{alt}" '
                f'style="max-width:90%;height:auto" />'
                f'<div class="fig-caption">{alt}</div></div>'
            )
            continue

        # Headings
        h_match = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        if h_match:
            end_list()
            level, text = len(h_match.group(1)), h_match.group(2)
            if level == 1 and "申报书" in text:
                continue
            if "项目名称" in text:
                after_title_heading = True
                has_info_block = True
                continue
            if level == 2 and "申报赛道" in text:
                has_info_block = True
                continue
            if level == 2:
                html_parts.append(f'<h2 class="section">{text}</h2>')
                continue
            if level == 3:
                html_parts.append(f"<h3>{text}</h3>")
                continue
            html_parts.append(f"<h{level}>{text}</h{level}>")
            continue

        # After title heading
        if after_title_heading:
            after_title_heading = False
            doc_title = title or stripped
            html_parts.append(f'<h1 class="doc-title">{doc_title}</h1>')
            continue

        if stripped == "大数据与智能化":
            continue

        if stripped.startswith("- "):
            start_list("ul")
            html_parts.append(f"<li>{stripped[2:]}</li>")
            continue
        if re.match(r"^\d+\.\s", stripped):
            start_list("ol")
            content = re.sub(r"^\d+\.\s+", "", stripped)
            html_parts.append(f"<li>{content}</li>")
            continue
        end_list()
        html_parts.append(f"<p>{stripped}</p>")

    end_list()
    body_html = "\n".join(html_parts)

    # Read CSS
    css_text = ""
    if CSS_PATH.exists():
        css_text = CSS_PATH.read_text(encoding="utf-8")

    # Build info block
    info_block = ""
    if has_info_block:
        info_entries = []
        if title:
            info_entries.append(f"<p><strong>项目名称：</strong>{title}</p>")
        if "大数据与智能化" in md_text:
            info_entries.append("<p><strong>申报赛道：</strong>大数据与智能化</p>")
        if APPLICANT:
            info_entries.append(f"<p><strong>申报人：</strong>{APPLICANT}</p>")
        if info_entries:
            info_block = '<div class="info-block">\n' + "\n".join(info_entries) + "\n</div>"

    # Architecture image
    arch_html = ""
    if architecture_path:
        arch_path = Path(architecture_path)
        if arch_path.exists():
            arch_html = (
                f'<div class="figure">'
                f'<img src="{arch_path}" alt="系统架构图" style="max-width:90%;height:auto" />'
                f'<div class="fig-caption">系统架构图</div></div>'
            )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title or "正式材料"}</title>
<style>
{css_text}
</style>
</head>
<body>
{info_block}
{body_html}
{arch_html}
</body>
</html>"""


def generate_html(md_text: str, output_path: Path, title: str, arch_path: str) -> bool:
    html_content = md_to_html(md_text, title=title, architecture_path=arch_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_content, encoding="utf-8")
    return True


def generate_pdf(html_path: Path, output_path: Path, max_mb: int) -> bool:
    try:
        from weasyprint import HTML
        doc = HTML(filename=str(html_path))
        doc.write_pdf(str(output_path))
        size_mb = output_path.stat().st_size / (1024 * 1024)
        if size_mb > max_mb:
            print(f"  ⚠ PDF size {size_mb:.1f} MB exceeds {max_mb} MB limit")
        return True
    except Exception as e:
        print(f"  ✗ PDF generation failed: {e}")
        return False


def generate_docx(md_source: Path, output_path: Path) -> bool:
    try:
        r = subprocess.run(
            ["pandoc", str(md_source), "-o", str(output_path), "--from", "markdown"],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode == 0:
            return True
        else:
            print(f"  ✗ pandoc error: {r.stderr[:200]}")
            return False
    except FileNotFoundError:
        print("  ✗ pandoc not found, DOCX generation skipped")
        return False
    except Exception as e:
        print(f"  ✗ DOCX generation failed: {e}")
        return False


def main():
    args = parse_args()
    md_path = Path(args.input)
    out_dir = Path(args.output_dir)
    basename = args.basename
    title = args.title
    arch_path = args.insert_architecture
    formats = [f.strip() for f in args.formats.split(",")]
    max_mb = args.max_pdf_mb

    # Validate input
    if not md_path.exists():
        print(f"[Error] Input not found: {md_path}")
        sys.exit(1)

    md_text = md_path.read_text(encoding="utf-8")
    if not title:
        for line in md_text.split("\n"):
            if line.startswith("# ") and "申报书" not in line and "申报" not in line:
                title = line.lstrip("# ").strip()
                break
        if not title:
            title = basename

    # Detect dependencies
    deps = check_dependencies()
    print(f"  Dependencies: pandoc={'✓' if deps['pandoc'] else '✗'}, "
          f"weasyprint={'✓' if deps['weasyprint'] else '✗'}, "
          f"Pillow={'✓' if deps['pillow'] else '✗'}")

    out_dir.mkdir(parents=True, exist_ok=True)
    results = {}

    # ── Generate HTML (always) ──
    html_path = out_dir / f"{basename}.html"
    if generate_html(md_text, html_path, title, arch_path):
        results["html"] = html_path
        print(f"  ✓ HTML: {html_path}")

    # ── Generate PDF ──
    if "pdf" in formats:
        pdf_path = out_dir / f"{basename}.pdf"
        if deps["weasyprint"] and html_path.exists():
            if generate_pdf(html_path, pdf_path, max_mb):
                results["pdf"] = pdf_path
                size_mb = pdf_path.stat().st_size / (1024 * 1024)
                print(f"  ✓ PDF:  {pdf_path} ({size_mb:.1f} MB)")
        else:
            print("  ✗ PDF: skipped (weasyprint unavailable)")

    # ── Generate DOCX ──
    if "docx" in formats:
        docx_path = out_dir / f"{basename}.docx"
        if deps["pandoc"]:
            if generate_docx(md_path, docx_path):
                results["docx"] = docx_path
                size_kb = docx_path.stat().st_size / 1024
                print(f"  ✓ DOCX: {docx_path} ({size_kb:.0f} KB)")
        else:
            print("  ✗ DOCX: skipped (pandoc unavailable)")

    # ── Summary ──
    print()
    print("=" * 60)
    print("  Render Summary")
    print("=" * 60)
    for fmt, path in results.items():
        size = path.stat().st_size
        if size > 1024 * 1024:
            size_str = f"{size / 1024 / 1024:.1f} MB"
        else:
            size_str = f"{size / 1024:.0f} KB"
        print(f"  {fmt.upper():4s}: {path} ({size_str})")
    print(f"  Input: {md_path}")
    print(f"  Title: {title}")
    print()


if __name__ == "__main__":
    main()
