"""Enrich statement NAV history with cached, multi-year AMFI observations.

AMFI observations are public scheme-level NAVs. Folio identity is retained for
analysis, but this data is not a folio-specific investor return.
"""
from datetime import date, datetime, timedelta, timezone

from amfi_nav import AMFINavProviderError, fetch_amfi_nav_history
from amfi_nav_cache import AMFINavCache


HISTORY_YEARS = 3
CHUNK_DAYS = 89
RECENT_CACHE_TTL_HOURS = 24
MAX_RANGE_FETCHES_PER_ISIN_PER_REQUEST = 2


def _history_ranges(start_date, end_date):
    ranges = []
    cursor = end_date
    while cursor >= start_date:
        chunk_start = max(start_date, cursor - timedelta(days=CHUNK_DAYS))
        ranges.append((chunk_start, cursor))
        cursor = chunk_start - timedelta(days=1)
    return ranges


def _is_stale(timestamp, now):
    try:
        fetched = datetime.fromisoformat(timestamp)
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        return (now - fetched).total_seconds() >= RECENT_CACHE_TTL_HOURS * 3600
    except (TypeError, ValueError):
        return True


def enrich_history_with_amfi_nav(
    records, as_of_date=None, fetcher=None, cache=None, cache_path=None,
    fetch_missing=True
):
    if records is None:
        records = []
    if not isinstance(records, list):
        raise ValueError("Instrument history must be a list.")

    fetch = fetcher or fetch_amfi_nav_history
    nav_cache = cache or AMFINavCache(cache_path)
    end_date = as_of_date or date.today()
    start_date = end_date - timedelta(days=365 * HISTORY_YEARS)
    ranges = _history_ranges(start_date, end_date)
    now = datetime.now(timezone.utc)

    base_records = [record for record in records if isinstance(record, dict)]
    holdings_by_isin = {}
    for record in base_records:
        isin = " ".join(str(record.get("isin") or "").upper().split())
        if isin.startswith("INF"):
            holdings_by_isin.setdefault(isin, []).append(record)

    replacements = {}
    provider_status = {
        "provider": "AMFI India",
        "enabled": True,
        "history_years_requested": HISTORY_YEARS,
        "max_range_fetches_per_isin_per_request": MAX_RANGE_FETCHES_PER_ISIN_PER_REQUEST,
        "requested_isin_count": len(holdings_by_isin),
        "matched_isin_count": 0,
        "backfill_pending": False,
        "failed_isins": [],
        "partially_cached_isins": [],
        "cache_path_configurable": True,
        "history_window": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        "note": (
            "AMFI scheme-level NAVs are cached in a local SQLite database. "
            "Only exact ISIN matches are used. Current holding values and "
            "portfolio valuations are unchanged. First-time history backfill "
            "is incremental and may take multiple background worker runs."
        ),
    }

    for isin, holdings in holdings_by_isin.items():
        try:
            completed = nav_cache.get_range_status(isin)
            pending = []
            for index, (range_start, range_end) in enumerate(ranges):
                key = (range_start.isoformat(), range_end.isoformat())
                fetched_at = completed.get(key)
                is_latest = index == 0
                if fetched_at is None or (is_latest and _is_stale(fetched_at, now)):
                    pending.append((range_start, range_end))

            # Always refresh the newest range when stale, then progressively
            # backfill one older missing range per request.
            selected = []
            if pending:
                latest = ranges[0]
                if latest in pending:
                    selected.append(latest)
                for item in pending:
                    if item not in selected and len(selected) < MAX_RANGE_FETCHES_PER_ISIN_PER_REQUEST:
                        selected.append(item)

            range_failures = False
            if fetch_missing:
                for range_start, range_end in selected:
                    try:
                        observations = fetch(isin, range_start, range_end)
                        nav_cache.save_range(isin, range_start, range_end, observations)
                    except (AMFINavProviderError, OSError, TimeoutError, ValueError):
                        range_failures = True
            elif selected:
                provider_status["backfill_pending"] = True

            completed_after = nav_cache.get_range_status(isin)
            if len(completed_after) < len(ranges):
                provider_status["partially_cached_isins"].append(isin)

            observations = nav_cache.get_observations(isin, start_date, end_date)
            if range_failures:
                provider_status["failed_isins"].append(isin)
        except (AMFINavProviderError, OSError, TimeoutError, ValueError):
            provider_status["failed_isins"].append(isin)
            continue
        except Exception:
            # Cache or provider failure must not block portfolio risk analysis.
            provider_status["failed_isins"].append(isin)
            continue

        if not observations:
            continue

        provider_status["matched_isin_count"] += 1
        replacements[isin] = [
            {
                "isin": isin,
                "folio_number": holding.get("folio_number"),
                "name": holding.get("name"),
                "report_date": observation["date"],
                "nav": observation["nav"],
                "data_source": observation.get("source", "AMFI India"),
                "scheme_code": observation.get("scheme_code"),
            }
            for holding in holdings
            for observation in observations
        ]

    enriched = []
    for record in base_records:
        isin = " ".join(str(record.get("isin") or "").upper().split())
        if isin in replacements:
            continue
        enriched.append(record)

    for observations in replacements.values():
        enriched.extend(observations)

    provider_status["fallback_isin_count"] = (
        len(holdings_by_isin) - provider_status["matched_isin_count"]
    )
    provider_status["partial_backfill_count"] = len(
        provider_status["partially_cached_isins"]
    )
    provider_status["cached_observation_count"] = sum(
        len(items) for items in replacements.values()
    )
    return enriched, provider_status
