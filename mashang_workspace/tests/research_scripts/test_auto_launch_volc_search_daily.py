"""
volc_search_daily 集成测试 — mock Volc Search API，验证全链路输出。

测试覆盖:
  - dry-run 只生成前 3 个文件
  - live-run (mock) 生成 6 个文件
  - 单条 query 失败不中断整体任务
  - search_audit 能统计 failed_queries
  - normalized 结构符合规范
  - raw 结构包含 envelope
"""

import json, os, sys, shutil
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research_scripts.auto_launch.volc_search_daily import run_pipeline, OUTPUT_BASE


TEST_DATE = "2026-07-02"
OUTDIR = OUTPUT_BASE / TEST_DATE / "brand_watch"


def _mock_search_success(query, limit=10):
    """模拟成功的 Volc Search 响应"""
    return {
        "query": query,
        "status": "success",
        "result_count": 2,
        "results": [
            {"title": f"Result 1 for {query}", "url": "https://example.com/1", "snippet": "Snippet 1",
             "source": "汽车之家", "publish_time": "2026-07-01"},
            {"title": f"Result 2 for {query}", "url": "https://example.com/2", "snippet": "Snippet 2",
             "source": "懂车帝", "publish_time": "2026-06-30"},
        ],
        "raw_response": {"status": 200},
        "retrieved_at": "2026-07-02T12:00:00",
        "attempts": 1,
    }


def _mock_search_partial_failure(query, limit=10):
    """模拟部分失败 — 以 '高管' 的 query 失败"""
    if "高管" in query:
        return {
            "query": query,
            "status": "error",
            "error": "Rate limit exceeded",
            "result_count": 0,
            "results": [],
            "retrieved_at": "2026-07-02T12:00:00",
            "attempts": 3,
        }
    return _mock_search_success(query, limit)


def _clean_output():
    if OUTDIR.exists():
        shutil.rmtree(OUTDIR.parent)
    OUTDIR.mkdir(parents=True, exist_ok=True)


class TestDryRun:
    def setup_method(self):
        _clean_output()

    def test_dry_run_produces_three_files(self):
        """dry-run 只生成前 3 个文件"""
        intent, config, plan, raw, norm, audit = run_pipeline(
            request="看看极氪最近 7 天都有什么动作",
            monitor_date=TEST_DATE,
            dry_run=True,
        )
        assert intent is not None
        assert config is not None
        assert plan is not None
        assert raw is None
        assert norm is None
        assert audit is None

        fnames = [f.name for f in OUTDIR.iterdir()]
        assert sorted(fnames) == sorted(["search_intent.json", "search_task_config.json", "query_plan.json"]), \
            f"Expected 3 files, got {fnames}"
        print(f"  [PASS] dry_run: {fnames}")


class TestLiveRun:
    def setup_method(self):
        _clean_output()

    @patch("research_scripts.auto_launch.volc_search_daily.VolcSearchClient")
    def test_live_run_produces_six_files(self, MockClient):
        """live-run 生成全部 6 个文件"""
        MockClient.return_value.search.side_effect = _mock_search_success
        intent, config, plan, raw, norm, audit = run_pipeline(
            request="看看极氪最近 7 天都有什么动作",
            monitor_date=TEST_DATE,
            dry_run=False,
        )
        assert raw is not None
        assert norm is not None
        assert audit is not None

        fnames = [f.name for f in OUTDIR.iterdir()]
        expected = {"search_intent.json", "search_task_config.json", "query_plan.json",
                     "search_results.raw.json", "search_results.normalized.json", "search_audit.json"}
        assert expected.issubset(set(fnames)), f"Missing. Got: {fnames}"
        print(f"  [PASS] live_run 6 files: {sorted(fnames)}")

    @patch("research_scripts.auto_launch.volc_search_daily.VolcSearchClient")
    def test_raw_envelope_structure(self, MockClient):
        """raw.json envelope 结构验证"""
        MockClient.return_value.search.side_effect = _mock_search_success
        run_pipeline("看看极氪最近 7 天都有什么动作", TEST_DATE, dry_run=False)
        with open(OUTDIR / "search_results.raw.json") as f:
            data = json.load(f)

        assert data["task_name"] == "auto_launch_volc_search"
        assert data["mode"] == "brand_watch"
        assert data["monitor_date"] == TEST_DATE
        assert "user_request" in data
        assert data["query_count"] == 8
        assert isinstance(data["results"], list)
        assert isinstance(data["errors"], list)
        assert len(data["results"]) == 8
        print(f"  [PASS] raw envelope OK ({len(data['results'])} results)")

    @patch("research_scripts.auto_launch.volc_search_daily.VolcSearchClient")
    def test_normalized_structure(self, MockClient):
        """normalized.json items 字段验证"""
        MockClient.return_value.search.side_effect = _mock_search_success
        run_pipeline("看看极氪最近 7 天都有什么动作", TEST_DATE, dry_run=False)
        with open(OUTDIR / "search_results.normalized.json") as f:
            data = json.load(f)

        assert "items" in data
        assert data["total"] == 16  # 8 queries × 2 results each
        for item in data["items"]:
            assert all(k in item for k in ("query", "target_id", "title", "url",
                                           "snippet", "source_tier_guess", "raw_rank"))
        print(f"  [PASS] normalized: {data['total']} items, all fields present")

    @patch("research_scripts.auto_launch.volc_search_daily.VolcSearchClient")
    def test_audit_structure(self, MockClient):
        """audit.json 字段验证"""
        MockClient.return_value.search.side_effect = _mock_search_success
        run_pipeline("看看极氪最近 7 天都有什么动作", TEST_DATE, dry_run=False)
        with open(OUTDIR / "search_audit.json") as f:
            data = json.load(f)

        required = ["mode", "monitor_date", "user_request", "query_count",
                     "target_count", "result_count_raw", "result_count_normalized",
                     "zero_result_queries", "failed_queries",
                     "source_tier_distribution", "coverage_by_event_type", "coverage_by_target"]
        for field in required:
            assert field in data, f"Missing: {field}"
        assert data["query_count"] == 8
        assert data["result_count_raw"] == 16
        assert data["result_count_normalized"] == 16
        print(f"  [PASS] audit: {len(required)} fields OK")

    @patch("research_scripts.auto_launch.volc_search_daily.VolcSearchClient")
    def test_partial_failure_does_not_abort(self, MockClient):
        """单条失败不中断，audit 记录 failed_queries"""
        MockClient.return_value.search.side_effect = _mock_search_partial_failure
        run_pipeline("看看极氪最近 7 天都有什么动作", TEST_DATE, dry_run=False)

        with open(OUTDIR / "search_results.raw.json") as f:
            raw_data = json.load(f)
        with open(OUTDIR / "search_audit.json") as f:
            audit_data = json.load(f)

        assert len(raw_data["errors"]) > 0
        assert len(audit_data["failed_queries"]) > 0
        statuses = {r.get("status") for r in raw_data["results"]}
        assert "success" in statuses
        assert "error" in statuses
        print(f"  [PASS] partial failure: {len(raw_data['errors'])} errors, "
              f"{len(audit_data['failed_queries'])} in audit, statuses={statuses}")
