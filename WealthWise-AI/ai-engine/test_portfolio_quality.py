import unittest

from data_quality import analyze_data_quality
from portfolio_analytics import calculate_portfolio_metrics


class PortfolioQualityTests(unittest.TestCase):

    def test_unclassified_assets_are_counted_consistently(self):
        portfolio = {
            "holdings": [
                {"name": "Other Asset", "asset_class": "Other"},
                {"name": "Unknown Asset", "asset_class": "Unknown"},
                {"name": "Mutual Fund", "asset_class": "Mutual Fund"},
                {"name": "Equity Holding", "asset_class": "Equity"},
            ]
        }

        result = analyze_data_quality(portfolio, as_of_date="2026-11-09")

        self.assertEqual(result["summary"]["unknown_asset_class"], 3)
        issue = next(
            item for item in result["issues"]
            if item["type"] == "Asset Classification"
        )
        self.assertEqual(issue["count"], 3)

    def test_top_three_concentration_uses_largest_holdings(self):
        portfolio = {
            "client_id": "CLIENT-TEST",
            "currency": "INR",
            "holdings": [
                {"name": "Small", "asset_class": "Equity", "current_value": 10, "invested_value": 10},
                {"name": "Largest", "asset_class": "Equity", "current_value": 60, "invested_value": 50},
                {"name": "Second", "asset_class": "Debt", "current_value": 20, "invested_value": 20},
                {"name": "Third", "asset_class": "Gold", "current_value": 10, "invested_value": 10},
            ]
        }

        result = calculate_portfolio_metrics(portfolio)

        self.assertEqual(result["concentration"]["top_three_concentration"], 90.0)
        self.assertEqual(result["largest_holding"]["name"], "Largest")

    def test_missing_cost_basis_does_not_create_false_total_return(self):
        portfolio = {
            "client_id": "CLIENT-TEST",
            "currency": "INR",
            "holdings": [
                {"name": "Known Cost", "asset_class": "Equity", "current_value": 100, "invested_value": 80},
                {"name": "Missing Cost", "asset_class": "Debt", "current_value": 50, "invested_value": None},
            ]
        }

        result = calculate_portfolio_metrics(portfolio)

        self.assertIsNone(result["total_invested"])
        self.assertIsNone(result["profit_loss"])
        self.assertIsNone(result["profit_loss_percentage"])
        self.assertEqual(result["known_invested_value"], 80.0)

    def test_sector_and_issuer_exposure_reports_identified_coverage(self):
        result = calculate_portfolio_metrics({
            "client_id": "CLIENT-TEST",
            "currency": "INR",
            "holdings": [
                {"name": "Fund A", "asset_class": "Equity", "sector": "Technology",
                 "issuer": "Issuer One", "current_value": 60, "invested_value": 50},
                {"name": "Fund B", "asset_class": "Debt", "sector": "Technology",
                 "issuer": "Issuer One", "current_value": 20, "invested_value": 20},
                {"name": "Unknown issuer", "asset_class": "Gold", "sector": "Unknown",
                 "current_value": 20, "invested_value": 20},
            ],
        })
        self.assertEqual(result["sector_exposure"]["coverage_percentage"], 80.0)
        self.assertEqual(result["sector_exposure"]["largest"]["name"], "Technology")
        self.assertEqual(result["sector_exposure"]["largest"]["portfolio_percentage"], 80.0)
        self.assertEqual(result["issuer_exposure"]["coverage_percentage"], 80.0)
        self.assertEqual(result["issuer_exposure"]["largest"]["name"], "Issuer One")

    def test_sector_threshold_is_optional_and_validated(self):
        from portfolio_analytics import resolve_thresholds
        self.assertIsNone(resolve_thresholds(None)["max_sector_pct"])
        self.assertEqual(resolve_thresholds({"max_sector_pct": 35})["max_sector_pct"], 35.0)
        with self.assertRaises(ValueError):
            resolve_thresholds({"max_sector_pct": 101})

    def test_negative_current_value_is_rejected(self):
        portfolio = {
            "client_id": "CLIENT-TEST",
            "currency": "INR",
            "holdings": [
                {"name": "Invalid Holding", "asset_class": "Equity", "current_value": -10, "invested_value": 5}
            ]
        }

        with self.assertRaisesRegex(ValueError, "Invalid current value"):
            calculate_portfolio_metrics(portfolio)


if __name__ == "__main__":
    unittest.main()
