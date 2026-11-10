"""Enrich statement NAV history with AMFI observations when available.

External observations replace statement NAV history only for the matching ISIN
when AMFI returns data. Folio identity is retained because the same scheme NAV
applies to each folio, while uploaded current values remain untouched.
"""
from datetime import date, timedelta

from amfi_nav import AMFINavProviderError, fetch_amfi_nav_history


HISTORY_WINDOW_DAYS = 89


def enrich_history_with_amfi_nav(records, as_of_date=None, fetcher=None):
    if records is None:
        records = []
    if not isinstance(records, list):
        raise ValueError("Instrument history must be a list.")

    fetch = fetcher or fetch_amfi_nav_history
    end_date = as_of_date or date.today()
    start_date = end_date - timedelta(days=HISTORY_WINDOW_DAYS)

    base_records = [record for record in records if isinstance(record, dict)]
    holdings_by_isin = {}
    for record in base_records:
        isin = " ".join(str(record.get("isin") or "").upper().split())
        if isin:
            holdings_by_isin.setdefault(isin, []).append(record)

    replacements = {}
    provider_status = {
        "provider": "AMFI India",
        "enabled": True,
        "requested_isin_count": len(holdings_by_isin),
        "matched_isin_count": 0,
        "failed_isins": [],
        "history_window": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        "note": (
            "AMFI NAV history is used only when an exact ISIN match is returned. "
            "Uploaded current values and portfolio valuations are not changed."
        ),
    }

    for isin, holdings in holdings_by_isin.items():
        try:
            observations = fetch(isin, start_date, end_date)
        except (AMFINavProviderError, OSError, TimeoutError, ValueError):
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
    return enriched, provider_status
