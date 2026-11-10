"""Read-only historical mutual-fund NAV retrieval from AMFI's public portal.

This module does not persist data or infer investor returns. It returns source-
attributed NAV observations for an explicitly supplied ISIN and date range.
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


AMFI_HISTORY_URL = "https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx"
AMFI_SOURCE = "AMFI India"
MAX_RANGE_DAYS = 90
MAX_RESPONSE_BYTES = 25 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 20
SCHEME_TYPES = (1, 2, 3)


class AMFINavProviderError(Exception):
    """Raised when AMFI NAV history cannot be retrieved or validated."""


def _normalise_isin(value):
    return "".join(str(value or "").upper().split())


def _parse_nav(value):
    try:
        nav = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not nav.is_finite() or nav <= 0:
        return None
    return nav


def _parse_history_date(value):
    try:
        return datetime.strptime(value.strip(), "%d-%b-%Y").date()
    except (AttributeError, ValueError):
        return None


def parse_amfi_history(text, requested_isin):
    """Parse AMFI's 8-column history rows and retain matching ISIN observations."""
    target_isin = _normalise_isin(requested_isin)
    if not target_isin:
        raise ValueError("A valid ISIN is required.")

    observations = []
    for line in (text or "").splitlines():
        columns = [part.strip() for part in line.strip().split(";")]
        if len(columns) < 8:
            continue

        scheme_code, scheme_name = columns[0], columns[1]
        growth_isin = _normalise_isin(columns[2])
        reinvestment_isin = _normalise_isin(columns[3])
        if target_isin not in {growth_isin, reinvestment_isin}:
            continue

        nav = _parse_nav(columns[4])
        nav_date = _parse_history_date(columns[7])
        if nav is None or nav_date is None or not scheme_code or not scheme_name:
            continue

        observations.append({
            "scheme_code": scheme_code,
            "scheme_name": scheme_name,
            "isin": target_isin,
            "nav": str(nav),
            "date": nav_date.isoformat(),
            "source": AMFI_SOURCE,
        })

    return observations


def fetch_amfi_nav_history(isin, start_date, end_date):
    """Fetch matching NAV observations across AMFI's three scheme types.

    AMFI's public history download accepts a maximum 90-day window. This
    function rejects wider windows instead of silently truncating the request.
    """
    target_isin = _normalise_isin(isin)
    if not target_isin:
        raise ValueError("A valid ISIN is required.")
    if not isinstance(start_date, date) or not isinstance(end_date, date):
        raise ValueError("start_date and end_date must be datetime.date values.")
    if start_date > end_date:
        raise ValueError("start_date must not be after end_date.")
    if (end_date - start_date).days >= MAX_RANGE_DAYS:
        raise ValueError("AMFI history requests must cover no more than 90 calendar days.")

    from_date = start_date.strftime("%d-%b-%Y")
    to_date = end_date.strftime("%d-%b-%Y")
    all_observations = []

    for scheme_type in SCHEME_TYPES:
        query = urlencode({
            "tp": scheme_type,
            "frmdt": from_date,
            "todt": to_date,
        })
        request = Request(
            f"{AMFI_HISTORY_URL}?{query}",
            headers={"User-Agent": "WealthWiseAI/1.0 (mutual-fund NAV history)"},
        )
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise AMFINavProviderError(
                "AMFI NAV history is temporarily unavailable."
            ) from error

        if len(body) > MAX_RESPONSE_BYTES:
            raise AMFINavProviderError("AMFI NAV history response exceeded the size limit.")

        try:
            content = body.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise AMFINavProviderError("AMFI returned an unreadable NAV history response.") from error

        all_observations.extend(parse_amfi_history(content, target_isin))

    # A scheme can appear in more than one response after AMFI corrections.
    unique = {}
    for item in all_observations:
        key = (item["scheme_code"], item["date"])
        existing = unique.get(key)
        if existing and existing["nav"] != item["nav"]:
            raise AMFINavProviderError(
                "AMFI returned conflicting NAV values for the same scheme and date."
            )
        unique[key] = item

    return sorted(unique.values(), key=lambda item: (item["date"], item["scheme_code"]))
