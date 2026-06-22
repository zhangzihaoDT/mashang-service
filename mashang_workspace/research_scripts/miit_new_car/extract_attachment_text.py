#!/usr/bin/env python
"""
对已下载的 MIIT 批次附件进行文本抽取。

V0.3:
  - 策略化抽取（html_strip / docx_zip / textutil / antiword / catdoc / libreoffice）
  - 成功文本落盘到 extracted/text/batch_N/*.txt
  - 支持 detect extractor 环境

支持格式: .html / .htm / .txt / .docx / .doc

用法:
  python mashang_workspace/research_scripts/miit_new_car/extract_attachment_text.py --batch 408
  python mashang_workspace/research_scripts/miit_new_car/extract_attachment_text.py --batch 408 --format json
"""

import sys, json, argparse, zipfile, re, shutil, subprocess
from pathlib import Path
from html.parser import HTMLParser
from xml.parsers.expat import ParserCreate
from typing import Optional

MODULE_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = MODULE_DIR.parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from research_scripts.miit_new_car.check_text_extractors import check_extractors

RAW_BASE = WORKSPACE_ROOT / "outputs" / "miit_new_car" / "raw"
EXTRACTED_BASE = WORKSPACE_ROOT / "outputs" / "miit_new_car" / "extracted"
TEXT_DIR = EXTRACTED_BASE / "text"


def _extract_html_text(filepath: Path) -> str:
    html = filepath.read_text("utf-8", errors="replace")

    class _Parser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts: list[str] = []
            self._skip = False

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if "display:none" in a.get("style", "") or "hidden" in a.get("class", ""):
                self._skip = True

        def handle_endtag(self, tag):
            if tag in ("p", "tr", "br", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li"):
                self.parts.append("\n")
            self._skip = False

        def handle_data(self, data):
            if not self._skip:
                s = data.strip()
                if s:
                    self.parts.append(s)

    p = _Parser()
    try:
        p.feed(html)
    except Exception:
        pass
    text = " ".join(p.parts)
    text = re.sub(r"\s{3,}", "\n\n", text)
    return text.strip()


def _extract_docx_text(filepath: Path) -> str:
    try:
        with zipfile.ZipFile(filepath, "r") as z:
            if "word/document.xml" not in z.namelist():
                return ""
            xml_bytes = z.read("word/document.xml")
            xml_text = xml_bytes.decode("utf-8", errors="replace")
    except Exception as e:
        raise RuntimeError(f"docx zip 读取失败: {e}")

    texts: list[str] = []
    in_text = False
    buf = ""

    def start(name, attrs):
        nonlocal in_text, buf
        if name == "w:t":
            in_text = True
            buf = ""

    def end(name):
        nonlocal in_text, buf
        if name == "w:t" and in_text:
            texts.append(buf)
            in_text = False
        if name == "w:p":
            texts.append("\n")

    def char_data(data):
        nonlocal buf
        if in_text:
            buf += data

    try:
        parser = ParserCreate()
        parser.StartElementHandler = start
        parser.EndElementHandler = end
        parser.CharacterDataHandler = char_data
        parser.Parse(xml_text, True)
    except Exception:
        pass

    return "".join(texts).strip()


def _extract_doc_text(filepath: Path) -> tuple[str, str, str]:
    """返回 (status, method, text)。尝试所有可用 .doc 抽取器。"""
    extractor_info = check_extractors()
    preferred = extractor_info.get("preferred_doc_extractor")
    extractors = extractor_info["extractors"]

    # Ordered by preference: textutil > antiword > catdoc > libreoffice
    order = ["textutil", "antiword", "catdoc", "libreoffice"]
    if preferred and preferred in order:
        order.remove(preferred)
        order.insert(0, preferred)

    for name in order:
        info = extractors.get(name)
        if not info or not info["available"]:
            continue
        tool_path = info["path"]
        if not tool_path:
            continue

        try:
            if name == "textutil":
                result = subprocess.run(
                    [tool_path, "-stdout", "-convert", "txt", str(filepath)],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return "success", "textutil", result.stdout.strip()
            elif name == "antiword":
                result = subprocess.run(
                    [tool_path, str(filepath)],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return "success", "antiword", result.stdout.strip()
            elif name == "catdoc":
                result = subprocess.run(
                    [tool_path, str(filepath)],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return "success", "catdoc", result.stdout.strip()
            elif name == "libreoffice":
                outdir = filepath.parent / "_lo_extract"
                outdir.mkdir(exist_ok=True)
                result = subprocess.run(
                    [tool_path, "--headless", "--convert-to", "txt", "--outdir", str(outdir), str(filepath)],
                    capture_output=True, text=True, timeout=60,
                )
                if result.returncode == 0:
                    txt_file = outdir / f"{filepath.stem}.txt"
                    if txt_file.exists():
                        text = txt_file.read_text("utf-8", errors="replace").strip()
                        txt_file.unlink(missing_ok=True)
                        if text:
                            return "success", "libreoffice", text
        except Exception:
            continue

    return "unsupported", "", ""


def extract_attachment_text(
    batch_no: int,
    output_dir: Optional[Path] = None,
) -> list[dict]:
    raw_dir = RAW_BASE / f"batch_{batch_no}"
    if not raw_dir.exists():
        raise FileNotFoundError(f"批次原始数据目录不存在: {raw_dir}")

    att_dir = raw_dir / "attachments"
    if not att_dir.exists():
        return []

    batch_text_dir = TEXT_DIR / f"batch_{batch_no}"
    batch_text_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for fpath in sorted(att_dir.iterdir()):
        if not fpath.is_file():
            continue

        entry = {
            "batch_no": batch_no,
            "filename": fpath.name,
            "local_path": str(fpath),
            "extract_status": "unknown",
            "extract_method": "",
            "text_length": 0,
            "text_path": "",
            "text_preview": "",
            "error": None,
        }

        try:
            if fpath.suffix in (".html", ".htm"):
                text = _extract_html_text(fpath)
                entry["extract_status"] = "success"
                entry["extract_method"] = "html_strip"
            elif fpath.suffix == ".txt":
                text = fpath.read_text("utf-8", errors="replace").strip()
                entry["extract_status"] = "success"
                entry["extract_method"] = "txt_direct"
            elif fpath.suffix == ".docx":
                text = _extract_docx_text(fpath)
                entry["extract_method"] = "docx_zip"
                if text:
                    entry["extract_status"] = "success"
                else:
                    entry["extract_status"] = "failed"
                    entry["error"] = "docx 文本抽取返回空"
            elif fpath.suffix == ".doc":
                status, method, text = _extract_doc_text(fpath)
                entry["extract_status"] = status
                entry["extract_method"] = method or "unsupported"
                if status == "unsupported":
                    entry["error"] = f"当前环境无可用的 .doc 抽取器"
                elif status == "failed":
                    entry["error"] = "doc 抽取失败"
            else:
                entry["extract_status"] = "unsupported"
                entry["extract_method"] = "unsupported"
                entry["error"] = f"不支持的文件格式: {fpath.suffix}"
                text = ""
        except Exception as e:
            entry["extract_status"] = "failed"
            entry["extract_method"] = "error"
            entry["error"] = f"{type(e).__name__}: {e}"
            text = ""

        entry["text_length"] = len(text)
        entry["text_preview"] = text[:500]

        # Write full text to file
        if text:
            txt_dest = batch_text_dir / f"{fpath.stem}.txt"
            txt_dest.write_text(text, encoding="utf-8")
            entry["text_path"] = str(txt_dest)
        else:
            entry["text_path"] = ""

        results.append(entry)

    out_dir = output_dir or EXTRACTED_BASE
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / f"batch_{batch_no}_attachment_text.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    md_path = out_dir / f"batch_{batch_no}_attachment_text.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# 第 {batch_no} 批附件文本抽取\n\n")
        f.write(f"| 文件 | 状态 | 方法 | 文本长度 |\n|------|------|------|---------|\n")
        for r in results:
            f.write(f"| {r['filename']} | {r['extract_status']} | {r['extract_method']} | {r['text_length']} |\n")
        f.write(f"\n## 文本路径\n\n")
        for r in results:
            if r["text_path"]:
                f.write(f"- {r['filename']}: {r['text_path']}\n")

    success = sum(1 for r in results if r["extract_status"] == "success")
    unsupported = sum(1 for r in results if r["extract_status"] == "unsupported")
    failed = sum(1 for r in results if r["extract_status"] == "failed")

    extractor_info = check_extractors()
    preferred = extractor_info.get("preferred_doc_extractor") or "无"

    print(f"  JSON: {json_path}")
    print(f"  Markdown: {md_path}")
    print(f"  文本抽取: {success} 成功 / {unsupported} 不支持 / {failed} 失败")
    print(f"  extractors: {preferred}")

    return results


def main():
    p = argparse.ArgumentParser(description="提取 MIIT 批次附件的文本内容")
    p.add_argument("--batch", type=int, required=True, help="批次号")
    p.add_argument("--output-dir", type=str, help="输出目录")
    p.add_argument("--format", choices=["terminal", "json"], default="terminal")
    args = p.parse_args()

    try:
        results = extract_attachment_text(
            batch_no=args.batch,
            output_dir=Path(args.output_dir) if args.output_dir else None,
        )
    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    if args.format == "json":
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    print(f"\n[Summary] 第 {args.batch} 批附件文本抽取")
    print(f"  附件数: {len(results)}")
    for r in results:
        print(f"  {r['filename']}: {r['extract_status']} ({r['extract_method']}, {r['text_length']} chars)")


if __name__ == "__main__":
    main()
