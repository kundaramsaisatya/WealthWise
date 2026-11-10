import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from amfi_nav_cache import AMFINavCache, get_default_cache_path


class AMFINavCacheTests(unittest.TestCase):
    def test_persists_and_reads_observations_and_completed_ranges(self):
        with tempfile.TemporaryDirectory() as folder:
            path = f"{folder}/cache.sqlite3"
            cache = AMFINavCache(path)
            cache.save_range("INF000000001", date(2026, 1, 1), date(2026, 1, 10), [
                {
                    "scheme_code": "100",
                    "scheme_name": "Fund A",
                    "nav": "125.50",
                    "date": "2026-01-02",
                    "source": "AMFI India",
                }
            ])

            reopened = AMFINavCache(path)
            self.assertEqual(
                reopened.get_observations(
                    "INF000000001", date(2026, 1, 1), date(2026, 1, 10)
                )[0]["nav"],
                "125.50",
            )
            self.assertIn(
                ("2026-01-01", "2026-01-10"),
                reopened.get_range_status("INF000000001"),
            )

    def test_default_cache_uses_configured_data_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {"WEALTHWISE_DATA_DIR": folder}):
                self.assertEqual(
                    get_default_cache_path(),
                    Path(folder) / "amfi_nav_cache.sqlite3",
                )

    def test_cache_isolated_by_isin(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = AMFINavCache(f"{folder}/cache.sqlite3")
            cache.save_range("INF000000001", date(2026, 1, 1), date(2026, 1, 10), [
                {"scheme_code": "100", "scheme_name": "Fund A", "nav": "10", "date": "2026-01-02"}
            ])
            self.assertEqual(
                cache.get_observations("INF000000002", date(2026, 1, 1), date(2026, 1, 10)),
                [],
            )


if __name__ == "__main__":
    unittest.main()
