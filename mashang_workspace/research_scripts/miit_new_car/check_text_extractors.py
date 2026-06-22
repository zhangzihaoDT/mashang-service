#!/usr/bin/env python
"""
检测当前环境可用的文本抽取工具。

用法:
  python check_text_extractors.py
  python check_text_extractors.py --format json
"""

import sys, json, argparse, shutil
from pathlib import Path

EXTRACTOR_DEFS = {
    "textutil": {
        "paths": ["/usr/bin/textutil"],
        "supports": [".doc", ".docx", ".rtf", ".html"],
        "platforms": ["darwin"],
    },
    "antiword": {
        "paths": None,
        "supports": [".doc"],
        "platforms": ["linux", "darwin"],
    },
    "catdoc": {
        "paths": None,
        "supports": [".doc"],
        "platforms": ["linux", "darwin"],
    },
    "libreoffice": {
        "paths": None,
        "supports": [".doc", ".docx"],
        "platforms": ["linux", "darwin"],
    },
}


def check_extractors() -> dict:
    import platform as _platform
    results = {}
    preferred_doc = None
    preferred_priority = 99

    for name, cfg in EXTRACTOR_DEFS.items():
        path = None
        if cfg["paths"]:
            for p in cfg["paths"]:
                if Path(p).exists():
                    path = p
                    break
        if path is None:
            found = shutil.which(name)
            if found:
                path = found

        available = path is not None
        results[name] = {
            "available": available,
            "path": path,
            "supports": cfg["supports"],
        }

        if available and ".doc" in cfg["supports"]:
            prio = {"textutil": 1, "antiword": 2, "catdoc": 3, "libreoffice": 4}.get(name, 99)
            if prio < preferred_priority:
                preferred_doc = name
                preferred_priority = prio

    return {
        "platform": _platform.system().lower(),
        "extractors": results,
        "preferred_doc_extractor": preferred_doc,
    }


def main():
    p = argparse.ArgumentParser(description="检测 MIIT 附件文本抽取工具")
    p.add_argument("--format", choices=["terminal", "json"], default="terminal")
    args = p.parse_args()

    info = check_extractors()

    if args.format == "json":
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return

    print(f"\n[Summary] 文本抽取环境检测")
    print(f"  平台: {info['platform']}")
    print(f"  首选 .doc 抽取器: {info.get('preferred_doc_extractor', '无')}")
    print()
    for name, e in info["extractors"].items():
        status = "✓" if e["available"] else "✗"
        path = e["path"] or "-"
        supports = ", ".join(e["supports"])
        print(f"  {status} {name}: {path}")
        print(f"     支持: {supports}")


if __name__ == "__main__":
    main()
