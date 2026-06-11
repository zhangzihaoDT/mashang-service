#!/usr/bin/env python
"""Helper: calls context_parser.parse_context and prints JSON result.
Used by run_reference_eval.py via subprocess to avoid module shadowing."""
import sys, json
from pathlib import Path

_WS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_WS_DIR))

from eval.context_parser import parse_context

payload = json.loads(sys.argv[1])
r = parse_context(payload["text"], previous_context=payload.get("prev_ctx", {}),
                  previous_result_context=payload.get("prev_result", {}))
print(json.dumps(r, ensure_ascii=False))
