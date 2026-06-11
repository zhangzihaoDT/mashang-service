#!/usr/bin/env python
"""
单轮 Context Parser CLI — 将自然语言转成结构化 context

用法:
    python eval/parse_context_cli.py "昨天锁单数分车型"
    python eval/parse_context_cli.py "那最近 7 天呢？" --previous-context '{"metric":"lock_count_share","time_window":"last_15_days","series":"LS6","group_by":"energy_type"}'
    python eval/parse_context_cli.py "昨天 LS8 的 75 个锁单城市分布" --format json
"""

import sys, argparse, json
from pathlib import Path

import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parents[1])); from utils.paths import PROJECT_ROOT, WORKSPACE_ROOT

from eval.context_parser import parse_context


def parse_args():
    parser = argparse.ArgumentParser(description="单轮 Context Parser CLI")
    parser.add_argument("text", type=str, help="用户自然语言文本")
    parser.add_argument("--previous-context", type=str, default=None,
                        help="上一轮 context JSON 字符串")
    parser.add_argument("--format", type=str, default="terminal", choices=["terminal", "json"],
                        help="输出格式 (默认 terminal)")
    return parser.parse_args()


def main():
    args = parse_args()

    previous = None
    if args.previous_context:
        try:
            previous = json.loads(args.previous_context)
        except json.JSONDecodeError as e:
            print(f"[Error] previous-context JSON 解析失败: {e}", file=sys.stderr)
            sys.exit(1)

    result = parse_context(args.text, previous_context=previous)

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"{'='*60}")
        print(f"Context Parser")
        print(f"{'='*60}")
        print(f"  Text:       {result['raw_text']}")
        print(f"  Confidence: {result['confidence']}")
        print(f"  Mode:       {result['parser_mode']}")
        print()
        print(f"  Parsed:     {result['parsed_context']}")
        print(f"  Resolved:   {result['resolved_context']}")
        print(f"  Inherited:  {result['inherited_context']}")
        print(f"  Overridden: {result['overridden_context']}")
        print(f"  Missing:    {result['missing_context']}")
        print()


if __name__ == "__main__":
    main()
