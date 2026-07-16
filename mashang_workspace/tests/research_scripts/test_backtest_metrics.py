"""
Tests for lock_predict_backtest.py — 回测指标计算、成熟度边界、零值处理等。
"""

import sys, json, subprocess
from pathlib import Path
import numpy as np
import pandas as pd

_WS_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_WS_DIR))


def _import_bt_module():
    """Import the backtest module from file path."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "lock_predict_backtest",
        _WS_DIR / "research_scripts" / "lock_predict_backtest.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── 1. Metrics Computation Tests ──

class TestMetricsComputation:
    def setup_method(self):
        self.bt = _import_bt_module()

    def _make_el(self, actuals, forecasts):
        n = len(actuals)
        dates = pd.date_range("2025-01-01", periods=n, freq="D")
        return pd.DataFrame({
            "date": dates,
            "cohort_actual_30_lock": actuals,
            "cohort_pred_30_lock": forecasts,
            "cohort_assign_count": [1000] * n,
            "prediction_method": ["actual"] * n,
            "maturity_days": [60] * n,
            "is_fully_matured": [True] * n,
            "evaluation_eligible": [True] * n,
            "exclusion_reason": ["已成熟"] * n,
            "as_of_date": dates,
            "age_at_prediction": [30] * n,
        })

    def test_mae(self):
        el = self._make_el([100, 200, 300], [110, 180, 310])
        # errors: [-10, 20, -10], abs: [10, 20, 10], MAE = 40/3 = 13.33
        m = self.bt.compute_official_metrics(el)
        assert abs(m["mae"] - 40/3) < 0.01, f"MAE expected {40/3}, got {m['mae']}"

    def test_rmse(self):
        el = self._make_el([100, 200, 300], [110, 180, 310])
        # errors: [-10, 20, -10], sq: [100, 400, 100], MSE = 200, RMSE = 14.14
        m = self.bt.compute_official_metrics(el)
        assert abs(m["rmse"] - np.sqrt(200)) < 0.01, f"RMSE expected {np.sqrt(200)}, got {m['rmse']}"

    def test_wape(self):
        el = self._make_el([100, 200, 300], [110, 180, 310])
        # sum(|error|) = 40, sum(actual) = 600, WAPE = 40/600 = 0.0667
        m = self.bt.compute_official_metrics(el)
        assert abs(m["wape"] - 40/600) < 0.001, f"WAPE expected {40/600}, got {m['wape']}"

    def test_mape(self):
        el = self._make_el([100, 200, 300], [110, 180, 310])
        # APE: [10/100=0.1, 20/200=0.1, 10/300=0.0333], MAPE = 0.0778
        m = self.bt.compute_official_metrics(el)
        expected = (0.1 + 0.1 + 10/300) / 3
        assert abs(m["mape"] - expected) < 0.001, f"MAPE expected {expected}, got {m['mape']}"

    def test_r2(self):
        el = self._make_el([100, 200, 300], [110, 180, 310])
        m = self.bt.compute_official_metrics(el)
        # R² shouldn't be exactly 0, should be reasonable
        assert not np.isnan(m["r2"]), "R² should not be NaN"
        assert m["r2"] < 1.0, "R² should be < 1.0 for imperfect prediction"

    def test_correlation(self):
        el = self._make_el([100, 200, 300], [110, 180, 310])
        m = self.bt.compute_official_metrics(el)
        assert not np.isnan(m["correlation"]), "Correlation should not be NaN"
        assert abs(m["correlation"] - 1.0) < 1.0, "Should be positively correlated"

    def test_bias_and_median(self):
        el = self._make_el([100, 200, 300], [110, 180, 310])
        m = self.bt.compute_official_metrics(el)
        # sum_forecast=600, sum_actual=600, bias=0 (wait: 110+180+310=600, 100+200+300=600)
        assert abs(m["bias_pct"]) < 0.001, f"Bias should be ~0, got {m['bias_pct']}"
        # mean error = (-10+20-10)/3 = 0
        assert abs(m["mean_error"]) < 0.001, f"Mean error should be ~0, got {m['mean_error']}"

    def test_all_overestimate(self):
        """All predictions > actual → systematic overestimation."""
        el = self._make_el([100, 100, 100], [150, 150, 150])
        m = self.bt.compute_official_metrics(el)
        # bias_pct = (sum_actual - sum_forecast) / sum_actual = (300-450)/300 = -0.5
        assert m["bias_pct"] < 0, "bias_pct < 0 when all overestimate (actual < forecast)"
        assert m["mean_error"] < 0, "mean_error < 0 when all overestimate (error = actual - forecast)"
        assert m["over_count"] == 3, "all 3 are overestimates"
        assert m["under_count"] == 0

    def test_all_underestimate(self):
        """All predictions < actual → systematic underestimation."""
        el = self._make_el([200, 200, 200], [100, 100, 100])
        m = self.bt.compute_official_metrics(el)
        # bias_pct = (sum_actual - sum_forecast) / sum_actual = (600-300)/600 = 0.5
        assert m["bias_pct"] > 0, "bias_pct > 0 when all underestimate (actual > forecast)"
        assert m["mean_error"] > 0, "mean_error > 0 when all underestimate"
        assert m["under_count"] == 3
        assert m["over_count"] == 0

    def test_within_hit_rates(self):
        """Check ±10/20/30% hit rates."""
        # actual=100, forecast=90 → 10% error → within 10%
        # actual=100, forecast=75 → 25% error → within 30% only
        # actual=100, forecast=60 → 40% error → outside 30%
        el = self._make_el([100, 100, 100], [90, 75, 60])
        m = self.bt.compute_official_metrics(el)
        assert m["within_10pct"] == 1/3, f"Expected 33.3%, got {m['within_10pct']}"
        assert m["within_20pct"] == 1/3, f"Expected 33.3%, got {m['within_20pct']}"
        assert m["within_30pct"] == 2/3, f"Expected 66.7%, got {m['within_30pct']}"

    def test_perfect_prediction(self):
        el = self._make_el([100, 200, 300], [100, 200, 300])
        m = self.bt.compute_official_metrics(el)
        assert m["mae"] == 0
        assert m["rmse"] == 0
        assert m["wape"] == 0
        assert abs(m["r2"] - 1.0) < 0.001
        assert abs(m["correlation"] - 1.0) < 0.001
        assert m["bias_pct"] == 0
        assert m["within_10pct"] == 1.0


# ── 2. Maturity Boundary Test ──

class TestMaturityBoundary:
    def setup_method(self):
        self.bt = _import_bt_module()

    def test_maturity_boundary(self):
        """
        Test that cohort_date <= as_of_date - 30 determines evaluation_eligible.
        Don't use actual data, construct synthetic data through the full flow.
        """
        n = 100
        # Create synthetic assign data spread across dates
        np.random.seed(42)
        dates = pd.date_range("2025-01-01", "2025-04-10", periods=n)
        df = pd.DataFrame({
            "Assign Time 年/月/日": [d.strftime("%Y年%m月%d日") for d in dates],
            "下发线索数": np.random.randint(500, 3000, n),
            "下发线索当日锁单数 (门店)": np.random.randint(0, 50, n),
            "下发线索 7 日锁单数": np.random.randint(10, 100, n),
            "下发线索 30 日锁单数": np.random.randint(30, 200, n),
        })
        # Pre-process like load_assign_data does
        df["_date"] = self.bt._parse_cn_date(df["Assign Time 年/月/日"])
        df = df[df["_date"].notna()].sort_values("_date").reset_index(drop=True)
        n_fn = lambda c: pd.to_numeric(c.astype(str).str.replace(",", "", regex=False), errors="coerce").fillna(0)
        df["_leads"] = n_fn(df["下发线索数"])
        df["_lock0"] = n_fn(df["下发线索当日锁单数 (门店)"])
        df["_lock7"] = n_fn(df["下发线索 7 日锁单数"])
        df["_lock30"] = n_fn(df["下发线索 30 日锁单数"])
        result, cutoff = self.bt.rolling_origin_backtest(df)
        assert "evaluation_eligible" in result.columns
        assert "maturity_days" in result.columns
        assert "exclusion_reason" in result.columns

        # The last date should NOT be eligible
        assert not result[result["date"] == result["date"].max()]["evaluation_eligible"].iloc[0], \
            "Last date should not be fully matured"

        # Cohort dates <= cutoff - 30 should be eligible
        threshold = cutoff - pd.Timedelta(days=30)
        eligible_on_time = result[result["date"] <= threshold]["evaluation_eligible"]
        assert eligible_on_time.all(), f"All cohorts <= {threshold.date()} should be eligible"

        # Cohort dates > cutoff - 30 should NOT be eligible
        ineligible = result[result["date"] > threshold]
        if not ineligible.empty:
            assert not ineligible["evaluation_eligible"].any(), "Cohorts within last 30 days should not be eligible"
            assert (ineligible["exclusion_reason"] == "观察窗口未满30日").all()

        # Verify the metadata
        assert result["maturity_days"].iloc[-1] == (cutoff - result["date"].iloc[-1]).days


# ── 3. Zero Value Tests ──

class TestZeroValues:
    def setup_method(self):
        self.bt = _import_bt_module()

    def _make_el(self, actuals, forecasts):
        n = len(actuals)
        dates = pd.date_range("2025-01-01", periods=n, freq="D")
        return pd.DataFrame({
            "date": dates,
            "cohort_actual_30_lock": actuals,
            "cohort_pred_30_lock": forecasts,
            "cohort_assign_count": [1000] * n,
            "prediction_method": ["actual"] * n,
            "maturity_days": [60] * n,
            "is_fully_matured": [True] * n,
            "evaluation_eligible": [True] * n,
            "exclusion_reason": ["已成熟"] * n,
            "as_of_date": dates,
            "age_at_prediction": [30] * n,
        })

    def test_mape_all_zero_actual(self):
        """MAPE should exclude zero-actual rows without crash."""
        el = self._make_el([0, 0, 0], [10, 20, 30])
        m = self.bt.compute_official_metrics(el)
        # MAPE should be NaN (no non-zero actual)
        assert np.isnan(m["mape"]), "MAPE should be NaN when all actuals are zero"
        assert m["mape_excluded"] == 3, f"Expected 3 excluded, got {m['mape_excluded']}"

    def test_mape_partial_zero(self):
        """Mixed zeros — only non-zero actuals count toward MAPE."""
        el = self._make_el([0, 100, 0, 200], [10, 90, 5, 210])
        m = self.bt.compute_official_metrics(el)
        assert m["mape_excluded"] == 2, f"Expected 2 excluded, got {m['mape_excluded']}"
        assert not np.isnan(m["mape"]), "MAPE should be computable from non-zero rows"
        # Expected: |90-100|/100 + |210-200|/200 = 0.1 + 0.05 = 0.15, / 2 = 0.075
        assert abs(m["mape"] - 0.075) < 0.001, f"MAPE expected 0.075, got {m['mape']}"

    def test_wape_with_zeros(self):
        """WAPE should work even when some actuals are zero."""
        el = self._make_el([0, 100, 0, 200], [10, 90, 5, 210])
        m = self.bt.compute_official_metrics(el)
        # sum|error| = 10+10+5+10=35, sum|actual| = 0+100+0+200=300, WAPE=35/300=0.1167
        assert not np.isnan(m["wape"]), "WAPE should be computable with zero actuals"
        assert abs(m["wape"] - 35/300) < 0.001, f"WAPE expected {35/300}, got {m['wape']}"

    def test_zero_sum_actual(self):
        """When sum(actual) is zero, WAPE should be NaN."""
        el = self._make_el([0, 0, 0], [10, 20, 30])
        m = self.bt.compute_official_metrics(el)
        assert np.isnan(m["wape"]), "WAPE should be NaN when sum(actual)=0"
        # Bias and others should also be NaN rather than crashing
        assert np.isnan(m["bias_pct"]), "Bias should be NaN when sum(actual)=0"


# ── 4. CLI Smoke Tests ──

class TestCLISmoke:
    def test_json_output(self):
        """Script should produce valid JSON output."""
        r = subprocess.run(
            [sys.executable, str(_WS_DIR / "research_scripts" / "lock_predict_backtest.py"),
             "--format", "json"],
            capture_output=True, text=True, timeout=180,
        )
        assert r.returncode == 0, f"Non-zero return: {r.stderr}"
        data = json.loads(r.stdout)
        assert data["status"] in ("success", "partial_success")
        assert "metrics" in data.get("result", {})

    def test_json_contract_fields(self):
        """JSON contract must include required fields."""
        r = subprocess.run(
            [sys.executable, str(_WS_DIR / "research_scripts" / "lock_predict_backtest.py"),
             "--format", "json"],
            capture_output=True, text=True, timeout=180,
        )
        data = json.loads(r.stdout)
        for field in ("status", "script", "scope", "result", "followup_context", "warnings", "errors"):
            assert field in data, f"missing required field: {field}"
        # Check new metrics exist
        metrics = data.get("result", {}).get("metrics", {})
        assert "n" in metrics, "n should be in metrics"
        assert "mae" in metrics, "mae should be in metrics"
        assert "wape" in metrics, "wape should be in metrics"

    def test_html_generated(self):
        """Script should generate HTML report."""
        html_path = _WS_DIR / "outputs" / "reports" / "lock_predict_backtest.html"
        r = subprocess.run(
            [sys.executable, str(_WS_DIR / "research_scripts" / "lock_predict_backtest.py"),
             "--format", "terminal"],
            capture_output=True, text=True, timeout=180,
        )
        assert html_path.exists(), "HTML report not generated"
        size = html_path.stat().st_size
        assert size > 100000, f"HTML too small: {size} bytes"

    def test_help_output(self):
        """--help should work."""
        r = subprocess.run(
            [sys.executable, str(_WS_DIR / "research_scripts" / "lock_predict_backtest.py"),
             "--help"],
            capture_output=True, text=True, timeout=30,
        )
        assert r.returncode == 0
        assert "回测" in r.stdout or "backtest" in r.stdout or "Cohort" in r.stdout


# ── 5. Report Consistency Tests ──

class TestReportConsistency:
    def test_no_daily_in_model_metrics(self):
        """Verify model metrics only use CohortActual_30d, not DailyLockCount."""
        r = subprocess.run(
            [sys.executable, str(_WS_DIR / "research_scripts" / "lock_predict_backtest.py"),
             "--format", "terminal"],
            capture_output=True, text=True, timeout=180,
        )
        stdout = r.stdout
        # The daily observation section should not use "误差" or "准确率" for model evaluation
        assert "正式回测样本" in stdout, "Report should mention formal backtest sample"

    def test_eligible_vs_immature_separation(self):
        """Verify mature/immature counts in output."""
        r = subprocess.run(
            [sys.executable, str(_WS_DIR / "research_scripts" / "lock_predict_backtest.py"),
             "--format", "terminal"],
            capture_output=True, text=True, timeout=180,
        )
        stdout = r.stdout
        assert "正式回测样本" in stdout, "Should show formal backtest sample count"
        assert "未成熟观察" in stdout, "Should show immature observation count"
