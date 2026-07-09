"""
volc_search_daily 集成测试 — mock Volc Search API，验证全链路输出 v2。
Output paths via output_paths.py.
"""

import json, os, sys, shutil
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from auto_launch.src.volc_search_daily import run_pipeline
from auto_launch.src import output_paths

TEST_DATE = "2026-07-02"

_URL_COUNTER = [0]

def _mock_search_success(query, limit=10):
    _URL_COUNTER[0] += 1
    base = _URL_COUNTER[0] * 100
    return {
        "query": query, "status": "success", "result_count": 2,
        "results": [
            {"title": f"R1 {query}", "url": f"https://example.com/{base+1}", "snippet": "S1",
             "source": "汽车之家", "publish_time": "2026-07-01"},
            {"title": f"R2 {query}", "url": f"https://example.com/{base+2}", "snippet": "S2",
             "source": "懂车帝", "publish_time": "2026-06-30"},
        ],
        "raw_response": {}, "retrieved_at": "2026-07-02T12:00:00", "attempts": 1,
    }

def _resolve_run_mode():
    """Determine the actual run_mode from a dry-run of the pipeline."""
    result = run_pipeline("看看极氪最近 7 天都有什么动作", TEST_DATE, dry_run=True)
    intent = result[0]
    label = intent["targets"][0].get("brand", "未知")
    return output_paths.run_mode_brand_watch(label)

RUN_MODE = None  # lazy init

def _get_run_mode():
    global RUN_MODE
    if RUN_MODE is None:
        RUN_MODE = _resolve_run_mode()
    return RUN_MODE

def _outdir():
    return output_paths.search_dir(TEST_DATE, _get_run_mode())

def _clean_output():
    d = output_paths.run_dir(TEST_DATE, _get_run_mode())
    if d.exists():
        shutil.rmtree(d.parent)


class TestDryRun:
    def setup_method(self):
        _clean_output()

    def test_dry_run_produces_plan(self):
        """dry-run 生成 plan.json"""
        result = run_pipeline("看看极氪最近 7 天都有什么动作", TEST_DATE, dry_run=True)
        intent, config, budget, plan = result[0], result[1], result[2], result[3]
        assert intent is not None and config is not None and budget is not None and plan is not None

        sd = _outdir()
        fnames = [f.name for f in sd.iterdir()]
        assert "plan.json" in fnames, f"Missing plan.json in {fnames}"
        qc = sum(len(t.get("queries", [])) for t in plan.get("targets", []))
        assert qc == 5, f"Expected 5 queries for standard_scan, got {qc}"
        print(f"  [PASS] dry_run: {fnames}, queries={qc}")

    def test_dry_run_lite_scan_3_queries(self):
        result = run_pipeline("看看极氪最近 7 天都有什么动作", TEST_DATE, dry_run=True, query_profile="lite_scan")
        plan = result[3]
        qc = sum(len(t.get("queries", [])) for t in plan.get("targets", []))
        assert qc == 3, f"Expected 3 for lite_scan, got {qc}"
        print(f"  [PASS] dry_run lite_scan: {qc} queries")

    def test_dry_run_deep_scan_8_queries(self):
        result = run_pipeline("看看极氪最近 7 天都有什么动作", TEST_DATE, dry_run=True, query_profile="deep_scan")
        plan = result[3]
        qc = sum(len(t.get("queries", [])) for t in plan.get("targets", []))
        assert qc == 8, f"Expected 8 for deep_scan, got {qc}"
        print(f"  [PASS] dry_run deep_scan: {qc} queries")


class TestLiveRun:
    def setup_method(self):
        _clean_output()
        _URL_COUNTER[0] = 0

    @patch("auto_launch.src.volc_search_daily.VolcSearchClient")
    def test_live_run_produces_all_files(self, MockClient):
        MockClient.return_value.search.side_effect = _mock_search_success
        result = run_pipeline("看看极氪最近 7 天都有什么动作", TEST_DATE, dry_run=False)
        intent, config, budget, plan, raw, norm, audit = result

        sd = _outdir()
        fnames = [f.name for f in sd.iterdir()]
        expected = {"plan.json", "raw.json", "normalized.json", "audit.json"}
        assert expected.issubset(set(fnames)), f"Missing: {expected - set(fnames)}"
        assert raw is not None and norm is not None and audit is not None
        print(f"  [PASS] live_run {len(fnames)} files")

    @patch("auto_launch.src.volc_search_daily.VolcSearchClient")
    def test_audit_has_budget_and_stages(self, MockClient):
        MockClient.return_value.search.side_effect = _mock_search_success
        run_pipeline("看看极氪最近 7 天都有什么动作", TEST_DATE, dry_run=False)
        sd = _outdir()
        with open(sd / "audit.json") as f:
            data = json.load(f)
        assert "budget" in data, "Missing budget in audit"
        assert data["budget"]["profile"] == "standard_scan"
        assert data["budget"]["query_count_planned"] == 5
        assert "stages" in data, "Missing stages in audit"
        assert "scout" in data["stages"]
        assert "refine" in data["stages"]
        print(f"  [PASS] audit has budget+stages: profile={data['budget']['profile']}")

    @patch("auto_launch.src.volc_search_daily.VolcSearchClient")
    def test_audit_has_cache_fields(self, MockClient):
        MockClient.return_value.search.side_effect = _mock_search_success
        run_pipeline("看看极氪最近 7 天都有什么动作", TEST_DATE, dry_run=False, disable_cache=True)
        sd = _outdir()
        with open(sd / "audit.json") as f:
            data = json.load(f)
        assert "api_call_count" in data["budget"]
        assert "cache_hit_count" in data["budget"]
        print(f"  [PASS] audit cache fields: api_calls={data['budget']['api_call_count']}")

    @patch("auto_launch.src.volc_search_daily.VolcSearchClient")
    def test_partial_failure_does_not_abort(self, MockClient):
        def _mock_partial(query, limit=10):
            if "高管" in query:
                return {"query": query, "status": "error", "error": "fail", "result_count": 0, "results": []}
            return _mock_search_success(query, limit)
        MockClient.return_value.search.side_effect = _mock_partial

        result = run_pipeline("看看极氪最近 7 天都有什么动作", TEST_DATE, dry_run=False,
                              query_profile="deep_scan")
        raw = result[4]
        audit = result[6]

        sd = _outdir()
        with open(sd / "raw.json") as f:
            raw_data = json.load(f)
        assert len(raw_data.get("errors", [])) > 0
        assert audit["budget"]["query_count_executed"] == 8
        print(f"  [PASS] partial failure: {len(raw_data.get('errors',[]))} errors in deep_scan=8 queries")
