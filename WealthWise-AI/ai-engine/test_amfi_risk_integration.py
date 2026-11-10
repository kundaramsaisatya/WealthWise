import unittest
from datetime import date

from amfi_risk_integration import enrich_history_with_amfi_nav


class AMFIRiskIntegrationTests(unittest.TestCase):
    def test_replaces_only_matching_isin_and_preserves_folio(self):
        records = [
            {"isin": "INF000000001", "folio_number": "F1", "name": "Fund A", "report_date": "2026-01-01", "nav": 90},
            {"isin": "INF000000001", "folio_number": "F2", "name": "Fund A", "report_date": "2026-01-01", "nav": 90},
            {"isin": "INF000000002", "folio_number": "F3", "name": "Fund B", "report_date": "2026-01-01", "nav": 50},
        ]

        def fetcher(isin, start, end):
            self.assertEqual(start, date(2026, 1, 11))
            self.assertEqual(end, date(2026, 4, 10))
            if isin == "INF000000001":
                return [
                    {"isin": isin, "scheme_code": "10", "scheme_name": "Fund A", "date": "2026-04-09", "nav": "100.5", "source": "AMFI India"}
                ]
            return []

        enriched, status = enrich_history_with_amfi_nav(
            records, as_of_date=date(2026, 4, 10), fetcher=fetcher
        )
        external = [item for item in enriched if item.get("data_source")]
        self.assertEqual(len(external), 2)
        self.assertEqual({item["folio_number"] for item in external}, {"F1", "F2"})
        self.assertTrue(all(item["nav"] == "100.5" for item in external))
        self.assertEqual(len([item for item in enriched if item["isin"] == "INF000000002"]), 1)
        self.assertEqual(status["matched_isin_count"], 1)
        self.assertEqual(status["fallback_isin_count"], 1)

    def test_provider_failure_keeps_statement_history(self):
        records = [
            {"isin": "INF000000001", "folio_number": "F1", "name": "Fund A", "report_date": "2026-01-01", "nav": 90}
        ]

        def failed_fetcher(*args):
            raise OSError("provider down")

        enriched, status = enrich_history_with_amfi_nav(
            records, as_of_date=date(2026, 4, 10), fetcher=failed_fetcher
        )
        self.assertEqual(enriched, records)
        self.assertEqual(status["failed_isins"], ["INF000000001"])

    def test_no_isin_does_not_call_provider(self):
        records = [{"name": "Unidentified fund", "report_date": "2026-01-01", "nav": 10}]
        enriched, status = enrich_history_with_amfi_nav(
            records, as_of_date=date(2026, 4, 10),
            fetcher=lambda *_: self.fail("must not fetch without ISIN")
        )
        self.assertEqual(enriched, records)
        self.assertEqual(status["requested_isin_count"], 0)


if __name__ == "__main__":
    unittest.main()
