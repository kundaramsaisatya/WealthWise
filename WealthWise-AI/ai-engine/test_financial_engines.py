import math
import unittest

from data_quality import analyze_data_quality
from performance_engine import calculate_portfolio_performance
from portfolio_analytics import resolve_thresholds
from risk_engine import analyze_portfolio_risk, resolve_profile


class PerformanceEngineTests(unittest.TestCase):

    def test_sorts_snapshots_and_calculates_value_change(self):
        result = calculate_portfolio_performance([
            {"report_date": "2026-02-01", "total_value": 1200},
            {"report_date": "2026-01-01", "total_value": 1000},
        ])
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["summary"]["absolute_change"], 200)
        self.assertEqual(result["summary"]["percentage_change"], 20.0)
        self.assertEqual(result["summary"]["period_days"], 31)
        self.assertFalse(result["summary"]["xirr_available"])

    def test_rejects_boolean_non_finite_negative_and_malformed_values(self):
        result = calculate_portfolio_performance([
            {"report_date": "2026-01-01", "total_value": True},
            {"report_date": "2026-01-02", "total_value": math.nan},
            {"report_date": "2026-01-03", "total_value": math.inf},
            {"report_date": "2026-01-04", "total_value": -1},
            None,
            {"report_date": "2026-01-05", "total_value": 100},
            {"report_date": "2026-02-05", "total_value": 110},
        ])
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["snapshot_count"], 2)
        self.assertEqual(len(result["rejected_snapshots"]), 5)

    def test_same_date_snapshots_are_ambiguous(self):
        result = calculate_portfolio_performance([
            {"report_date": "2026-01-01", "total_value": 100},
            {"report_date": "2026-01-01", "total_value": 120},
        ])
        self.assertEqual(result["status"], "ambiguous_data")
        self.assertIsNone(result["summary"])


class RiskAndThresholdValidationTests(unittest.TestCase):

    def test_rejects_invalid_goal_horizons(self):
        for value in (True, -1, math.nan, math.inf, "not-a-number"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "horizon_years"):
                    resolve_profile({"horizon_years": value})

    def test_accepts_finite_non_negative_goal_horizon(self):
        _, profile = resolve_profile({"horizon_years": "2.5"})
        self.assertEqual(profile["horizon_years"], 2.5)

    def test_profile_summary_records_goal_horizon_rule(self):
        _, profile = resolve_profile({"horizon_years": "2.5"})
        self.assertEqual(profile["goal_horizon_equity_limit_pct"], 40)
        self.assertIn(
            "default portfolio thresholds",
            profile["used_in_calculation"]
        )
        self.assertIn(
            "illustrative goal-horizon equity exposure rule",
            profile["used_in_calculation"]
        )

    def test_profile_summary_records_risk_tolerance_and_custom_overrides(self):
        _, profile = resolve_profile({
            "risk_tolerance": "moderate",
            "thresholds": {"max_equity_pct": 65}
        })
        self.assertEqual(
            profile["used_in_calculation"],
            [
                "risk-tolerance profile thresholds",
                "custom threshold overrides"
            ]
        )

    def test_horizons_beyond_configured_rules_are_not_claimed_as_applied(self):
        _, profile = resolve_profile({"horizon_years": 8})
        self.assertIsNone(profile["goal_horizon_equity_limit_pct"])
        self.assertNotIn(
            "illustrative goal-horizon equity exposure rule",
            profile["used_in_calculation"]
        )

    def test_rejects_out_of_range_or_unknown_thresholds(self):
        for thresholds in (
            {"max_equity_pct": 101},
            {"max_single_holding_pct": -1},
            {"min_liquidity_pct": True},
            {"unknown_limit": 10},
        ):
            with self.subTest(thresholds=thresholds):
                with self.assertRaises(ValueError):
                    resolve_thresholds(thresholds)


class DataQualityTests(unittest.TestCase):

    def test_rejects_non_object_holding_instead_of_skewing_percentages(self):
        with self.assertRaisesRegex(ValueError, "Invalid holding record"):
            analyze_data_quality({"holdings": [{"name": "Valid"}, None]})

    def test_matches_history_using_normalized_isin(self):
        result = analyze_data_quality(
            {
                "report_date": "2026-11-09",
                "holdings": [
                    {
                        "name": "Example Fund",
                        "isin": " inf000000001 ",
                        "asset_class": "Equity",
                        "invested_value": 100,
                        "sector": "Financials",
                    }
                ],
            },
            history_records=[
                {"isin": "INF000000001", "report_date": "2025-01-01"},
                {"isin": "INF000000001", "report_date": "2026-11-09"},
            ],
            as_of_date="2026-11-09",
        )
        self.assertEqual(result["historical_coverage_percentage"], 100.0)
        self.assertEqual(result["holdings"][0]["history_days"], 677)


    def test_history_is_isolated_between_folios_of_same_fund(self):
        result = analyze_data_quality(
            {
                "report_date": "2026-11-09",
                "holdings": [
                    {
                        "name": "Same Fund",
                        "isin": "INF000000001",
                        "folio_number": "FOLIO-A",
                        "asset_class": "Equity",
                        "invested_value": 100,
                        "sector": "Financials",
                    },
                    {
                        "name": "Same Fund",
                        "isin": "INF000000001",
                        "folio_number": "FOLIO-B",
                        "asset_class": "Equity",
                        "invested_value": 100,
                        "sector": "Financials",
                    },
                ],
            },
            history_records=[
                {"isin": "INF000000001", "folio_number": "FOLIO-A", "report_date": "2025-01-01"},
                {"isin": "INF000000001", "folio_number": "FOLIO-A", "report_date": "2026-11-09"},
                {"isin": "INF000000001", "folio_number": "FOLIO-B", "report_date": "2026-11-09"},
            ],
            as_of_date="2026-11-09",
        )
        self.assertEqual(result["historical_coverage_percentage"], 50.0)
        self.assertEqual(result["holdings"][0]["history_status"], "Sufficient")
        self.assertEqual(result["holdings"][1]["history_status"], "Insufficient History")



class LimitedHistoryConcentrationTests(unittest.TestCase):

    def _portfolio(self, new_value):
        return {
            "client_id": "CLIENT-TEST",
            "currency": "INR",
            "holdings": [
                {
                    "name": "New Instrument",
                    "isin": "INF000000001",
                    "asset_class": "Equity",
                    "sector": "Technology",
                    "current_value": new_value,
                    "invested_value": new_value,
                    "report_date": "2026-11-09",
                },
                {
                    "name": "Established Holding",
                    "isin": "INF000000002",
                    "asset_class": "Debt",
                    "sector": "Debt",
                    "current_value": 100 - new_value,
                    "invested_value": 100 - new_value,
                    "report_date": "2026-11-09",
                },
            ],
        }

    def _analyze(self, new_value):
        return analyze_portfolio_risk(
            self._portfolio(new_value),
            history_records=[
                {"isin": "INF000000001", "date": "2026-11-09"},
                {"isin": "INF000000002", "date": "2025-01-01"},
                {"isin": "INF000000002", "date": "2026-11-09"},
            ],
            as_of_date="2026-11-09",
        )

    def test_large_holding_with_insufficient_history_gets_uncertainty_flag(self):
        result = self._analyze(30)
        flag = next(
            item for item in result["risk_flags"]
            if item["type"] == "Limited-History Concentration"
        )
        self.assertEqual(flag["holding_name"], "New Instrument")
        self.assertEqual(flag["holding_percentage"], 30.0)
        self.assertEqual(flag["severity"], "Medium")
        self.assertEqual(flag["configured_limit"], 20)

    def test_small_holding_with_insufficient_history_does_not_get_flag(self):
        result = self._analyze(10)
        self.assertFalse(any(
            item["type"] == "Limited-History Concentration"
            for item in result["risk_flags"]
        ))

    def test_weights_are_not_reported_when_any_current_value_is_missing(self):
        from data_quality import analyze_data_quality

        result = analyze_data_quality({
            "holdings": [
                {"name": "Known", "current_value": 100},
                {"name": "Unknown", "current_value": None},
            ]
        }, as_of_date="2026-11-09")
        self.assertIsNone(result["holdings"][0]["weight_percentage"])
        self.assertIsNone(result["holdings"][1]["weight_percentage"])


if __name__ == "__main__":
    unittest.main()
