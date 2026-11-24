import base64
import hashlib
import json
from wsgiref.util import setup_testing_defaults

import pandas as pd
import pytest

from apps.market_monitor.backend import __main__ as cli
from apps.market_monitor.backend.snapshot import (
    MIIT_FIELDS,
    build_miit,
    envelope,
    import_snapshot,
    publish,
)
from apps.market_monitor.backend.web import create_app
from workspace.research_scripts.market_report.generate_monthly_brief import (
    ReportData,
    build_brand_landscape,
    build_overall_market,
)


def passenger(batch, published, stage="confirmed"):
    return {
        **{key: "" for key in MIIT_FIELDS},
        "vehicle_record_id": f"{batch}:MODEL",
        "batch_no": batch,
        "model_code": "MODEL",
        "publish_date": published,
        "source": "miit_gov",
        "stage": stage,
        "vehicle_category": "passenger_vehicle",
    }


def test_canonical_identity_follows_batch_not_model(tmp_path):
    path = tmp_path / "product_master.json"
    records = [
        passenger("410", "2026-08-07"),
        passenger("411", "2026-09-08", "proposed"),
        passenger("412", "2026-09-30"),
    ]
    path.write_text(json.dumps(records))
    result = build_miit(path)
    assert result["latest_month"] == "2026-09"
    assert [row["vehicle_record_id"] for row in result["months"]["2026-09"]] == [
        "412:MODEL", "411:MODEL",
    ]
    assert result["months"]["2026-09"][1]["stage"] == "proposed"
    assert "vehicle_category" not in result["months"]["2026-08"][0]
    path.write_text(json.dumps([*records, records[0]]))
    with pytest.raises(ValueError, match="canonical"):
        build_miit(path)
    path.write_text(json.dumps([dict(records[0], vehicle_category="commercial_vehicle")]))
    with pytest.raises(ValueError, match="乘用车契约"):
        build_miit(path)


def test_reused_report_builders_handle_missing_comparison_baselines():
    energy = pd.DataFrame({
        "date_month": pd.to_datetime(["2026-01-01", "2026-01-01"]),
        "fuel_type_group": ["新能源", "燃油"],
        "fuel_type": ["纯电动", "汽油"],
        "sales": [100, 300],
        "weighted_tp": [200000, 100000],
    })
    brands = pd.DataFrame({
        "date_month": pd.to_datetime(["2025-12-01", "2026-01-01", "2026-01-01"]),
        "brand": ["A", "A", "B"],
        "sales": [100, 300, 100],
        "weighted_tp": [100000, 100000, 200000],
    })
    report = ReportData("2026-01", frames={"market_energy_monthly": energy, "brand_monthly": brands})

    overall = build_overall_market(report)
    assert overall["total_sales"] == 400
    assert overall["weighted_tp"] == 125000
    assert overall["nev_penetration"] == 25
    assert overall["mom_pct"] is None and overall["yoy_pct"] is None
    assert [row["mom_pct"] for row in overall["energy_breakdown"]] == [None, None]
    ranking = build_brand_landscape(report)["top20"]
    assert ranking[0]["mom_pct"] == 200
    assert pd.isna(ranking[1]["mom_pct"])


def request(app, path, authorization=None, method="GET"):
    environ = {}
    setup_testing_defaults(environ)
    environ.update(PATH_INFO=path, REQUEST_METHOD=method)
    if authorization is not None:
        environ["HTTP_AUTHORIZATION"] = authorization
    response = []

    def start_response(status, headers):
        response.extend([int(status.split()[0]), dict(headers)])

    data = b"".join(app(environ, start_response))
    return (*response, data)


def insurance_month(total):
    return {"metrics": {"total_sales": total}, "energy": [], "brands": []}


def test_api_reports_independent_coverage_and_preserves_missing_months(tmp_path):
    publish(tmp_path, "insurance", envelope(
        "insurance", {"2026-07": insurance_month(42), "2026-09": insurance_month(53)}, None,
    ))
    publish(tmp_path, "miit", envelope("miit", {"2026-10": []}, None))
    app = create_app(tmp_path, local=True)
    status, _, content = request(app, "/api/v1/status")
    assert status == 200
    sources = json.loads(content)["sources"]
    assert sources["insurance"]["latest_month"] == "2026-09"
    assert sources["miit"]["latest_month"] == "2026-10"
    assert {source["cadence"] for source in sources.values()} == {"monthly"}
    assert request(app, "/api/v1/insurance/2026-08")[0] == 404
    assert request(app, "/api/v1/miit/2026-09")[0] == 404

    status, headers, content = request(app, "/api/v1/insurance/2026-09")
    assert status == 200 and headers["Cache-Control"] == "no-store"
    payload = json.loads(content)
    assert payload["data"]["metrics"]["total_sales"] == 53
    assert len(payload["trend"]) == 12
    assert payload["trend"][-3:] == [
        {"month": "2026-07", "total_sales": 42},
        {"month": "2026-08", "total_sales": None},
        {"month": "2026-09", "total_sales": 53},
    ]
    (tmp_path / "miit.json").write_text("[]")
    assert request(app, "/api/v1/miit/2026-10")[0] == 503
    assert request(app, "/api/v1/insurance/2026-09")[0] == 200


def test_deployment_auth_gates_web_and_api(tmp_path, monkeypatch):
    monkeypatch.delenv("MARKET_MONITOR_AUTH_FILE", raising=False)
    with pytest.raises(ValueError, match="MARKET_MONITOR_AUTH_FILE"):
        create_app(tmp_path)

    auth_file = tmp_path / "access.json"
    token = "example-test-token"
    auth_file.write_text(json.dumps({"reader": hashlib.sha256(token.encode()).hexdigest()}))
    monkeypatch.setenv("MARKET_MONITOR_AUTH_FILE", str(auth_file))
    app = create_app(tmp_path)
    for path in ("/", "/app.js", "/api/v1/status", "/api/v1/insurance/2026-10"):
        for invalid in (None, "Basic !!", "Basic cmVhZGVyOmJhZA=="):
            status, headers, body = request(app, path, invalid)
            assert status == 401 and headers["WWW-Authenticate"].startswith("Basic ")
            assert json.loads(body)["error"] == "authentication_required"

    credentials = "Basic " + base64.b64encode(f"reader:{token}".encode()).decode()
    assert request(app, "/", credentials)[0] == 200
    assert request(app, "/app.js", credentials, method="HEAD")[2] == b""
    assert request(app, "/api/v1/status", credentials, method="POST")[0] == 405
    assert request(app, "/api/v1/insurance/2026-10", credentials)[0] == 503


def test_import_rejects_regressed_or_wrong_source_snapshot(tmp_path):
    current = envelope("insurance", {"2026-10": insurance_month(53)}, None)
    import_snapshot(tmp_path, "insurance", current)
    path = tmp_path / "insurance.json"
    previous_bytes = path.read_bytes()
    with pytest.raises(ValueError, match="早于线上"):
        import_snapshot(tmp_path, "insurance", envelope("insurance", {"2026-09": insurance_month(42)}, None))
    with pytest.raises(ValueError, match="版本或来源"):
        import_snapshot(tmp_path, "miit", current)
    assert path.read_bytes() == previous_bytes


def test_partial_refresh_keeps_failed_source_and_updates_other(tmp_path, monkeypatch):
    original = envelope("insurance", {"2026-09": insurance_month(53)}, None)
    publish(tmp_path, "insurance", original)
    monkeypatch.setenv("MARKET_MONITOR_SNAPSHOT_DIR", str(tmp_path))
    monkeypatch.setenv("MARKET_MONITOR_MIIT_FILE", str(tmp_path / "product_master.json"))
    (tmp_path / "product_master.json").write_text(json.dumps([passenger("413", "2026-11-03")]))

    def unavailable():
        raise ValueError("registry 缺失")

    monkeypatch.setattr(cli, "build_insurance", unavailable)
    assert cli.refresh("all") == 1
    assert json.loads((tmp_path / "insurance.json").read_bytes()) == original
    assert json.loads((tmp_path / "miit.json").read_bytes())["latest_month"] == "2026-11"
