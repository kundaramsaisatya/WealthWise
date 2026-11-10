import unittest
from datetime import date, datetime, timezone

from amfi_risk_integration import (
    HISTORY_YEARS,
    MAX_RANGE_FETCHES_PER_ISIN_PER_REQUEST,
    enrich_history_with_amfi_nav,
)


class FakeCache:
    def __init__(self):
        self.ranges = {}
        self.observations = {}

    def get_range_status(self, isin):
        return self.ranges.get(isin, {}).copy()

    def save_range(self, isin, start, end, observations):
        self.ranges.setdefault(isin, {})[(start.isoformat(), end.isoformat())] = datetime.now(timezone.utc).isoformat()
        self.observations.setdefault(isin, {}).update({
            (item["scheme_code"], item["date"]): item for item in observations
        })

    def get_observations(self, isin, start, end):
        return [
            item for item in self.observations.get(isin, {}).values()
            if start.isoformat() <= item["date"] <= end.isoformat()
        ]


class AMFIRiskIntegrationTests(unittest.TestCase):
    def test_replaces_matching_isin_and_preserves_folio_with_long_history(self):
        records = [
            {"isin": "INF000000001", "folio_number": "F1", "name": "Fund A", "report_date": "2026-01-01", "nav": 90},
            {"isin": "INF000000001", "folio_number": "F2", "name": "Fund A", "report_date": "2026-01-01", "nav": 90},
            {"isin": "INF000000002", "folio_number": "F3", "name": "Fund B", "report_date": "2026-01-01", "nav": 50},
        ]
        cache = FakeCache()
        calls = []

        def fetcher(isin, start, end):
            calls.append((isin, start, end))
            if isin == "INF000000001":
                return [
                    {"isin": isin, "scheme_code": "10", "scheme_name": "Fund A", "date": end.isoformat(), "nav": "100.5", "source": "AMFI India"}
                ]
            return []

        enriched, status = enrich_history_with_amfi_nav(
            records, as_of_date=date(2026, 4, 10), fetcher=fetcher, cache=cache
        )
        external = [item for item in enriched if item.get("data_source")]
        self.assertEqual({item["folio_number"] for item in external}, {"F1", "F2"})
        self.assertTrue(all(item["nav"] == "100.5" for item in external))
        self.assertEqual(len([item for item in enriched if item["isin"] == "INF000000002"]), 1)
        self.assertEqual(status["history_years_requested"], HISTORY_YEARS)
        self.assertLessEqual(len(calls), 2 * 2)
        self.assertEqual(status["matched_isin_count"], 1)

    def test_provider_failure_keeps_statement_history(self):
        records = [
            {"isin": "INF000000001", "folio_number": "F1", "name": "Fund A", "report_date": "2026-01-01", "nav": 90}
        ]

        def failed_fetcher(*args):
            raise OSError("provider down")

        enriched, status = enrich_history_with_amfi_nav(
            records, as_of_date=date(2026, 4, 10),
            fetcher=failed_fetcher, cache=FakeCache()
        )
        self.assertEqual(enriched, records)
        self.assertEqual(status["failed_isins"], ["INF000000001"])

    def test_no_isin_does_not_call_provider(self):
        records = [{"name": "Unidentified fund", "report_date": "2026-01-01", "nav": 10}]
        enriched, status = enrich_history_with_amfi_nav(
            records, as_of_date=date(2026, 4, 10),
            fetcher=lambda *_: self.fail("must not fetch without ISIN"),
            cache=FakeCache()
        )
        self.assertEqual(enriched, records)
        self.assertEqual(status["requested_isin_count"], 0)

    def test_backfill_is_incremental_and_cached_ranges_are_not_refetched(self):
        cache = FakeCache()
        calls = []

        def fetcher(isin, start, end):
            calls.append((start, end))
            return []

        records = [{"isin": "INF000000001", "name": "Fund A"}]
        enrich_history_with_amfi_nav(
            records, as_of_date=date(2026, 4, 10), fetcher=fetcher, cache=cache
        )
        first_count = len(calls)
        self.assertGreater(first_count, 0)
        self.assertLessEqual(first_count, MAX_RANGE_FETCHES_PER_ISIN_PER_REQUEST)

        enrich_history_with_amfi_nav(
            records, as_of_date=date(2026, 4, 10), fetcher=fetcher, cache=cache
        )
        self.assertEqual(len(calls), first_count)

    def test_long_history_is_split_into_amfi_compatible_ranges(self):
        from amfi_risk_integration import _history_ranges
        ranges = _history_ranges(date(2023, 1, 1), date(2026, 1, 1))
        self.assertGreater(len(ranges), 10)
        self.assertTrue(all((end - start).days < 90 for start, end in ranges))
        self.assertEqual(ranges[0][1], date(2026, 1, 1))
        self.assertEqual(ranges[-1][0], date(2023, 1, 1))


if __name__ == "__main__":
    unittest.main()
