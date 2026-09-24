"""presale_intention_funnel.py smoke test — 泛化预售小订转化漏斗。"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

_PRJ = Path(__file__).resolve().parents[3]
SCRIPT = _PRJ / "mashang_workspace" / "runtime_scripts" / "presale_intention_funnel.py"
ORDER_DATA = _PRJ / "dataset" / "order_data.parquet"


def _run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, timeout=180
    )


def test_help():
    r = _run("--help")
    assert r.returncode == 0
    assert "--series" in r.stdout and "--as-of" in r.stdout


def test_list_generations():
    r = _run("--list")
    assert r.returncode == 0
    assert "CM3" in r.stdout


def test_unknown_generation_errors():
    r = _run("--series", "NOT_A_GEN")
    assert r.returncode != 0


@pytest.mark.skipif(not ORDER_DATA.exists(), reason="order_data.parquet 不存在")
def test_cm3_funnel_contract():
    r = _run("--series", "CM3", "--as-of", "2026-09-24", "--format", "json")
    assert r.returncode == 0, r.stderr[-2000:]
    contract = json.loads(r.stdout)
    assert contract["status"] == "success"
    row = contract["result"]["tables"][0]["rows"][0]
    assert row["generation"] == "CM3"
    partition = (
        row["locked_only"]
        + row["deposit_not_locked"]
        + row["refunded_not_progressed"]
        + row["pending"]
    )
    assert partition == row["cohort_total"]
    assert row["refunded_not_progressed"] <= row["refunded_total"]
    assert row["lock_total"] <= row["cohort_total"]
    assert row["cohort_total"] > 0
    assert contract["result"]["metrics"]["CM3_cohort_total"] == row["cohort_total"]
