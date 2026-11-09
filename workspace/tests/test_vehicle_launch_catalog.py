"""车型上市专题入口的静态一致性校验（不读取订单数据、不执行脚本或推送）。"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "workspace/registry/vehicle_launch_capabilities.json"
GLOBAL = ROOT / "workspace/registry/capability_registry.json"
JOBS = ROOT / "jobs/config/jobs_config.json"


def _load():
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def test_launch_catalog_structure():
    x = _load()
    assert x["topic_id"] == "vehicle_launch"
    assert len(x["capability_types"]) == 2
    assert {r["id"] for r in x["capability_types"]} == {"research_reports", "monitoring"}
    assert len(x["report_entries"]) == 4
    assert x["capability_types"][0]["entry_count"] == 4
    assert x["capability_types"][1]["entry_count"] == 1
    assert x["monitor_entry"]["id"] == "vehicle_sales_monitor"
    ids = [e["id"] for e in x["report_entries"]] + [x["monitor_entry"]["id"]]
    assert len(ids) == len(set(ids))


def test_launch_catalog_real_scripts_and_supported_flags():
    x = _load()
    entries = x["report_entries"] + [x["monitor_entry"]]
    for e in entries:
        p = ROOT / e["script"]
        assert p.is_file(), e["script"]
        source = p.read_text(encoding="utf-8")
        for flag in e["cli"]["flags"]:
            token = flag.split()[0].split("|")[0]
            assert f'"{token}"' in source, (e["id"], token)


def test_launch_catalog_date_semantics():
    x = _load()
    assert x["authority"]["business_definition"] == "shared/schema/business_definition.json"
    periods = x["authority"]["time_periods"]
    assert "预售" in periods["start"]
    assert "正式上市" in periods["end"]
    assert "权益" in periods["finish"]
    risk = next(e for e in x["report_entries"] if e["id"] == "launch_presale_risk_snapshot")
    assert "start" in risk["anchor"]
    assert "严格 < start" in risk["anchor"]
    assert "end" not in risk["anchor"]
    assert all(r["production_job_registered"] is False for r in x["report_entries"])


def test_launch_catalog_preserves_existing_governance():
    x = _load()
    assert x["governance"]["no_new_job_registration"] is True
    assert x["governance"]["no_change_to_algorithms"] is True
    global_caps = json.loads(GLOBAL.read_text(encoding="utf-8"))
    assert isinstance(global_caps, list)
    jobs = json.loads(JOBS.read_text(encoding="utf-8"))
    assert "feature_jobs" in jobs


def test_launch_catalog_docs_linked():
    for path in ["docs/README.md", "workspace/README.md"]:
        content = (ROOT / path).read_text(encoding="utf-8")
        assert "vehicle_launch_capabilities.md" in content
    assert (ROOT / "docs/业务能力/车型预售与上市/vehicle_launch_capabilities.md").exists()
