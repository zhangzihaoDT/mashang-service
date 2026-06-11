#!/usr/bin/env python
"""
锁单释放曲线分析 — 包装 lock_release_curve.py

用法:
    python scripts/release_curve_analysis.py                                    # 默认全量分析
    python scripts/release_curve_analysis.py --format html --output outputs/reports/
    python scripts/release_curve_analysis.py --series LS8                       # 暂不支持

说明: 此脚本包装 lock_release_curve.py（~700 行分析逻辑），提供统一 CLI 接口。
      lock_release_curve.py 本身基于全量 order_data，不支持 series/city 等过滤。
"""

import sys
import argparse
import subprocess
from pathlib import Path

_WS_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = _WS_ROOT.parent


def parse_args():
    parser = argparse.ArgumentParser(description="锁单释放曲线分析 (Release Curve)")
    parser.add_argument("--date", type=str, help="此脚本忽略 date 参数")
    parser.add_argument("--start-date", type=str, help="此脚本忽略 start-date 参数")
    parser.add_argument("--end-date", type=str, help="此脚本忽略 end-date 参数")
    parser.add_argument("--series", type=str, help="此脚本忽略 series 参数 (基于全量订单)")
    parser.add_argument("--model", type=str, help="此脚本忽略 model 参数")
    parser.add_argument("--city", type=str, help="此脚本忽略 city 参数")
    parser.add_argument("--output", type=str, default=str(REPO_ROOT / "outputs" / "reports"),
                        help="报告输出目录 (默认 outputs/reports/)")
    parser.add_argument("--format", type=str, default="html", choices=["html", "terminal"],
                        help="输出格式 (默认 html，terminal 仅打印摘要)")
    parser.add_argument("--limit", type=int, default=0, help="此脚本忽略 limit 参数")
    return parser.parse_args()


def main():
    args = parse_args()
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_html = out_dir / "release_curve_analysis.html"

    print("[Summary]")
    print(f"  锁单释放曲线分析")
    print()
    print("[Scope]")
    print(f"  数据源: dataset/order_data.parquet")
    print(f"  分析窗口: first_assign_time → lock_time 的 day_after (0~60d)")
    print(f"  指标口径: cumulative lock rate by assign_date cohort")
    print()

    # 通过子进程调用原脚本，避免模块级代码冲突
    script_path = REPO_ROOT / "scripts" / "lock_release_curve.py"
    env = dict(__import__("os").environ)
    env["OUTPUT_HTML"] = str(out_html)

    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=False, text=True, timeout=600,
        env=env,
    )

    print()
    print("[Output]")
    print(f"  HTML: {out_html}")

    if args.format == "terminal":
        print()
        print("[Result] (请查看 HTML 报告获取完整图表)")
        print(f"  报告文件: {out_html}")


if __name__ == "__main__":
    main()
