"""Run the bounded Discovery queue and merge scanner outputs.

The queue is explicit and ordered. Adding a variable requires changing a
scanner's registry, rather than silently expanding a Cartesian product.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SCANNERS = [
    ("expectation_wow", HERE / "expectation_wow_scan.py", HERE / "_signals_expectation_wow.json"),
    ("nonlinear_pattern", HERE / "nonlinear_pattern_scan.py", HERE / "_signals_nonlinear.json"),
    ("segment_discriminator", HERE / "segment_discriminator_scan.py", HERE / "_signals_segment_discriminator.json"),
]
OUT = HERE / "_signals_round2.json"


def main() -> None:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    merged = []
    for analysis_type, script, output in SCANNERS:
        subprocess.run([sys.executable, str(script)], cwd=ROOT, env=env, check=True)
        payload = json.loads(output.read_text(encoding="utf-8"))
        for signal in payload:
            signal.setdefault("analysis_type", analysis_type)
        merged.extend(payload)
    OUT.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"merged {len(merged)} signals -> {OUT}")


if __name__ == "__main__":
    main()
