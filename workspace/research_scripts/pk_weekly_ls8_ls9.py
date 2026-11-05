#!/usr/bin/env python3
"""兼容 shim：``pk_weekly_ls8_ls9`` → ``pk_weekly_compare``。

保留旧入口与旧默认（series = LS8 LS9，输出 ``pk_weekly_compare_ls8_ls9.html``）。
新功能（显式 ``--weeks``、任意车型、``--format json`` 等）一律走
``research_scripts/pk_weekly_compare.py``。
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from research_scripts.pk_weekly_compare import main as _main  # noqa: E402

_DEFAULT_HTML = _ROOT / "outputs" / "reports" / "pk_weekly_compare_ls8_ls9.html"


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not any(a == "--series" or a.startswith("--series=") for a in argv):
        argv += ["--series", "LS8", "LS9"]
    if not any(
        a == "--html-out" or a.startswith("--html-out=")
        or a == "--output" or a.startswith("--output=")
        or a == "--format" or a.startswith("--format=")
        for a in argv
    ):
        argv += ["--html-out", str(_DEFAULT_HTML)]
    _main(argv)


if __name__ == "__main__":
    main()
