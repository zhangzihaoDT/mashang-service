"""Validate a Topic Deck against the canonical Slide Contract (structural + semantic).

Two layers:

1. Structural (schema):
   - every required field present
   - slide_role / claim_level / visual.type / comparison_semantics within enums
   - CONTROLLED_FINDING needs controls/estimator/sample_n
   - appendix_ref points to a registered appendix

2. Semantic lint (cross-field consistency):
   - evidence.ids must exist in the referenced run's evidence.jsonl
   - claim_level=OBSERVATION must not contain causal language
   - controlled_anchor must point to a CONTROLLED_FINDING / MECHANISM_EVIDENCE page
   - MANAGERIAL_SYNTHESIS / CONCEPTUAL_BRIDGE must not carry p-value / significance in hero
   - BOUNDARY / RESEARCH_BOUNDARY must not be visual-highlighted as a positive finding
   - visual.type must be compatible with slide_role (visual_role_compatibility matrix)
   - visual.type=before_after must declare comparison_semantics

Usage:
  PYTHONPATH=. ../.venv/bin/python scratch/validate_slide_contract.py \
      --deck reports/from_parameters_to_experience_topic_deck.md
  PYTHONPATH=. ../.venv/bin/python scratch/validate_slide_contract.py --format json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

CAUSAL_PATTERNS = None


def _load_causal_patterns(contract: dict) -> list[re.Pattern]:
    words = contract.get("causal_language", {}).get("reject", [])
    return [re.compile(re.escape(w)) for w in words]


def parse_metadata_blocks(text: str) -> list[tuple[str, dict]]:
    """Return [(page_title, metadata_dict), ...] for each ```yaml ... ``` block."""
    out = []
    pattern = re.compile(
        r"^#\s+(P\d+).*?\n\n```yaml\n---\n(.*?)\n---\n```",
        re.M | re.S,
    )
    for m in pattern.finditer(text):
        page, body = m.group(1), m.group(2)
        try:
            meta = yaml.safe_load(body) if yaml else {}
        except Exception as exc:
            meta = {"__yaml_error__": str(exc)}
        out.append((page, meta))
    return out


def load_run_evidence_ids(contract: dict) -> dict[str, set[str]]:
    """Map run name -> set of evidence ids found in research/runs/<run>/evidence.jsonl."""
    mapping: dict[str, set[str]] = {}
    runs_dir = PROJECT_ROOT / "research" / "runs"
    if not runs_dir.exists():
        return mapping
    for run_dir in runs_dir.iterdir():
        ev_file = run_dir / "evidence.jsonl"
        if not ev_file.exists():
            continue
        ids = set()
        for line in ev_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                ids.add(json.loads(line).get("id", ""))
            except json.JSONDecodeError:
                continue
        mapping[run_dir.name] = {i for i in ids if i}
    return mapping


def load_known_signal_ids(contract: dict) -> set[str]:
    """Aggregate signal_ids from contract.signal_sources (json signal records + signal_board.md)."""
    known: set[str] = set()
    for rel in contract.get("signal_sources", []):
        path = PROJECT_ROOT / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        # JSON signal records: every "signal_id" value
        for m in re.finditer(r'"signal_id"\s*:\s*"([^"]+)"', text):
            known.add(m.group(1))
        # signal_board.md tables: first column is the signal id (e.g. expectation_wow_01)
        for m in re.finditer(r"^\|?\s*(expectation_wow_\d+|main_effect_\d+|segment_discriminator_\d+|nonlinear_pattern_\d+|interaction_\d+)", text, re.M):
            known.add(m.group(1))
    return known


def _flatten_text(*values) -> str:
    """Join nested lists/strings/numbers into a single searchable string."""
    parts = []
    for v in values:
        if v is None:
            continue
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, (list, tuple)):
            parts.extend(str(x) for x in v)
        else:
            parts.append(str(v))
    return " ".join(parts)


def _norm_ref(ref: str) -> str:
    """Normalize a 'Pn / run / id' anchor to its page token (Pn)."""
    m = re.search(r"(P\d+)", ref or "")
    return m.group(1) if m else ""


def validate(deck_text: str, contract: dict) -> dict:
    required = set(contract.get("required_fields", []))
    enums = contract.get("enums", {})
    registry = contract.get("appendix_registry", {})
    governance = contract.get("governance_rules", [])
    compat = contract.get("visual_role_compatibility", {})
    causal = _load_causal_patterns(contract)
    global CAUSAL_PATTERNS
    CAUSAL_PATTERNS = causal

    blocks = parse_metadata_blocks(deck_text)
    meta_by_page = {page: meta for page, meta in blocks if "__yaml_error__" not in meta}
    run_ids = load_run_evidence_ids(contract)
    known_signal_ids = load_known_signal_ids(contract)
    pages = {}

    # helper to check a page claim_level
    def claim_of(anchor_ref: str) -> str | None:
        page = _norm_ref(anchor_ref)
        m = meta_by_page.get(page)
        return m.get("claim_level") if m else None

    for page, meta in blocks:
        if "__yaml_error__" in meta:
            pages[page] = [{"level": "error", "rule": "yaml", "msg": meta["__yaml_error__"]}]
            continue
        errors = []
        # ---------- structural ----------
        for f in sorted(required - set(meta)):
            errors.append({"level": "error", "rule": "required", "msg": f"missing '{f}'"})
        for field, values in enums.items():
            if field == "visual_type":
                val = (meta.get("visual") or {}).get("type")
            else:
                val = meta.get(field)
            if val is not None and val not in values:
                errors.append({"level": "error", "rule": "enum", "msg": f"'{field}'='{val}' not in {values}"})
        claim = meta.get("claim_level")
        if claim == "CONTROLLED_FINDING":
            ev = meta.get("evidence") or {}
            if not ev.get("controls") and not ev.get("estimator"):
                errors.append({"level": "warn", "rule": "governance", "msg": "CONTROLLED_FINDING without controls/estimator"})
        for r in (meta.get("appendix_ref") or []):
            if str(r) not in registry:
                errors.append({"level": "warn", "rule": "appendix", "msg": f"appendix '{r}' not registered"})

        # ---------- semantic ----------
        vis = meta.get("visual") or {}
        ev = meta.get("evidence") or {}

        # S1. evidence.ids must exist in the referenced run
        run = ev.get("run")
        ids = ev.get("ids") or []
        if run and ids:
            known = run_ids.get(run, set())
            for eid in ids:
                if eid not in known:
                    errors.append({"level": "error", "rule": "semantic.evidence_id",
                                   "msg": f"evidence id '{eid}' not found in run '{run}'"})
        # S1b. evidence.signal_ids must exist in the known signal records
        sids = ev.get("signal_ids") or []
        for sid in sids:
            if sid not in known_signal_ids:
                errors.append({"level": "error", "rule": "semantic.signal_id",
                               "msg": f"signal_id '{sid}' not found in signal sources (contract.signal_sources)"})
        # S2. OBSERVATION no causal language
        if claim == "OBSERVATION":
            text = _flatten_text(meta.get("question"), meta.get("answer"),
                                 vis.get("hero_message"), vis.get("annotation"))
            for pat in causal:
                if pat.search(text):
                    errors.append({"level": "error", "rule": "semantic.causal",
                                   "msg": f"OBSERVATION page contains causal language: '{pat.pattern}' in: {text[:80]}"})
        # S3. controlled_anchor must point to CONTROLLED_FINDING / MECHANISM_EVIDENCE
        anchor = ev.get("controlled_anchor")
        if claim == "OBSERVATION" and anchor:
            target_claim = claim_of(anchor)
            if target_claim not in {"CONTROLLED_FINDING", "MECHANISM_EVIDENCE"}:
                errors.append({"level": "error", "rule": "semantic.anchor",
                               "msg": f"controlled_anchor '{anchor}' -> claim_level='{target_claim}', expected CONTROLLED_FINDING/MECHANISM_EVIDENCE"})
        # S4. MANAGERIAL_SYNTHESIS / CONCEPTUAL_BRIDGE no p-value / significance hero
        if claim in {"MANAGERIAL_SYNTHESIS", "CONCEPTUAL_BRIDGE"}:
            text = _flatten_text(vis.get("hero_message"), vis.get("annotation"), meta.get("answer"))
            if re.search(r"p[<=]\s*0?\.?\d+|d\s*=\s*[-\d.]|显著|significan", text, re.I):
                errors.append({"level": "error", "rule": "semantic.significance",
                               "msg": f"{claim} page must not present p-value/significance in hero: {text[:80]}"})
        # S5. BOUNDARY / RESEARCH_BOUNDARY not highlighted as positive finding
        if claim in {"BOUNDARY", "RESEARCH_BOUNDARY"}:
            hl = vis.get("highlight") or []
            if hl:
                joined = " ".join(str(h) for h in hl)
                if re.search(r"主要|核心|胜利|最好|最优|领先", joined):
                    errors.append({"level": "warn", "rule": "semantic.boundary_highlight",
                                   "msg": f"{claim} page highlights may read as positive finding: {joined}"})
        # S6. visual.type compatible with slide_role
        vtype = vis.get("type")
        role = meta.get("slide_role")
        if vtype and role and vtype in compat:
            if role not in compat[vtype]:
                errors.append({"level": "error", "rule": "semantic.visual_role",
                               "msg": f"visual.type='{vtype}' not compatible with slide_role='{role}' (allowed: {compat[vtype]})"})
        # S7. before_after requires comparison_semantics
        if vtype == "before_after":
            cs = vis.get("comparison_semantics")
            if not cs:
                errors.append({"level": "error", "rule": "semantic.comparison_semantics",
                               "msg": "visual.type=before_after must declare comparison_semantics (raw_vs_adjusted / group_a_vs_b / temporal_trend)"})

        pages[page] = errors

    n_pages = len(pages)
    n_err = sum(1 for v in pages.values() if any(e["level"] == "error" for e in v))
    n_warn = sum(1 for v in pages.values() if any(e["level"] == "warn" for e in v))
    return {
        "status": "pass" if n_err == 0 else "fail",
        "contract_version": contract.get("schema_version"),
        "n_pages": n_pages,
        "n_pages_with_errors": n_err,
        "n_pages_with_warnings": n_warn,
        "governance_rules_checked": len(governance),
        "semantic_rules_checked": len(contract.get("semantic_rules", [])),
        "pages": pages,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a deck against the canonical Slide Contract")
    parser.add_argument("--deck", default="reports/from_parameters_to_experience_topic_deck.md")
    parser.add_argument("--contract", default="contracts/slide_contract.json")
    parser.add_argument("--format", default="text", choices=["text", "json"])
    args = parser.parse_args()

    if yaml is None:
        print("missing PyYAML; pip install PyYAML", file=sys.stderr)
        sys.exit(2)

    contract = json.loads((PROJECT_ROOT / args.contract).read_text(encoding="utf-8"))
    deck = (PROJECT_ROOT / args.deck).read_text(encoding="utf-8")
    result = validate(deck, contract)

    if args.format == "json":
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"deck        : {args.deck}")
        print(f"contract    : {args.contract} (v{result['contract_version']})")
        print(f"status      : {result['status']}")
        print(f"pages       : {result['n_pages']}  errors={result['n_pages_with_errors']} warnings={result['n_pages_with_warnings']}")
        print(f"rules       : structural-governance={result['governance_rules_checked']} semantic={result['semantic_rules_checked']}")
        for page, issues in result["pages"].items():
            if not issues:
                continue
            print(f"  {page}:")
            for issue in issues:
                print(f"    [{issue['level']}] {issue['rule']}: {issue['msg']}")
    sys.exit(0 if result["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
