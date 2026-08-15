"""Render a final insight payload; no dataset or research judgment is imported."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def render(payload: dict) -> str:
    evidence = payload.get("evidence", [])
    evidence_lines = "\n".join(
        f"- `{item.get('id', '')}` {item.get('finding', item.get('statement', ''))}"
        for item in evidence
    )
    return f"""# {payload.get('headline', 'Untitled Topic')}\n\n{payload.get('insight', '')}\n\n## Evidence\n\n{evidence_lines or '- 暂无证据'}\n\n## Implication\n\n{payload.get('implication', '')}\n\n## Recommendation\n\n{payload.get('recommendation', '')}\n"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Render final insight JSON as Markdown")
    parser.add_argument("--input", default="research/runs/topic_x/insight.json")
    parser.add_argument("--output", default="reports/topic_x.md")
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    Path(args.output).write_text(render(payload), encoding="utf-8")
    print(f"Markdown report: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
