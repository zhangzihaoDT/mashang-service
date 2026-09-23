#!/usr/bin/env python
"""预售小订监控（飞书）— compatibility shim。

已收敛到唯一入口 `runtime_scripts/vehicle_sales_monitor.py`：
    python runtime_scripts/vehicle_sales_monitor.py --series CM3 --force-phase --phase presale

`--force-phase` 让监控忽略 active 窗口判定，按指定 phase 渲染显式 series，
因此「代际已进入 launch 后仍要发预售快照」无需独立实现。

本文件保留仅为兼容旧调用；缺省 `--series` 取当前 presale 代际。

用法:
    python research_scripts/presale_metrics_to_feishu.py --series CM3
    python research_scripts/presale_metrics_to_feishu.py --series CM3 --dry-run
    python research_scripts/presale_metrics_to_feishu.py                 # 默认当前 presale 代际
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
_WS_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(REPO_ROOT), str(_WS_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils.monitors.phase import detect_active, load_business_definition  # noqa: E402

_VSM_PATH = _WS_ROOT / "runtime_scripts" / "vehicle_sales_monitor.py"


def _next_value(argv: list[str], flag: str) -> str | None:
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def _inject(argv: list[str]) -> list[str] | None:
    """补齐 --force-phase / --phase presale，并在缺省时解析当前 presale 代际。"""
    if "--force-phase" not in argv:
        argv.append("--force-phase")
    if "--phase" not in argv:
        argv += ["--phase", "presale"]
    if "--series" not in argv:
        bdef = load_business_definition()
        as_of = _next_value(argv, "--as-of")
        today = pd.Timestamp(as_of) if as_of else pd.Timestamp.now().normalize()
        active = detect_active(bdef, today, phases=("presale",))
        if not active:
            print(f"⚠️ {today.date()} 无 presale 代际")
            return None
        argv += ["--series", active[0]["generation"]]
    return argv


def _load_runner():
    spec = importlib.util.spec_from_file_location("vehicle_sales_monitor", _VSM_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {_VSM_PATH}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    argv = _inject([a for a in sys.argv[1:]])
    if argv is None:
        return 0
    runner = _load_runner()
    sys.argv = [sys.argv[0]] + argv
    return runner.main()


if __name__ == "__main__":
    raise SystemExit(main())
