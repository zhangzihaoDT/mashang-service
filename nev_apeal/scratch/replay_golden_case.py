"""Replay the Production Pipeline v1 Golden Case.

Runs both QA gates against the frozen artifacts and compares results to the
expected acceptance values in `contracts/golden_case_v1.json`:

  - slides count == expected.slides (from deck.md contract, cross-checked vs rendered HTML)
  - semantic lint 0 error / 0 warn
  - render QA     0 error / 0 warn

Any mismatch returns FAIL and the exit code is non-zero, which blocks a merge
until the change is fixed and replayed.

Usage:
  PYTHONPATH=. ../.venv/bin/python scratch/replay_golden_case.py
  PYTHONPATH=. ../.venv/bin/python scratch/replay_golden_case.py --format json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def _run_module(rel_script: str, args: list[str], cwd: Path) -> dict:
    """Run a scratch validator as JSON and return its result dict."""
    proc = subprocess.run(
        [PYTHON, rel_script, "--format", "json", *args],
        cwd=cwd, capture_output=True, text=True,
    )
    out = proc.stdout.strip()
    if not out:
        return {"_error": f"{rel_script} produced no JSON output", "_stderr": proc.stderr[-500:]}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"_error": f"{rel_script} produced invalid JSON", "_raw": out[-500:], "_stderr": proc.stderr[-500:]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay Production Pipeline v1 Golden Case")
    parser.add_argument("--format", default="text", choices=["text", "json"])
    args = parser.parse_args()

    golden = json.loads((PROJECT_ROOT / "contracts" / "golden_case_v1.json").read_text(encoding="utf-8"))
    expected = golden["expected"]
    deck_rel = "reports/from_parameters_to_experience_topic_deck.md"
    html_rel = "reports/from_parameters_to_experience_topic_deck.html"

    # 1. semantic lint
    semantic = _run_module("scratch/validate_slide_contract.py", ["--deck", deck_rel], PROJECT_ROOT)
    # 2. render QA
    render = _run_module("scratch/render_qa.py", ["--html", html_rel, "--deck", deck_rel], PROJECT_ROOT)

    semantic_n = semantic.get("n_pages", -1)
    semantic_err = semantic.get("n_pages_with_errors", -1)
    semantic_warn = semantic.get("n_pages_with_warnings", -1)
    render_n = render.get("pages_expected", render.get("n_pages", -1))
    render_err = sum(1 for c in render.get("checks", []) if c.get("level") == "error")
    render_warn = sum(1 for c in render.get("checks", []) if c.get("level") == "warn")

    checks = [
        ("slides", semantic_n, expected["slides"], 10),
        ("semantic_errors", semantic_err, expected["semantic_errors"], 0),
        ("semantic_warnings", semantic_warn, expected["semantic_warnings"], 0),
        ("render_errors", render_err, expected["render_errors"], 0),
        ("render_warnings", render_warn, expected["render_warnings"], 0),
    ]

    ok = all(actual == expect for _, actual, expect, _ in checks) and render_n == expected["slides"]
    result = {
        "golden_case": golden["golden_case"],
        "version": golden["version"],
        "status": "PASS" if ok else "FAIL",
        "expected": expected,
        "actual": {
            "slides": semantic_n,
            "slides_rendered": render_n,
            "semantic_errors": semantic_err,
            "semantic_warnings": semantic_warn,
            "render_errors": render_err,
            "render_warnings": render_warn,
        },
        "checks": [
            {"metric": name, "expected": expect, "actual": actual, "pass": actual == expect}
            for name, actual, expect, _ in checks
        ],
        "semantic_detail": semantic.get("_error", None) or semantic.get("status"),
        "render_detail": render.get("_error", None) or render.get("status"),
    }

    if args.format == "json":
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"golden case  : {result['golden_case']} v{result['version']}")
        print(f"status       : {result['status']}")
        print("  metric            expected  actual")
        for c in result["checks"]:
            mark = "OK" if c["pass"] else "!!"
            print(f"  [{mark}] {c['metric']:<20s} {c['expected']:<9d} {c['actual']}")
        print(f"  slides_rendered  expected {expected['slides']}  actual {render_n}")
        if result.get("semantic_detail") not in (None, "pass"):
            print(f"  semantic_detail: {result['semantic_detail']}")
        if result.get("render_detail") not in (None, "pass"):
            print(f"  render_detail: {result['render_detail']}")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
