"""CPCA poster Job checks using a v1 fixture and a stub image response."""

import base64
import hashlib
import json
from argparse import Namespace
from datetime import date
from io import BytesIO

import pytest
from PIL import Image

from jobs.adapter import load_jobs, run_job
from jobs.production import JobLock
from workspace.business_scripts import cpca_market_retail_poster as poster


DATE = "2026-11-22"
REDRAW = "a" * 32


@pytest.fixture
def job(tmp_path, monkeypatch):
    source = tmp_path / "briefing.v1.json"
    monkeypatch.setenv("MASHANG_DATA_CPCA_BRIEFING", str(source))
    monkeypatch.setattr(poster, "ROOT", tmp_path)
    monkeypatch.setattr(poster, "OUTPUT", tmp_path / "formal")
    monkeypatch.setattr(poster, "LOGS", tmp_path / "jobs")
    monkeypatch.setattr(poster.generation, "api_key", lambda: "stub")

    def period(start):
        return {"start": start, "end": DATE, "days": (date.fromisoformat(DATE) - date.fromisoformat(start)).days + 1}

    estimate = {"value": 37.3, "yoy_pct": -25.0, "estimated": True, "unit": "万辆"}
    edition = {
        "edition": DATE,
        "period": period("2026-11-01"),
        "report_status": "preliminary",
        "source": {"publisher": "CPCA"},
        "sections": [
            {"key": "week", "period": period("2026-11-16"), "metrics": {"passenger_retail": estimate}},
            {"key": "year_to_date", "period": period("2026-01-01"),
             "metrics": {"nev_retail": {**estimate, "value": 957.0, "estimated": False, "yoy_pct": None}}},
        ],
    }
    export = {"contract": poster.cpca.CONTRACT, "schema_version": "1.0", "latest_edition": DATE,
              "source": {}, "generated_at": "2026-11-26T05:30:05Z", "editions": [edition]}
    source.write_text(json.dumps(export))
    return source, export, poster.EditionOutput(DATE)


def invoke(**kwargs):
    return poster.run(Namespace(**{"date": DATE, "mode": "render", "redraw": "none", "review": None, **kwargs}))


def stub_generation(monkeypatch, *, http_status=None):
    calls = []

    def generate(prompt, reference, attempt):
        calls.append(attempt)
        assert "37.3 万辆" in prompt
        assert reference.startswith(b"\x89PNG")
        if http_status is None:
            image = attempt / "poster.jpg"
            Image.new("RGB", poster.SIZE, "blue").save(image)
            response = {
                "status": "pending_visual_review",
                "actual_model_version": poster.generation.MODEL_ID,
                "image_path": str(image),
                "seconds": 1.2,
                "cost_usd": 0.03,
            }
        else:
            response = {"status": "failed", "http_status": http_status, "error": f"HTTP {http_status}"}
        poster._atomic_json(attempt / "generation.json", response)

    monkeypatch.setattr(poster.generation, "generate", generate)
    return calls


def review(pending, decision="approve", **overrides):
    fields = pending["result"]
    return invoke(**{
        "review": decision, "attempt": fields["attempt"], "sha256": fields["candidate_sha256"],
        "note": "测试用人工验收记录", **overrides,
    })


def test_preflight_omits_missing_metrics_and_sections(job, monkeypatch):
    _, export, output = job
    calls = stub_generation(monkeypatch)
    assert invoke(mode="dry-run", date="latest")["result"]["outcome"] == "preflight_passed"
    assert not calls
    assert [file.name for file in output.formal.iterdir()] == ["briefing.json"]
    saved = poster.read_json(output.briefing)
    assert saved["business"] == export["editions"][0]
    assert [section["key"] for section in saved["layout"]["sections"]] == ["week", "year_to_date"]
    assert saved["layout"]["sections"][1]["metrics"]["nev_retail"]["yoy_text"] is None
    assert saved["execution"]["actual_model"] is None


def test_month_opening_only_shows_week(job):
    source, export, output = job
    edition = export["editions"][0]
    edition["sections"][0]["period"] = edition["period"]
    source.write_text(json.dumps(export))
    assert invoke(mode="dry-run")["status"] == "success"
    assert [section["key"] for section in poster.read_json(output.briefing)["layout"]["sections"]] == ["week"]


def test_v12_prompt_copies_each_canonical_period(job):
    source, export, output = job
    edition = export["editions"][0]
    week, year = edition["sections"]
    month = {
        **week,
        "key": "month_to_date",
        "period": {"start": "2026-11-02", "end": DATE, "days": 21},
    }
    # Nonstandard start days reveal any attempt to rebuild dates from the cutoff.
    year["period"].update(start="2026-01-03", days=324)
    edition["sections"] = [week, month, year]
    source.write_text(json.dumps(export))

    assert invoke(mode="dry-run")["status"] == "success"
    source.unlink()
    report = poster.read_json(output.briefing)
    _, experimental_template, reference = poster.drawing.load_assets("V1.2")
    _, production_template, production_reference = poster.drawing.load_assets()
    prompt = poster.drawing.build_prompt(output.briefing, experimental_template)
    production_prompt = poster.drawing.build_prompt(output.briefing, production_template)
    assert [row["period"] for row in report["layout"]["sections"]] == [s["period"] for s in edition["sections"]]
    assert "只负责照录日期，不推导、重算、补齐或纠正起止日" in prompt
    assert "只负责照录日期" not in production_prompt
    assert reference == production_reference
    _, business_text = prompt.split("待排版内容\n", 1)
    assert '卡片「最新区间」 日期「11月16-22日」' in business_text
    assert '卡片「当月累计」 日期「11月2-22日」' in business_text
    assert '卡片「当年累计」 日期「1月3日-11月22日」' in business_text


def stub_native_response(monkeypatch, *, image_size=poster.SIZE):
    output = BytesIO()
    Image.new("RGB", image_size, "blue").save(output, format="PNG")
    body = json.dumps({
        "modelVersion": poster.generation.MODEL_ID,
        "candidates": [{"content": {"parts": [{"inlineData": {
            "mimeType": "image/png",
            "data": base64.b64encode(output.getvalue()).decode("ascii"),
        }}]}}],
    }).encode()
    requests = []

    class Response:
        status = 200

        def read(self):
            return body

    class Connection:
        def __init__(self, host, timeout):
            assert (host, timeout) == ("opencode.ai", 180)

        def request(self, method, route, *, body, headers):
            assert method == "POST" and route == poster.generation.ROUTE
            assert headers["Authorization"] == "Bearer stub"
            requests.append(body)

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(poster.generation, "HTTPSConnection", Connection)
    return requests


def test_fast_path_uses_one_briefing_and_repeats_identical_wire_bytes(job, monkeypatch):
    source, export, output = job
    requests = stub_native_response(monkeypatch)
    edition = export["editions"][0]
    week = edition["sections"][0]
    week["metrics"]["passenger_retail"]["value"] = 37.345
    source.write_text(json.dumps(export))
    pending = invoke()
    assert pending["result"]["outcome"] == "pending_review"
    attempt = output.latest()
    assert pending["result"]["review_briefing_path"] == str(attempt / "briefing.json")
    snapshot = output.snapshot(attempt)
    assert snapshot["business"] == edition
    assert snapshot["execution"]["request_sha256"] == hashlib.sha256(requests[0]).hexdigest()
    _, template, reference = poster.drawing.load_assets()
    prompt = poster.drawing.build_prompt(attempt / "briefing.json", template)
    assert "37.345 万辆" in prompt
    assert requests[0] == poster.generation.request_bytes(prompt, reference)

    # The export's object/section ordering and updated export timestamp are not drawing input.
    edition["sections"].reverse()
    export["generated_at"] = "2026-11-27T05:30:05Z"
    source.write_text(json.dumps(export, sort_keys=True))
    assert invoke(redraw=REDRAW)["result"]["outcome"] == "pending_review"
    assert len(requests) == 2 and requests[0] == requests[1]
    assert not output.image.exists()


def test_native_image_at_wrong_size_is_rejected_before_publication(job, monkeypatch):
    _, _, output = job
    requests = stub_native_response(monkeypatch, image_size=(64, 64))
    assert invoke()["result"]["outcome"] == "validation_failed"
    assert invoke()["result"]["outcome"] == "validation_failed"
    assert len(requests) == 1
    assert not output.image.exists()
    assert poster.read_json(output.briefing)["execution"]["failure_code"] == "validation_failed"


def test_missing_input_stops_before_spend(job, monkeypatch):
    source, export, output = job
    calls = stub_generation(monkeypatch)
    assert invoke(date="2020-01-01")["result"]["outcome"] == "preflight_failed"
    for section in export["editions"][0]["sections"]:
        section["metrics"] = {}
    source.write_text(json.dumps(export))
    assert invoke()["result"]["outcome"] == "preflight_failed"
    source.unlink()
    assert invoke()["result"]["outcome"] == "preflight_failed"
    assert not calls
    assert not output.formal.exists()


def test_missing_key_does_not_reserve_a_paid_attempt(job, monkeypatch):
    _, _, output = job
    calls = stub_generation(monkeypatch)

    def unavailable():
        raise ValueError("missing API key")

    monkeypatch.setattr(poster.generation, "api_key", unavailable)
    assert invoke()["result"]["outcome"] == "model_unavailable"
    assert not calls and output.latest() is None and not output.image.exists()


def test_model_api_failure_is_not_retried(job, monkeypatch):
    _, _, output = job
    calls = stub_generation(monkeypatch, http_status=503)
    for _ in range(2):
        assert invoke()["result"]["outcome"] == "model_unavailable"
    assert len(calls) == 1
    assert not output.image.exists()


def test_busy_blocks_concurrent_submission(job, monkeypatch):
    calls = stub_generation(monkeypatch)
    with JobLock(poster.ROOT, "fixture", "test", job=poster.JOB):
        assert invoke()["result"]["outcome"] == "busy"
    assert not calls


def test_uncertain_submission_is_never_replayed(job, monkeypatch):
    _, _, output = job
    calls = []

    def interrupted(prompt, reference, attempt):
        calls.append(attempt)
        poster._atomic_json(attempt / "generation.json", {"status": "submission_started"})

    monkeypatch.setattr(poster.generation, "generate", interrupted)
    assert invoke()["result"]["outcome"] == "submission_uncertain"
    assert invoke()["result"]["outcome"] == "submission_uncertain"
    assert len(calls) == 1 and not output.image.exists()


def test_pending_approval_reuse_and_rejected_redraw(job, monkeypatch):
    _, _, output = job
    calls = stub_generation(monkeypatch)

    pending = invoke()
    assert pending["status"] == "partial_success"
    assert "png" not in pending["artifacts"]
    assert invoke()["result"]["candidate_sha256"] == pending["result"]["candidate_sha256"]
    assert len(calls) == 1 and not output.image.exists()
    assert review(pending, sha256="0" * 64)["result"]["outcome"] == "validation_failed"
    assert review(pending)["result"]["outcome"] == "approved"
    with Image.open(output.image) as image:
        assert image.format == "PNG" and image.size == poster.SIZE
    with Image.open(calls[0] / "poster.jpg") as original, Image.open(output.image) as expected:
        assert original.tobytes() == expected.tobytes()
    formal = {path.name: path.read_bytes() for path in output.formal.iterdir()}
    assert set(formal) == {"briefing.json", "poster.png"}

    assert invoke()["result"]["outcome"] == "reused"
    assert invoke(mode="dry-run")["result"]["existing_approved"]
    pending = invoke(redraw=REDRAW)
    assert invoke(redraw=REDRAW)["result"]["outcome"] == "pending_review"
    reason = "实图的当年累计误用了当月累计起始日"
    rejection = review(pending, "reject", note=reason)["result"]
    assert rejection["outcome"] == "validation_failed" and rejection["summary"] == reason
    assert invoke(redraw=REDRAW)["result"]["outcome"] == "validation_failed"
    assert len(calls) == 2
    assert {path.name: path.read_bytes() for path in output.formal.iterdir()} == formal


def test_interrupted_publication_recovers_without_spend(job, monkeypatch):
    _, _, output = job
    calls = stub_generation(monkeypatch)
    pending = invoke()
    publish = poster.EditionOutput.publish

    def interrupted(self, attempt, snapshot):
        raise OSError("simulated interruption")

    monkeypatch.setattr(poster.EditionOutput, "publish", interrupted)
    assert review(pending)["result"]["outcome"] == "job_error"
    assert not output.image.exists()
    monkeypatch.setattr(poster.EditionOutput, "publish", publish)
    assert invoke()["result"]["outcome"] == "reused"
    assert output.image.exists() and len(calls) == 1


def test_registered_contract_rejects_bad_input():
    config = load_jobs()[poster.JOB]
    assert config["timeout_seconds"] == 240
    assert run_job(poster.JOB, {"model": "unapproved"})["status"] == "error"
    invalid_date = run_job(poster.JOB, {"date": "2026-02-30"})
    assert invalid_date["summary_json"]["result"]["outcome"] == "invalid_parameters"
    unpinned_redraw = run_job(poster.JOB, {"mode": "render", "redraw": REDRAW})
    assert unpinned_redraw["summary_json"]["result"]["outcome"] == "invalid_parameters"
