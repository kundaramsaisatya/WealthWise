import unittest
from datetime import date, timedelta

from instrument_risk import analyze_instrument_nav_history


class InstrumentNavRiskTests(unittest.TestCase):
    def test_calculates_nav_change_and_drawdown_from_dated_nav_only(self):
        result = analyze_instrument_nav_history([
            {"name": "Fund A", "isin": "INF0001", "folio_number": "A", "date": "2026-01-01", "nav": 100},
            {"name": "Fund A", "isin": "INF0001", "folio_number": "A", "date": "2026-01-02", "nav": 120},
            {"name": "Fund A", "isin": "INF0001", "folio_number": "A", "date": "2026-01-03", "nav": 90},
        ])
        item = result["instruments"][0]
        self.assertEqual(item["nav_change_percentage"], -10.0)
        self.assertEqual(item["max_drawdown_percentage"], -25.0)
        self.assertIsNone(item["volatility_per_observation_percentage"])

    def test_volatility_requires_at_least_30_valid_observations(self):
        start = date(2026, 1, 1)
        records = [
            {"name": "Fund A", "isin": "INF0001", "date": (start + timedelta(days=i)).isoformat(), "nav": 100 + i}
            for i in range(30)
        ]
        item = analyze_instrument_nav_history(records)["instruments"][0]
        self.assertEqual(item["volatility_status"], "available")
        self.assertIsNotNone(item["volatility_per_observation_percentage"])

    def test_conflicting_same_day_nav_is_rejected_as_ambiguous(self):
        result = analyze_instrument_nav_history([
            {"name": "Fund A", "isin": "INF0001", "date": "2026-01-01", "nav": 100},
            {"name": "Fund A", "isin": "INF0001", "date": "2026-01-01", "nav": 101},
        ])
        self.assertEqual(result["instruments"][0]["status"], "ambiguous_data")
        self.assertIsNone(result["instruments"][0]["nav_change_percentage"])

    def test_invalid_and_non_finite_navs_are_rejected(self):
        result = analyze_instrument_nav_history([
            {"name": "Fund A", "isin": "INF0001", "date": "2026-01-01", "nav": True},
            {"name": "Fund A", "isin": "INF0001", "date": "2026-01-02", "nav": float("nan")},
            {"name": "Fund A", "isin": "INF0001", "date": "2026-01-03", "nav": -2},
        ])
        self.assertEqual(result["rejected_observation_count"], 3)
        self.assertEqual(result["instrument_count"], 0)

    def test_separates_folios_for_same_isin(self):
        result = analyze_instrument_nav_history([
            {"name": "Fund A", "isin": "INF0001", "folio_number": "A", "date": "2026-01-01", "nav": 100},
            {"name": "Fund A", "isin": "INF0001", "folio_number": "B", "date": "2026-01-01", "nav": 105},
        ])
        self.assertEqual(result["instrument_count"], 2)


if __name__ == "__main__":
    unittest.main()
