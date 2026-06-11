#!/usr/bin/env python
"""
VOC 主题分析 — 微信群聊情感/主题挖掘

用法:
    python scripts/voc_theme_analysis.py                                         # 默认分析销售全员群
    python scripts/voc_theme_analysis.py --model "LS8"                           # 消息内容含 "LS8"
    python scripts/voc_theme_analysis.py --start-date 2026-05-01 --end-date 2026-06-01
    python scripts/voc_theme_analysis.py --format csv --output outputs/tables/

说明: 此脚本为 VOC 分析骨架。当前阶段读取微信群聊数据并输出基础统计。
      后续可集成 NLP/JTBD 分类模块。
"""

import sys
import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
_WS_ROOT = Path(__file__).resolve().parents[1]
if str(_WS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WS_ROOT))

import pandas as pd
from datetime import datetime, timedelta

WECHAT_DIR = REPO_ROOT / "dataset" / "wechat"


def parse_args():
    parser = argparse.ArgumentParser(description="VOC 主题分析")
    parser.add_argument("--date", type=str, help="单日查询 (YYYY-MM-DD)")
    parser.add_argument("--start-date", type=str, help="开始日期 (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="结束日期 (YYYY-MM-DD)")
    parser.add_argument("--series", type=str, help="消息内容包含的车系关键词")
    parser.add_argument("--model", type=str, help="消息内容包含的车型关键词")
    parser.add_argument("--city", type=str, help="此脚本忽略 city 参数")
    parser.add_argument("--output", type=str, help="输出目录 (默认 outputs/tables/)")
    parser.add_argument("--format", type=str, default="terminal", choices=["terminal", "csv", "json"],
                        help="输出格式 (默认 terminal)")
    parser.add_argument("--limit", type=int, default=20, help="返回 TopN 关键词 (默认 20)")
    parser.add_argument("--group", type=str, default="销售全员群", help="群聊名称 (默认: 销售全员群)")
    return parser.parse_args()


def resolve_time_range(args):
    if args.date:
        d = pd.Timestamp(args.date)
        return d, d + timedelta(days=1), args.date
    if args.start_date and args.end_date:
        s, e = pd.Timestamp(args.start_date), pd.Timestamp(args.end_date)
        return s, e, f"{args.start_date}~{args.end_date}"
    yesterday = datetime.now() - timedelta(days=1)
    d = pd.Timestamp(yesterday.date())
    return d, d + timedelta(days=1), yesterday.strftime("%Y-%m-%d")


def main():
    args = parse_args()
    t_start, t_end, t_label = resolve_time_range(args)

    group_file = WECHAT_DIR / f"{args.group}.parquet"
    if not group_file.exists():
        print(f"[Error] 未找到群聊数据: {group_file}")
        avail = list(WECHAT_DIR.glob("*.parquet"))
        if avail:
            print(f"  可用的群聊文件: {avail}")
        return

    df = pd.read_parquet(str(group_file))
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    filtered = df[df["timestamp"].notna()].copy()

    mask = (filtered["timestamp"] >= t_start) & (filtered["timestamp"] < t_end)
    filtered = filtered[mask]

    if args.series:
        filtered = filtered[filtered["content"].str.contains(args.series, na=False)]
    if args.model:
        filtered = filtered[filtered["content"].str.contains(args.model, na=False)]

    total_msgs = len(filtered)

    # ── 简单词频统计 (骨架) ──
    keyword_counts = pd.Series(dtype=int)
    if total_msgs > 0:
        content_series = filtered["content"].dropna().astype(str)
        words = content_series.str.findall(r"[\w\u4e00-\u9fff]+")
        all_words = [w for sublist in words for w in sublist]
        word_series = pd.Series(all_words)
        # 过滤短词、标点
        word_series = word_series[word_series.str.len() >= 2]
        keyword_counts = word_series.value_counts().head(args.limit)

    # ── 统一输出 ──
    print("[Summary]")
    print(f"  群聊: {args.group}")
    print(f"  消息数: {total_msgs}")
    print()
    print("[Scope]")
    print(f"  数据源: {group_file}")
    print(f"  时间窗口: {t_label}")
    print(f"  关键词过滤 (series/model): {args.series or '-'} / {args.model or '-'}")
    print()
    print("[Result]")
    if total_msgs > 0 and len(keyword_counts) > 0:
        print(f"  {'关键词':20s} {'出现次数':>8s}")
        print(f"  {'-'*20} {'-'*8}")
        for word, count in keyword_counts.items():
            print(f"  {str(word):20s} {count:8d}")
    else:
        print("  (当前为 VOC 骨架，尚未集成 NLP/JTBD 分类)")
        print("  待建设能力:")
        print("    1. 关键词/主题提取")
        print("    2. JTBD 分类 (Jobs To Be Done)")
        print("    3. 情感分析")
        print("    4. 趋势变化检测")

    if args.format == "csv" or (args.output and args.format == "terminal"):
        out_dir = Path(args.output) if args.output else REPO_ROOT / "outputs" / "tables"
        out_dir.mkdir(parents=True, exist_ok=True)
        if len(keyword_counts) > 0:
            kdf = keyword_counts.reset_index()
            kdf.columns = ["keyword", "count"]
            fname = f"{t_label}_voc_keywords_{args.group}.csv"
            kdf.to_csv(out_dir / fname, index=False)
            print()
            print("[Output]")
            print(f"  CSV: {out_dir / fname}")
        else:
            print()
            print("[Output]")
            print(f"  输出目录: {out_dir}")

    if args.format == "json":
        result = {
            "summary": {"group": args.group, "message_count": total_msgs, "time_window": t_label},
            "scope": {"data_source": str(group_file)},
            "result": [{"keyword": k, "count": int(v)} for k, v in keyword_counts.items()] if len(keyword_counts) > 0 else [],
        }
        if args.output:
            out_dir = Path(args.output)
            out_dir.mkdir(parents=True, exist_ok=True)
            jpath = out_dir / f"{t_label}_voc_keywords_{args.group}.json"
            with open(jpath, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print()
            print("[Output]")
            print(f"  JSON: {jpath}")
        else:
            print()
            print("[Output]")
            print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
