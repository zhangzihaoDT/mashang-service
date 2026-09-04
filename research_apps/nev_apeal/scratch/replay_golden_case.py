"""Production Golden Case v1 — unified regression entrypoint.

Replays the two QA gates against the frozen artifacts and compares results to
the expected acceptance values in `contracts/golden_case_v1.json`.

Checks:
  slides            == expected.slides        (10)
  semantic errors   == 0
  semantic warnings == 0
  evidence refs     == >0 and all resolved (no semantic.evidence_id errors)
  signal refs       == >0 and all resolved (no semantic.signal_id errors)
  render errors     == 0
  render warnings   == 0

Any mismatch -> FAIL, non-zero exit code, blocks merge until fixed and replayed.

Usage:
  PYTHONPATH=. ../.venv/bin/python scratch/replay_golden_case.py
  PYTHONPATH=. ../.venv/bin/python scratch/replay_golden_case.py --format json
  make production-golden
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable

REPORT_TEMPLATE = """Production Golden Case v1
──────────────────────────
Slides                {slides:>5} / {slides_exp:<4} {slides_ok}
Semantic errors       {sem_errors:>5}    {sem_errors_ok}
Semantic warnings     {sem_warnings:>5}    {sem_warnings_ok}
Evidence refs         {ev_refs:>5}    {ev_refs_ok}
Signal refs           {sig_refs:>5}    {sig_refs_ok}
Render errors         {render_errors:>5}    {render_errors_ok}
Render warnings       {render_warnings:>5}    {render_warnings_ok}


RESULT: {result}
"""


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


def _flag(actual, expected, extra: bool = True) -> str:
    return "PASS" if (actual == expected and extra) else "FAIL"


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay Production Golden Case v1")
    parser.add_argument("--format", default="text", choices=["text", "json"])
    args = parser.parse_args()

    golden = json.loads((PROJECT_ROOT / "contracts" / "golden_case_v1.json").read_text(encoding="utf-8"))
    expected = golden["expected"]
    deck_rel = "reports/from_parameters_to_experience_topic_deck.md"
    html_rel = "reports/from_parameters_to_experience_topic_deck.html"

    semantic = _run_module("scratch/validate_slide_contract.py", ["--deck", deck_rel], PROJECT_ROOT)
    render = _run_module("scratch/render_qa.py", ["--html", html_rel, "--deck", deck_rel], PROJECT_ROOT)

    # page count from semantic lint (deck.md metadata blocks)
    slides = semantic.get("n_pages", -1)
    sem_errors = semantic.get("n_pages_with_errors", -1)
    sem_warnings = semantic.get("n_pages_with_warnings", -1)

    # provenance: evidence/signal refs are valid only when no id-resolution errors
    page_issues = semantic.get("pages", {})
    ev_id_errors = sum(1 for v in page_issues.values() for e in v if e.get("rule") == "semantic.evidence_id")
    sig_id_errors = sum(1 for v in page_issues.values() for e in v if e.get("rule") == "semantic.signal_id")
    ev_refs = semantic.get("evidence_refs", 0)
    sig_refs = semantic.get("signal_refs", 0)

    # render QA counts
    render_checks = render.get("checks", [])
    render_errors = sum(1 for c in render_checks if c.get("level") == "error")
    render_warnings = sum(1 for c in render_checks if c.get("level") == "warn")
    slides_rendered = render.get("pages_expected", render.get("n_pages", -1))

    checks = [
        ("slides", slides, expected["slides"]),
        ("semantic_errors", sem_errors, expected["semantic_errors"]),
        ("semantic_warnings", sem_warnings, expected["semantic_warnings"]),
        ("evidence_refs", ev_refs, 0),
        ("signal_refs", sig_refs, 0),
        ("render_errors", render_errors, expected["render_errors"]),
        ("render_warnings", render_warnings, expected["render_warnings"]),
    ]
    # evidence/signal: refs must exist (>0) AND resolve (no id errors)
    ev_ok = ev_refs > 0 and ev_id_errors == 0
    sig_ok = sig_refs > 0 and sig_id_errors == 0

    ok = (
        slides == expected["slides"]
        and sem_errors == expected["semantic_errors"]
        and sem_warnings == expected["semantic_warnings"]
        and ev_ok and sig_ok
        and render_errors == expected["render_errors"]
        and render_warnings == expected["render_warnings"]
        and slides_rendered == expected["slides"]
    )

    result = {
        "golden_case": golden["golden_case"],
        "version": golden["version"],
        "status": "PASS" if ok else "FAIL",
        "expected": expected,
        "actual": {
            "slides": slides,
            "slides_rendered": slides_rendered,
            "semantic_errors": sem_errors,
            "semantic_warnings": sem_warnings,
            "evidence_refs": ev_refs,
            "signal_refs": sig_refs,
            "evidence_id_errors": ev_id_errors,
            "signal_id_errors": sig_id_errors,
            "render_errors": render_errors,
            "render_warnings": render_warnings,
        },
        "checks": [
            {"metric": m, "expected": e, "actual": a, "pass": (a == e)}
            for m, a, e in checks
        ],
        "provenance": {"evidence": ev_ok, "signal": sig_ok},
        "semantic_detail": semantic.get("_error") or semantic.get("status"),
        "render_detail": render.get("_error") or render.get("status"),
    }

    if args.format == "json":
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print(REPORT_TEMPLATE.format(
            slides=slides, slides_exp=expected["slides"], slides_ok="PASS" if slides == expected["slides"] else "FAIL",
            sem_errors=sem_errors, sem_errors_ok=_flag(sem_errors, expected["semantic_errors"]),
            sem_warnings=sem_warnings, sem_warnings_ok=_flag(sem_warnings, expected["semantic_warnings"]),
            ev_refs=ev_refs, ev_refs_ok="PASS" if ev_ok else "FAIL",
            sig_refs=sig_refs, sig_refs_ok="PASS" if sig_ok else "FAIL",
            render_errors=render_errors, render_errors_ok=_flag(render_errors, expected["render_errors"]),
            render_warnings=render_warnings, render_warnings_ok=_flag(render_warnings, expected["render_warnings"]),
            result="PASS" if ok else "FAIL",
        ))
        if not ok:
            for detail in ("semantic_detail", "render_detail"):
                v = result.get(detail)
                if v not in (None, "pass"):
                    print(f"[detail] {detail}: {v}")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
