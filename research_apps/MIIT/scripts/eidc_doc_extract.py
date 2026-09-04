#!/usr/bin/env python3
"""
MIIT EIDC doc → txt 备用提取器（textutil 无法处理超大 .doc 时使用）

原理：读取 OLE WordDocument 流，按 FIB (File Information Block) 的 fcMin/fcMac
精确切出文本区（UTF-16LE），还原 \x07 表格分隔。

适用：textutil 报 "isn't in the correct format" 的超大 WPS .doc（如 32MB 完整目录）。

用法:
  python3 scripts/eidc_doc_extract.py --input a.doc --output a.txt
"""
import argparse
import struct
from pathlib import Path

import olefile


def doc_to_txt_ole(doc_path: Path) -> str:
    """从 .doc 提取纯文本（含 \x07 表格分隔），供 04/05 parser 消费。"""
    ole = olefile.OleFileIO(str(doc_path))
    try:
        data = ole.openstream("WordDocument").read()
    finally:
        ole.close()
    fcMin = struct.unpack("<I", data[0x18:0x1C])[0]
    fcMac = struct.unpack("<I", data[0x1C:0x20])[0]
    if fcMac <= fcMin:
        raise ValueError(f"fcMac({fcMac}) <= fcMin({fcMin})，无法提取文本区")
    text_zone = data[fcMin:fcMac]
    text = text_zone.decode("utf-16le", errors="ignore")
    # 归一化换行
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def main():
    parser = argparse.ArgumentParser(description="EIDC doc → txt 备用提取器（olefile FIB）")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    text = doc_to_txt_ole(Path(args.input))
    Path(args.output).write_text(text, encoding="utf-8")
    print(f"提取 {len(text)} chars → {args.output}")


if __name__ == "__main__":
    main()