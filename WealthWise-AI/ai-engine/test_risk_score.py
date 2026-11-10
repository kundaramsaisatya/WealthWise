import unittest

from risk_engine import calculate_transparent_risk_score


class TransparentRiskScoreTests(unittest.TestCase):
    def _inputs(self):
        return (
            {
                "largest_holding": {"weight_percentage": 30},
                "concentration": {"top_three_concentration": 65},
                "thresholds": {
                    "max_single_holding_pct": 25,
                    "max_top_three_pct": 60,
                    "max_equity_pct": 70,
                    "min_liquidity_pct": 10,
                },
                "equity_percentage": 50,
                "liquidity": {"percentage": 5, "basis": "Reported categories"},
            },
            {
                "document_completeness_percentage": 80,
                "historical_coverage_percentage": 60,
            },
            {"instruments": [{
                "volatility_status": "available",
                "volatility_per_observation_percentage": 1.2,
            }]},
        )

    def test_score_is_bounded_and_explains_each_scored_dimension(self):
        result = calculate_transparent_risk_score(*self._inputs())
        self.assertEqual(result["status"], "available")
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)
        self.assertEqual(result["scored_dimension_count"], 4)
        for dimension in result["dimensions"]:
            if dimension["status"] == "scored":
                self.assertIn("rule", dimension)
                self.assertIn("evidence", dimension)

    def test_missing_equity_limit_is_not_guessed(self):
        portfolio, quality, history = self._inputs()
        portfolio["thresholds"]["max_equity_pct"] = None
        result = calculate_transparent_risk_score(portfolio, quality, history)
        allocation = next(x for x in result["dimensions"] if x["id"] == "allocation")
        self.assertIsNone(allocation["score"])
        self.assertEqual(allocation["status"], "not_scored")

    def test_historical_volatility_is_reported_but_not_aggregated(self):
        result = calculate_transparent_risk_score(*self._inputs())
        volatility = next(x for x in result["dimensions"] if x["id"] == "historical_volatility")
        self.assertEqual(volatility["status"], "informational_only")
        self.assertIsNone(volatility["score"])
        self.assertEqual(
            volatility["evidence"]["highest_volatility_per_observation_percentage"],
            1.2,
        )

    def test_no_available_dimensions_means_no_overall_score(self):
        result = calculate_transparent_risk_score(
            {
                "largest_holding": {},
                "concentration": {},
                "thresholds": {},
                "liquidity": {},
            },
            {},
            {"instruments": []},
        )
        self.assertIsNone(result["score"])
        self.assertEqual(result["status"], "insufficient_data")

    def test_liquidity_score_is_zero_at_or_above_minimum(self):
        portfolio, quality, history = self._inputs()
        portfolio["liquidity"]["percentage"] = 15
        result = calculate_transparent_risk_score(portfolio, quality, history)
        liquidity = next(x for x in result["dimensions"] if x["id"] == "liquidity")
        self.assertEqual(liquidity["score"], 0)


if __name__ == "__main__":
    unittest.main()
