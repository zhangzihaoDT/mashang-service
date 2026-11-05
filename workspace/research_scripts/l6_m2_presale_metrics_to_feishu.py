#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""[DEPRECATED] DM2 预售监控兼容入口。

通用实现已迁移到 research_scripts/presale_metrics_to_feishu.py：
    python research_scripts/presale_metrics_to_feishu.py --series CM3

本文件保留仅为兼容旧调用（默认 --series DM2）。
"""

from __future__ import annotations

import sys
from pathlib import Path

_WS_ROOT = Path(__file__).resolve().parents[1]
if str(_WS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WS_ROOT))

from research_scripts.presale_metrics_to_feishu import main as _main  # noqa: E402


def main() -> int:
    if "--series" not in sys.argv:
        sys.argv += ["--series", "DM2"]
    return _main()


if __name__ == "__main__":
    raise SystemExit(main())
