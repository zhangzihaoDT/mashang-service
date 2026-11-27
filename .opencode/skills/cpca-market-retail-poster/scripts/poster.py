#!/usr/bin/env python3
"""Render a candidate CPCA poster from a prepared Job briefing."""

import argparse
import hashlib
import json
import sys
from io import BytesIO
from pathlib import Path
from string import Template

from PIL import Image

import generation

SKILL = Path(__file__).resolve().parents[1]
REFERENCE = SKILL / "assets/reference-poster.png"
PROMPT = SKILL / "references/poster-prompt.txt"
PROMPT_V1_2 = SKILL / "references/poster-prompt-v1.2.txt"
BASELINE = SKILL / "references/production-baseline.json"


def load_assets(prompt_version="V1.1"):
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    prompt_bytes = PROMPT.read_bytes()
    reference = REFERENCE.read_bytes()
    if hashlib.sha256(prompt_bytes).hexdigest() != baseline["prompt_sha256"]:
        raise ValueError(f"固定 Prompt 与 {baseline['version']} 生产基线不一致")
    if hashlib.sha256(reference).hexdigest() != baseline["reference_sha256"]:
        raise ValueError(f"参考图与 {baseline['version']} 生产基线不一致")
    if prompt_version == "V1.2":
        prompt_bytes = PROMPT_V1_2.read_bytes()
    elif prompt_version != baseline["version"]:
        raise ValueError(f"不支持的 Prompt 版本：{prompt_version}")
    with Image.open(BytesIO(reference)) as image:
        if image.format != "PNG":
            raise ValueError("参考图必须是 PNG")
        image.verify()
    return baseline, prompt_bytes.decode("utf-8"), reference


def build_prompt(briefing_path, template):
    layout = json.loads(briefing_path.read_text(encoding="utf-8"))["layout"]
    lines = [f'日期条「{layout["date_strip"]}」']
    for row in layout["sections"]:
        lines.extend(["", f'卡片「{row["label"]}」 日期「{row["period_text"]}」'])
        for metric in row["metrics"].values():
            fields = [f'指标「{metric["label"]}」']
            if metric["value_text"] is not None:
                fields.append(f'销量「{metric["value_text"]} 万辆」')
            if metric["yoy_text"] is not None:
                fields.append(f'同比「{metric["yoy_text"]}」 （{metric["trend"]}）')
            lines.append("  ".join(fields))
    lines.extend(["", *(f"页脚「{line}」" for line in layout["footer"])])
    return Template(template).substitute(poster_text="\n".join(lines))


def render(briefing_path, template, reference, output):
    return generation.generate(build_prompt(briefing_path, template), reference, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--briefing", type=Path, required=True, help="Job 生成的 briefing.json")
    parser.add_argument("--prompt-version", choices=("V1.1", "V1.2"), default="V1.1",
                        help="V1.1 正式版或 V1.2 实验版")
    parser.add_argument("--generate", action="store_true", help="显式授权一次候选图生成")
    parser.add_argument("--output", type=Path, help="候选图目录")
    args = parser.parse_args()
    if args.generate != (args.output is not None):
        parser.error("--generate 和 --output 必须同时指定")
    try:
        _, template, reference = load_assets(args.prompt_version)
        if not args.generate:
            print(build_prompt(args.briefing, template))
            return 0
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=True)
        result = render(args.briefing, template, reference, output)
        print(f"{result['status']} | {result.get('image_path', '')}")
        return 0 if result["status"] == "pending_visual_review" else 1
    except (ValueError, TypeError, OSError, KeyError) as error:
        parser.exit(1, f"CPCA 海报失败：{error}\n")


if __name__ == "__main__":
    sys.exit(main())
