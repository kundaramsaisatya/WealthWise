import unittest
from datetime import date
from unittest.mock import patch

from amfi_nav import (
    AMFINavProviderError,
    fetch_amfi_nav_history,
    parse_amfi_history,
)


ISIN = "INF000000001"


class AMFINavTests(unittest.TestCase):
    def test_parses_matching_growth_and_reinvestment_isins(self):
        feed = "\n".join([
            "Scheme Code;Scheme Name;ISIN Growth;ISIN Reinvestment;NAV;Repurchase;Sale;Date",
            f"100;Fund Growth;{ISIN};-;125.5000;0;0;02-Jan-2026",
            f"101;Fund Reinvestment;-;{ISIN};99.2500;0;0;03-Jan-2026",
            "102;Other Fund;INF000000002;-;20.0;0;0;03-Jan-2026",
            "AMC Name",
        ])
        rows = parse_amfi_history(feed, ISIN)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["nav"], "125.5000")
        self.assertEqual(rows[0]["date"], "2026-01-02")
        self.assertEqual(rows[0]["source"], "AMFI India")

    def test_skips_invalid_nav_and_date_rows(self):
        feed = "\n".join([
            f"100;Fund;{ISIN};-;0;0;0;02-Jan-2026",
            f"101;Fund;{ISIN};-;NaN;0;0;02-Jan-2026",
            f"102;Fund;{ISIN};-;10;0;0;not-a-date",
        ])
        self.assertEqual(parse_amfi_history(feed, ISIN), [])

    def test_rejects_invalid_isin(self):
        with self.assertRaises(ValueError):
            parse_amfi_history("100;Fund;A;-;10;0;0;02-Jan-2026", "")

    def test_rejects_date_ranges_over_90_days(self):
        with self.assertRaises(ValueError):
            fetch_amfi_nav_history(ISIN, date(2026, 1, 1), date(2026, 4, 1))

    def test_rejects_reversed_date_range(self):
        with self.assertRaises(ValueError):
            fetch_amfi_nav_history(ISIN, date(2026, 2, 1), date(2026, 1, 1))

    @patch("amfi_nav.urlopen")
    def test_fetches_each_scheme_type_and_deduplicates(self, mocked_urlopen):
        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, limit):
                return (
                    f"100;Fund;{ISIN};-;125.5;0;0;02-Jan-2026"
                ).encode()

        mocked_urlopen.return_value = FakeResponse()
        rows = fetch_amfi_nav_history(
            ISIN, date(2026, 1, 1), date(2026, 1, 10)
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(mocked_urlopen.call_count, 3)

    @patch("amfi_nav.urlopen", side_effect=OSError("network detail"))
    def test_hides_provider_transport_error(self, _mocked_urlopen):
        with self.assertRaises(AMFINavProviderError) as context:
            fetch_amfi_nav_history(
                ISIN, date(2026, 1, 1), date(2026, 1, 10)
            )
        self.assertNotIn("network detail", str(context.exception))


if __name__ == "__main__":
    unittest.main()
