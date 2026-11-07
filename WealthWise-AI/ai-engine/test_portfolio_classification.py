import unittest

from data_quality import analyze_data_quality
from portfolio_analytics import calculate_portfolio_metrics, normalize_asset_class


class PortfolioClassificationTests(unittest.TestCase):
    def test_unclassified_values_are_preserved_as_unclassified(self):
        self.assertEqual(normalize_asset_class("Other"), "Unclassified")
        self.assertEqual(normalize_asset_class("Unclassified"), "Unclassified")
        self.assertEqual(normalize_asset_class("Equity - Large Cap"), "Equity")

    def test_subcategory_is_not_treated_as_sector(self):
        portfolio = {
            "currency": "INR",
            "holdings": [{
                "name": "Example Equity Fund",
                "asset_class": "Equity",
                "sub_category": "Large Cap",
                "current_value": 1000,
                "invested_value": 900,
            }],
        }

        result = calculate_portfolio_metrics(portfolio)

        self.assertEqual(result["sector_allocation"][0]["category"], "Unknown")
        self.assertEqual(result["data_quality"]["unknown_sector_count"], 1)

        quality = analyze_data_quality(portfolio, as_of_date="2026-11-07")
        self.assertEqual(quality["summary"]["missing_sector"], 1)

    def test_unclassified_asset_is_counted_as_data_quality_issue(self):
        result = calculate_portfolio_metrics({
            "currency": "INR",
            "holdings": [{
                "name": "Unmapped Instrument",
                "asset_class": "Other",
                "current_value": 1000,
                "invested_value": 900,
            }],
        })

        self.assertEqual(result["data_quality"]["unknown_asset_count"], 1)
        self.assertTrue(any(
            flag["type"] == "Data Quality"
            and "unclassified asset types" in flag["message"]
            for flag in result["risk_flags"]
        ))


if __name__ == "__main__":
    unittest.main()
