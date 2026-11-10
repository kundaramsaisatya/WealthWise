"""Durable SQLite cache for public AMFI mutual-fund NAV observations."""
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_CACHE_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "amfi_nav_cache.sqlite3"
)


class AMFINavCache:
    def __init__(self, path=None):
        configured = path or os.getenv("AMFI_NAV_CACHE_PATH")
        self.path = Path(configured) if configured else DEFAULT_CACHE_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    def _connect(self):
        connection = sqlite3.connect(str(self.path), timeout=15)
        connection.execute("PRAGMA busy_timeout = 15000")
        return connection

    def _initialise(self):
        with self._connect() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.execute("""
                CREATE TABLE IF NOT EXISTS nav_observations (
                    isin TEXT NOT NULL,
                    scheme_code TEXT NOT NULL,
                    observation_date TEXT NOT NULL,
                    nav TEXT NOT NULL,
                    scheme_name TEXT NOT NULL,
                    source TEXT NOT NULL,
                    PRIMARY KEY (isin, scheme_code, observation_date)
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS completed_ranges (
                    isin TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY (isin, start_date, end_date)
                )
            """)
            db.execute("""
                CREATE INDEX IF NOT EXISTS idx_nav_observations_isin_date
                ON nav_observations (isin, observation_date)
            """)

    def get_range_status(self, isin):
        with self._connect() as db:
            rows = db.execute(
                "SELECT start_date, end_date, fetched_at FROM completed_ranges WHERE isin = ?",
                (isin,),
            ).fetchall()
        return {
            (row[0], row[1]): row[2]
            for row in rows
        }

    def save_range(self, isin, start_date, end_date, observations):
        fetched_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            for item in observations:
                db.execute("""
                    INSERT INTO nav_observations
                    (isin, scheme_code, observation_date, nav, scheme_name, source)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(isin, scheme_code, observation_date)
                    DO UPDATE SET nav=excluded.nav,
                                  scheme_name=excluded.scheme_name,
                                  source=excluded.source
                """, (
                    isin,
                    str(item["scheme_code"]),
                    str(item["date"]),
                    str(item["nav"]),
                    str(item.get("scheme_name") or "Unknown scheme"),
                    str(item.get("source") or "AMFI India"),
                ))
            db.execute("""
                INSERT INTO completed_ranges (isin, start_date, end_date, fetched_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(isin, start_date, end_date)
                DO UPDATE SET fetched_at=excluded.fetched_at
            """, (isin, start_date.isoformat(), end_date.isoformat(), fetched_at))

    def get_observations(self, isin, start_date, end_date):
        with self._connect() as db:
            rows = db.execute("""
                SELECT scheme_code, scheme_name, nav, observation_date, source
                FROM nav_observations
                WHERE isin = ? AND observation_date >= ? AND observation_date <= ?
                ORDER BY observation_date, scheme_code
            """, (isin, start_date.isoformat(), end_date.isoformat())).fetchall()
        return [
            {
                "scheme_code": row[0],
                "scheme_name": row[1],
                "nav": row[2],
                "date": row[3],
                "source": row[4],
                "isin": isin,
            }
            for row in rows
        ]
