#!/usr/bin/env python
"""
Compatibility entrypoint for legacy Mashang Feishu bot.

The real legacy bot entrypoint lives at:
    mashang_runtime/feishu_bot.py

New development should use:
    mashang_workspace/
    mashang_runtime_v2/
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
RUNTIME_ROOT = PROJECT_ROOT / "mashang_runtime"

for p in [str(PROJECT_ROOT), str(RUNTIME_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

if __name__ == "__main__":
    runpy.run_path(str(RUNTIME_ROOT / "feishu_bot.py"), run_name="__main__")
