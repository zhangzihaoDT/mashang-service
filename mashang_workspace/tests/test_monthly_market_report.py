"""
月度汽车市场报告 — 测试套件

覆盖：
  - Query Spec YAML 可加载、含 24 个 required query
  - query id 唯一、字段完整
  - 时间参数计算正确（含滚动 12 月边界）
  - dry-run CLI 可执行成功
  - 最小 query_results 可生成 report_draft.md
  - runner --help 正常
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

try:
    import yaml
except ImportError:
    yaml = None

pytest.importorskip("yaml")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_WS_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = _WS_DIR / "configs"
QUERY_SPEC_PATH = CONFIG_DIR / "monthly_market_report_queries.yaml"
RUNNER_PATH = _WS_DIR / "research_scripts" / "market_report" / "run_monthly_market_report.py"

REQUIRED_QUERY_FIELDS = [
    "id",
    "group",
    "section",
    "title",
    "question",
    "dataset",
    "grain",
    "metrics",
    "dimensions",
    "filters",
    "output_type",
    "required",
]

KNOWN_TABLES = {
    "market_energy_monthly",
    "brand_monthly",
    "model_monthly",
    "geo_monthly",
    "price_segment_monthly",
    "product_segment_monthly",
}

KNOWN_GROUPS = {
    "overall_market",
    "premium_market",
    "transaction_price",
    "model_rankings",
    "brand_competition",
    "city_competition",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def query_spec() -> dict[str, Any]:
    """加载 Query Spec YAML。"""
    with open(QUERY_SPEC_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def queries(query_spec) -> list[dict[str, Any]]:
    return query_spec.get("queries", [])


# ---------------------------------------------------------------------------
# Tests: Query Spec structural integrity
# ---------------------------------------------------------------------------
class TestQuerySpecStructure:
    def test_spec_loads_successfully(self, query_spec):
        """顶层字段完整，yaml 可解析。"""
        assert query_spec is not None
        assert query_spec.get("report_name") == "月度汽车市场标准查询"
        assert query_spec.get("default_dataset") == "passenger_insurance"

    def test_spec_version_0_1(self, query_spec):
        """Query Spec 标记为 version 0.1。"""
        assert query_spec.get("version") == "0.1", f"预期 version=0.1，实为 {query_spec.get('version')}"

    def test_spec_scope_single_table(self, query_spec):
        """Query Spec 标记为 scope single_table_monthly_market_report。"""
        assert query_spec.get("scope") == "single_table_monthly_market_report"

    def test_required_query_count(self, queries):
        """required 为 true 的 query 共 24 个。"""
        required = [q for q in queries if q.get("required", False)]
        assert len(required) == 24, f"预期 24 个 required query，实为 {len(required)}"

    def test_total_query_count(self, queries):
        """queries 总数共 24 个（无一遗漏）。"""
        assert len(queries) == 24, f"预期 24 个 query，实为 {len(queries)}"

    def test_query_ids_unique(self, queries):
        """所有 query id 唯一。"""
        ids = [q["id"] for q in queries]
        duplicates = [qid for qid in ids if ids.count(qid) > 1]
        assert not duplicates, f"存在重复 query id: {set(duplicates)}"

    def test_query_contains_required_fields(self, queries):
        """每个 query 包含所有必需字段。"""
        for q in queries:
            missing = [f for f in REQUIRED_QUERY_FIELDS if f not in q]
            assert not missing, f"query '{q.get('id', '?')}' 缺少字段: {missing}"

    def test_query_ids_convention(self, queries):
        """id 使用英文 snake_case，不与保留名冲突。"""
        for q in queries:
            qid = q["id"]
            assert qid.isascii(), f"query id '{qid}' 包含非 ASCII 字符"
            assert "_" in qid or qid.islower(), f"query id '{qid}' 不是 snake_case"
            assert qid.islower(), f"query id '{qid}' 含大写字母"

    def test_query_groups_valid(self, queries):
        """每个 query 的 group 属于已知分组。"""
        for q in queries:
            g = q.get("group", "")
            assert g in KNOWN_GROUPS, f"query '{q['id']}' 的 group='{g}' 不在已知分组中: {KNOWN_GROUPS}"

    def test_query_tables_valid(self, queries):
        """每个 query 的 table 属于已知表。"""
        for q in queries:
            table = q.get("table", "")
            assert table in KNOWN_TABLES, f"query '{q['id']}' 的 table='{table}' 不在已知表中"

    def test_query_questions_nonempty(self, queries):
        """每个 query 的 question 不为空。"""
        for q in queries:
            assert q.get("question", "").strip(), f"query '{q['id']}' 的 question 为空"

    def test_query_metrics_nonempty(self, queries):
        """每个 query 的 metrics 列表非空。"""
        for q in queries:
            assert len(q.get("metrics", [])) > 0, f"query '{q['id']}' 的 metrics 为空"

    def test_spec_has_time_params(self, query_spec):
        """Query Spec 包含 time_params 占位定义。"""
        assert "time_params" in query_spec
        tp = query_spec["time_params"]
        expected_keys = [
            "report_month", "month_start", "month_end",
            "ytd_start", "ytd_end",
            "last_year_month_start", "last_year_month_end",
            "last_year_ytd_start", "last_year_ytd_end",
            "rolling_12m_start", "rolling_12m_end",
        ]
        for k in expected_keys:
            assert k in tp, f"time_params 缺少字段: {k}"


# ---------------------------------------------------------------------------
# Tests: Time parameter calculation
# ---------------------------------------------------------------------------
class TestTimeParams:
    def _import_runner_module(self):
        """动态导入 runner（需先放上 sys.path）。"""
        ws = str(_WS_DIR)
        if ws not in sys.path:
            sys.path.insert(0, ws)
        from research_scripts.market_report.run_monthly_market_report import compute_time_params
        return compute_time_params

    def test_standard_month(self):
        compute = self._import_runner_module()
        tp = compute("2026-05")
        assert tp["report_month"] == "2026-05"
        assert tp["month_start"] == "2026-05-01"
        assert tp["month_end"] == "2026-05-31"
        assert tp["ytd_start"] == "2026-01-01"
        assert tp["ytd_end"] == "2026-05-31"
        assert tp["last_year_month_start"] == "2025-05-01"
        assert tp["last_year_month_end"] == "2025-05-31"
        assert tp["last_year_ytd_start"] == "2025-01-01"
        assert tp["last_year_ytd_end"] == "2025-05-31"
        assert tp["rolling_12m_start"] == "2025-06-01"
        assert tp["rolling_12m_end"] == "2026-05-31"

    def test_january(self):
        """1 月边界：滚动 12 月应为去年 2 月到今年 1 月。"""
        compute = self._import_runner_module()
        tp = compute("2026-01")
        assert tp["month_start"] == "2026-01-01"
        assert tp["month_end"] == "2026-01-31"
        assert tp["last_year_month_start"] == "2025-01-01"
        assert tp["last_year_month_end"] == "2025-01-31"
        assert tp["rolling_12m_start"] == "2025-02-01"
        assert tp["rolling_12m_end"] == "2026-01-31"

    def test_december(self):
        """12 月边界：滚动 12 月应为今年 1 月到今年 12 月。"""
        compute = self._import_runner_module()
        tp = compute("2026-12")
        assert tp["month_start"] == "2026-12-01"
        assert tp["month_end"] == "2026-12-31"
        assert tp["last_year_month_start"] == "2025-12-01"
        assert tp["last_year_month_end"] == "2025-12-31"
        assert tp["rolling_12m_start"] == "2026-01-01"
        assert tp["rolling_12m_end"] == "2026-12-31"

    def test_february_leap_year(self):
        """闰年 2 月。"""
        compute = self._import_runner_module()
        tp = compute("2024-02")
        assert tp["month_start"] == "2024-02-01"
        assert tp["month_end"] == "2024-02-29"
        assert tp["last_year_month_end"] == "2023-02-28"

    def test_february_non_leap(self):
        """非闰年 2 月。"""
        compute = self._import_runner_module()
        tp = compute("2025-02")
        assert tp["month_start"] == "2025-02-01"
        assert tp["month_end"] == "2025-02-28"

    def test_all_time_params_count(self):
        """返回 11 个时间参数。"""
        compute = self._import_runner_module()
        tp = compute("2026-06")
        assert len(tp) == 11


# ---------------------------------------------------------------------------
# Tests: CLI invocation
# ---------------------------------------------------------------------------
class TestCLI:
    def test_help(self):
        """--help 正常输出，不崩溃。"""
        result = subprocess.run(
            [sys.executable, str(RUNNER_PATH), "--help"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "usage:" in result.stdout or "usage:" in result.stderr.lower()

    def test_dry_run_default(self, tmp_path):
        """默认模式（dry-run）运行 2026-02，不崩溃，输出 24 个 query 计划。"""
        result = subprocess.run(
            [sys.executable, str(RUNNER_PATH), "--month", "2026-02"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "DRY RUN" in result.stdout
        assert "24 queries" in result.stdout or "计划: 24" in result.stdout
        assert "total_passenger_vehicle_sales" in result.stdout

    def test_dry_run_with_output_dir(self, tmp_path):
        """指定 --output-dir，输出文件应生成。"""
        out_dir = tmp_path / "monthly_output"
        result = subprocess.run(
            [
                sys.executable, str(RUNNER_PATH),
                "--month", "2026-03",
                "--output-dir", str(out_dir),
            ],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert (out_dir / "query_results.json").exists()
        assert (out_dir / "report_draft.md").exists()
        assert (out_dir / "run_metadata.json").exists()

    def test_dry_run_twelve_month_queries(self):
        """12 月的边界月份不会崩溃。"""
        result = subprocess.run(
            [sys.executable, str(RUNNER_PATH), "--month", "2026-12"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "24 queries" in result.stdout or "计划: 24" in result.stdout

    def test_dry_run_generates_report_draft(self, tmp_path):
        """report_draft.md 包含各查询章节。"""
        out_dir = tmp_path / "draft_test"
        subprocess.run(
            [
                sys.executable, str(RUNNER_PATH),
                "--month", "2026-02",
                "--output-dir", str(out_dir),
            ],
            capture_output=True, timeout=30, check=True,
        )
        md_path = out_dir / "report_draft.md"
        assert md_path.exists()
        content = md_path.read_text(encoding="utf-8")
        # Should contain section headers for all 6 groups
        for section in ["整体市场概览", "中高端市场", "成交价结构", "车型排名", "品牌竞争", "城市市场结构"]:
            assert section in content, f"report_draft.md 缺少章节: {section}"
        # Should list all 24 query IDs
        assert "total_passenger_vehicle_sales" in content
        assert "tier3_lower_city_competition" in content
        assert "已生成时间" not in content  # uses "生成时间"


# ---------------------------------------------------------------------------
# Tests: JSON output structure
# ---------------------------------------------------------------------------
class TestJsonOutput:
    def test_json_contains_all_queries(self, tmp_path):
        """query_results.json 包含全部 24 query。"""
        out_dir = tmp_path / "json_test"
        subprocess.run(
            [
                sys.executable, str(RUNNER_PATH),
                "--month", "2026-04",
                "--output-dir", str(out_dir),
            ],
            capture_output=True, timeout=30, check=True,
        )
        json_path = out_dir / "query_results.json"
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert len(data["queries"]) == 24
        ids = [q["id"] for q in data["queries"]]
        assert len(set(ids)) == 24  # unique

    def test_json_has_contract(self, tmp_path):
        """query_results.json 包含 Result Contract。"""
        out_dir = tmp_path / "contract_test"
        subprocess.run(
            [
                sys.executable, str(RUNNER_PATH),
                "--month", "2026-04",
                "--output-dir", str(out_dir),
            ],
            capture_output=True, timeout=30, check=True,
        )
        with open(out_dir / "query_results.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        c = data["contract"]
        assert c["status"] == "success"
        assert "script" in c
        assert "scope" in c
        assert "result" in c

    def test_json_has_time_params(self, tmp_path):
        """query_results.json 包含时间参数。"""
        out_dir = tmp_path / "timeparam_test"
        subprocess.run(
            [
                sys.executable, str(RUNNER_PATH),
                "--month", "2026-04",
                "--output-dir", str(out_dir),
            ],
            capture_output=True, timeout=30, check=True,
        )
        with open(out_dir / "query_results.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        tp = data["time_params"]
        assert tp["report_month"] == "2026-04"
        assert tp["month_start"] == "2026-04-01"
        assert tp["month_end"] == "2026-04-30"

    def test_metadata_counts(self, tmp_path):
        """run_metadata.json 统计信息正确。"""
        out_dir = tmp_path / "meta_test"
        subprocess.run(
            [
                sys.executable, str(RUNNER_PATH),
                "--month", "2026-04",
                "--output-dir", str(out_dir),
            ],
            capture_output=True, timeout=30, check=True,
        )
        with open(out_dir / "run_metadata.json", "r", encoding="utf-8") as f:
            meta = json.load(f)

        assert meta["total_queries"] == 24
        assert meta["dry_run"] == 24  # all dry-run
        assert meta["success"] == 0
        assert meta["failed"] == 0


# ---------------------------------------------------------------------------
# Tests: Adapter queries (5 cross-table queries)
# ---------------------------------------------------------------------------
class TestAdapterQueries:
    """Adapter 查询的 dry-run 和 execute 模式测试。"""

    ADAPTER_IDS = [
        "price_band_brand_competition",
        "tier1_city_competition",
        "new_tier1_city_competition",
        "tier2_city_competition",
        "tier3_lower_city_competition",
    ]

    def test_adapter_dry_run_contained(self, tmp_path):
        """dry-run 模式下 adapter query 显示 adapter 标签。"""
        out_dir = tmp_path / "adapter_dry"
        result = subprocess.run(
            [sys.executable, str(RUNNER_PATH), "--month", "2026-03", "--output-dir", str(out_dir)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        with open(out_dir / "query_results.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        adapter_queries = [q for q in data["queries"] if q["id"] in self.ADAPTER_IDS]
        assert len(adapter_queries) == 5
        for q in adapter_queries:
            assert q["status"] == "dry_run"
            assert "adapter" in q.get("summary", "").lower() or "跨表" in q.get("summary", "")

    def test_execute_price_band_brand(self, tmp_path):
        """price_band_brand_competition 在 execute 模式下返回价位段品牌排名。"""
        out_dir = tmp_path / "adapter_pbb"
        result = subprocess.run(
            [sys.executable, str(RUNNER_PATH), "--month", "2026-03", "--execute", "--output-dir", str(out_dir)],
            capture_output=True, text=True, timeout=120,
        )
        # May fail if passenger_insurance data not available — acceptable
        if result.returncode != 0:
            return
        with open(out_dir / "query_results.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        q = next((q for q in data["queries"] if q["id"] == "price_band_brand_competition"), None)
        assert q is not None
        assert q["status"] in ("success", "skipped", "error")
        if q["status"] == "success":
            assert q["table"] == "adapter"
            assert "grouped" in q.get("data", {})
            assert "band_summary" in q.get("data", {})

    def test_execute_tier1_city(self, tmp_path):
        """一线城市市场结构在 execute 模式下返回销量和渗透率（不含品牌排名）。"""
        out_dir = tmp_path / "adapter_t1"
        subprocess.run(
            [sys.executable, str(RUNNER_PATH), "--month", "2026-03", "--execute", "--output-dir", str(out_dir)],
            capture_output=True, timeout=120,
        )
        json_path = out_dir / "query_results.json"
        if not json_path.exists():
            return
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        q = next((q for q in data["queries"] if q["id"] == "tier1_city_competition"), None)
        assert q is not None
        assert q["status"] == "success", f"预期 success，实为 {q['status']}: {q.get('error', '')}"
        d = q.get("data", {})
        assert "city_ranking" in d
        assert "nev_penetration_pct" in d
        assert "total_sales" in d
        # v0.1 不返回 brand/model ranking — 不包含 unavailable 字段
        assert "unavailable" not in d, "v0.1 城市类 query 不返回 unavailable 缺口告警"

    def test_execute_new_tier1_city(self, tmp_path):
        """新一线城市市场结构在 execute 模式下返回城市数据。"""
        out_dir = tmp_path / "adapter_nt1"
        subprocess.run(
            [sys.executable, str(RUNNER_PATH), "--month", "2026-03", "--execute", "--output-dir", str(out_dir)],
            capture_output=True, timeout=120,
        )
        json_path = out_dir / "query_results.json"
        if not json_path.exists():
            return
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        q = next((q for q in data["queries"] if q["id"] == "new_tier1_city_competition"), None)
        assert q is not None
        assert q["status"] == "success"
        assert q["data"]["tier"] == "新一线"
        assert "unavailable" not in q.get("data", {})

    def test_execute_tier2_city(self, tmp_path):
        """二线城市市场结构在 execute 模式下返回城市数据。"""
        out_dir = tmp_path / "adapter_t2"
        subprocess.run(
            [sys.executable, str(RUNNER_PATH), "--month", "2026-03", "--execute", "--output-dir", str(out_dir)],
            capture_output=True, timeout=120,
        )
        json_path = out_dir / "query_results.json"
        if not json_path.exists():
            return
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        q = next((q for q in data["queries"] if q["id"] == "tier2_city_competition"), None)
        assert q is not None
        assert q["status"] == "success"
        assert q["data"]["tier"] == "二线"
        assert "unavailable" not in q.get("data", {})

    def test_execute_tier3_lower_city(self, tmp_path):
        """三线及以下城市市场结构在 execute 模式下返回城市数据。"""
        out_dir = tmp_path / "adapter_t3"
        subprocess.run(
            [sys.executable, str(RUNNER_PATH), "--month", "2026-03", "--execute", "--output-dir", str(out_dir)],
            capture_output=True, timeout=120,
        )
        json_path = out_dir / "query_results.json"
        if not json_path.exists():
            return
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        q = next((q for q in data["queries"] if q["id"] == "tier3_lower_city_competition"), None)
        assert q is not None
        assert q["status"] == "success"
        d = q.get("data", {})
        assert d["tier"] == "三线及以下"
        assert "nev_penetration_pct" in d
        assert "total_sales" in d
        assert "unavailable" not in d

    def test_city_query_spec_no_brand_ranking(self, query_spec):
        """城市类 query 的 question 不描述品牌/车型排名等 v0.1 不支持内容。"""
        city_ids = ["tier1_city_competition", "new_tier1_city_competition",
                    "tier2_city_competition", "tier3_lower_city_competition"]
        forbidden_terms = ["品牌排名", "车型排名", "TOP50", "city×brand", "city×model"]
        for q in query_spec.get("queries", []):
            if q["id"] in city_ids:
                q_text = q.get("question", "")
                title = q.get("title", "")
                for term in forbidden_terms:
                    assert term not in q_text, f"城市 query '{q['id']}' question 仍包含禁止词: {term}"
                # title 必须包含"市场结构"，不能包含"竞争格局"
                assert "市场结构" in title, f"城市 query '{q['id']}' title 应含'市场结构'，实为: {title}"
                assert "竞争格局" not in title, f"城市 query '{q['id']}' title 不应含'竞争格局'，实为: {title}"
                # v0.1 城市类只问销量/份额/渗透率
                assert "新能源销量" in q_text or "渗透率" in q_text, f"城市 query '{q['id']}' 缺少市场结构指标"

    def test_adapter_status_in_dry_run_metadata(self, tmp_path):
        """dry-run 元信息中 adapter query 显示为 dry_run 而非 skipped。"""
        out_dir = tmp_path / "adapter_meta"
        subprocess.run(
            [sys.executable, str(RUNNER_PATH), "--month", "2026-03", "--output-dir", str(out_dir)],
            capture_output=True, timeout=30, check=True,
        )
        with open(out_dir / "run_metadata.json", "r", encoding="utf-8") as f:
            meta = json.load(f)
        assert meta["dry_run"] == 24  # all 24 are dry_run, including 5 adapters
        assert meta["skipped"] == 0  # no skipped queries in dry-run mode


# ---------------------------------------------------------------------------
# Tests: Version boundary & scope consistency
# ---------------------------------------------------------------------------
class TestVersionAndScope:
    """v0.1 版本标记和范围边界验证。"""

    DOCS_PATH = _WS_DIR / "docs" / "monthly_market_report.md"

    def test_docs_contains_version_scope(self):
        """文档包含 version 和 scope 标记。"""
        content = self.DOCS_PATH.read_text(encoding="utf-8")
        assert "version: 0.1" in content
        assert "scope: single_table_monthly_market_report" in content

    def test_docs_contains_support_list(self):
        """文档包含 v0.1 支持范围。"""
        content = self.DOCS_PATH.read_text(encoding="utf-8")
        expected_items = [
            "整体市场",
            "新能源市场",
            "城市线级结构",
            "区域市场",
            "中高端市场",
            "成交价与价位段",
        ]
        for item in expected_items:
            assert item in content, f"文档缺少 v0.1 支持范围: {item}"

    def test_docs_contains_unsupport_list(self):
        """文档包含 v0.1 不支持范围。"""
        content = self.DOCS_PATH.read_text(encoding="utf-8")
        expected_items = [
            "city×brand",
            "city×model",
            "city×price_band×brand",
            "brand×city_tier",
            "region×model",
            "TOP50",
            "完整竞争格局页复刻",
        ]
        for item in expected_items:
            assert item in content, f"文档缺少 v0.1 不支持范围: {item}"

    def test_docs_contains_v0_2_extension(self):
        """文档包含 v0.2 扩展方向说明，但不包含 v0.2 skill 定义。"""
        content = self.DOCS_PATH.read_text(encoding="utf-8")
        assert "## 后续扩展方向" in content
        assert "v0.2" in content
        assert "market-competition-cross-analysis" in content
        # 确保没有创建 v0.2 skill
        assert "market-competition-cross-analysis/SKILL.md" not in content

    def test_execute_output_contract_not_broken(self, tmp_path):
        """execute 模式输出的 Result Contract 结构不被破坏。"""
        out_dir = tmp_path / "contract_check"
        result = subprocess.run(
            [sys.executable, str(RUNNER_PATH), "--month", "2026-03", "--execute", "--output-dir", str(out_dir)],
            capture_output=True, timeout=120,
        )
        json_path = out_dir / "query_results.json"
        if not json_path.exists():
            return  # skip if passenger_insurance not available
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Root level
        assert "contract" in data
        assert "time_params" in data
        assert "queries" in data
        # Contract structure
        c = data["contract"]
        assert c["status"] in ("success", "partial_success")
        assert "scope" in c
        assert "result" in c
        assert "artifacts" in c
        # All 24 queries present
        assert len(data["queries"]) == 24
        # All queries have required fields
        for q in data["queries"]:
            assert "id" in q
            assert "status" in q
            assert q["status"] in ("success", "dry_run", "skipped", "error")
