"""store_leads_intention_quadrant.py smoke test — 线索×小订转化 四象限。"""

import subprocess
import sys
from pathlib import Path

import pytest

_PRJ = Path(__file__).resolve().parents[3]
_WS_DIR = _PRJ / "mashang_workspace"
SCRIPT = _WS_DIR / "research_scripts" / "store_leads_intention_quadrant.py"
OBS_CSV = _WS_DIR / "outputs" / "tables" / "store_operation_observation.csv"


def _run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, timeout=180)


def test_help():
    r = _run("--help")
    assert r.returncode == 0
    assert "--input" in r.stdout and "--top-label" in r.stdout


@pytest.mark.skipif(not OBS_CSV.exists(), reason="store_operation_observation.csv 不存在")
def test_render(tmp_path):
    out = tmp_path / "quad.html"
    r = _run("--input", str(OBS_CSV), "--output", str(out))
    assert r.returncode == 0, r.stderr[-2000:]
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert "四象限" in html and "report_style.css" in html
