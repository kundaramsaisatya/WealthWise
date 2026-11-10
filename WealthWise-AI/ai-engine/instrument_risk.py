import math
from collections import defaultdict
from datetime import datetime, timezone
from statistics import stdev


MIN_OBSERVATIONS_FOR_VOLATILITY = 30


def _parse_date(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.date()
    except (TypeError, ValueError, OverflowError):
        return None


def _finite_positive(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def analyze_instrument_nav_history(records):
    """
    Analyze explicit, dated NAV observations only.

    NAV changes are not investor returns: distributions, fees, taxes and
    external cash flows are not adjusted. Volatility is per-observation,
    not annualized, because observation frequency is not guaranteed.
    """
    if records is None:
        records = []
    if not isinstance(records, list):
        raise ValueError("Instrument history must be a list.")

    grouped = defaultdict(list)
    rejected = 0

    for record in records:
        if not isinstance(record, dict):
            rejected += 1
            continue

        nav = _finite_positive(record.get("nav"))
        date = _parse_date(record.get("report_date") or record.get("date"))
        if nav is None or date is None:
            rejected += 1
            continue

        isin = " ".join(str(record.get("isin") or "").upper().split())
        folio = " ".join(str(record.get("folio_number") or "").upper().split())
        name = " ".join(str(record.get("name") or "Unknown instrument").split())
        identity = (isin, folio, name.casefold() if not isin else "")
        grouped[identity].append({
            "date": date,
            "nav": nav,
            "name": name,
            "isin": isin or None,
            "folio_number": folio or None,
        })

    results = []
    for identity, observations in grouped.items():
        observations.sort(key=lambda item: item["date"])
        by_date = {}
        ambiguous_dates = set()
        for observation in observations:
            date = observation["date"]
            if date in by_date and not math.isclose(
                by_date[date], observation["nav"], rel_tol=1e-9, abs_tol=1e-9
            ):
                ambiguous_dates.add(date)
            by_date[date] = observation["nav"]

        if ambiguous_dates:
            results.append({
                "name": observations[0]["name"],
                "isin": observations[0]["isin"],
                "folio_number": observations[0]["folio_number"],
                "status": "ambiguous_data",
                "observation_count": len(by_date),
                "rejected_observation_count": rejected,
                "message": "Conflicting NAV observations exist for the same date; metrics were not calculated.",
                "nav_change_percentage": None,
                "max_drawdown_percentage": None,
                "volatility_per_observation_percentage": None,
            })
            continue

        clean = sorted(by_date.items())
        nav_values = [item[1] for item in clean]
        returns = [
            (nav_values[index] / nav_values[index - 1]) - 1
            for index in range(1, len(nav_values))
        ]

        peak = nav_values[0] if nav_values else None
        max_drawdown = 0.0
        for value in nav_values:
            peak = max(peak, value)
            max_drawdown = min(max_drawdown, (value / peak) - 1)

        enough_history = len(nav_values) >= MIN_OBSERVATIONS_FOR_VOLATILITY
        results.append({
            "name": observations[0]["name"],
            "isin": observations[0]["isin"],
            "folio_number": observations[0]["folio_number"],
            "status": "success" if len(nav_values) >= 2 else "insufficient_data",
            "observation_count": len(nav_values),
            "first_observation_date": clean[0][0].isoformat() if clean else None,
            "last_observation_date": clean[-1][0].isoformat() if clean else None,
            "nav_change_percentage": (
                round((nav_values[-1] / nav_values[0] - 1) * 100, 4)
                if len(nav_values) >= 2 else None
            ),
            "max_drawdown_percentage": (
                round(max_drawdown * 100, 4) if len(nav_values) >= 2 else None
            ),
            "volatility_per_observation_percentage": (
                round(stdev(returns) * 100, 4)
                if enough_history and len(returns) >= 2 else None
            ),
            "volatility_status": (
                "available" if enough_history else "insufficient_history"
            ),
            "message": (
                "NAV change is not a cash-flow-adjusted investor return. "
                "Volatility is per observation and is not annualized."
                if len(nav_values) >= 2 else
                "At least two valid dated NAV observations are required."
            ),
        })

    return {
        "method": "Dated NAV observations; no external market data is fetched.",
        "minimum_observations_for_volatility": MIN_OBSERVATIONS_FOR_VOLATILITY,
        "instrument_count": len(results),
        "rejected_observation_count": rejected,
        "instruments": results,
        "limitations": [
            "NAV change is not adjusted for distributions, fees, taxes or cash flows.",
            "Volatility is per observation and is not annualized.",
            "Historical NAV does not predict future performance.",
        ],
    }
