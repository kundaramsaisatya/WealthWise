from datetime import datetime, timezone
import math

from portfolio_analytics import normalize_asset_class


STALE_DOCUMENT_DAYS = 365
MIN_HISTORY_DAYS = 365
LIMITED_HISTORY_CONCENTRATION_PCT = 20

ISSUE_SEVERITY = {
    "Cost Basis": "Medium",
    "Sector Information": "Low",
    "Asset Classification": "Medium",
    "Instrument Identifier": "Low",
    "Report Date": "Low",
    "Data Freshness": "Medium",
    "Historical Coverage": "Low",
}


def parse_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (ValueError, TypeError):
        return None


def _normalized_identifier(value):
    return "".join(str(value or "").strip().upper().split())


def _normalized_name(value):
    return " ".join(str(value or "").strip().casefold().split())


def analyze_data_quality(portfolio, history_records=None, as_of_date=None):
    if not isinstance(portfolio, dict):
        raise ValueError("Invalid portfolio data.")

    holdings = portfolio.get("holdings", [])
    if not isinstance(holdings, list):
        raise ValueError("Invalid holdings data.")
    if any(not isinstance(holding, dict) for holding in holdings):
        raise ValueError("Invalid holding record in data-quality analysis.")

    now = parse_date(as_of_date) or datetime.now(timezone.utc)
    history_records = [] if history_records is None else history_records
    if not isinstance(history_records, list):
        raise ValueError("Invalid history records.")

    portfolio_report_date = portfolio.get("report_date") or portfolio.get("reportDate")
    issues = []
    holding_results = []
    total_holdings = len(holdings)

    missing_cost_basis = 0
    missing_sector = 0
    unknown_asset_class = 0
    missing_identifier = 0
    missing_report_date = 0
    stale_holdings = 0
    insufficient_history = 0
    complete_documents = 0
    sufficient_history_count = 0

    current_values = [holding.get("current_value") for holding in holdings]
    values_complete = all(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
        for value in current_values
    )
    total_current_value = sum(current_values) if values_complete else 0
    weights_available = values_complete and total_current_value > 0

    for holding in holdings:
        name = holding.get("name") or "Unknown Holding"
        document_issues = []
        history_issues = []
        freshness_issues = []

        if holding.get("invested_value") is None:
            missing_cost_basis += 1
            document_issues.append("Missing cost basis")

        sector_value = holding.get("sector")
        if not sector_value or str(sector_value).strip().lower() in ("unknown", "n/a"):
            missing_sector += 1
            document_issues.append("Missing sector information")

        if normalize_asset_class(holding.get("asset_class")) == "Unclassified":
            unknown_asset_class += 1
            document_issues.append("Unknown asset classification")

        isin = _normalized_identifier(holding.get("isin"))
        folio = _normalized_identifier(holding.get("folio_number"))
        if not (isin or folio):
            missing_identifier += 1
            document_issues.append("Missing instrument identifier")

        report_date = parse_date(
            holding.get("report_date")
            or holding.get("reportDate")
            or portfolio_report_date
        )
        if report_date is None:
            missing_report_date += 1
            document_issues.append("Report date unavailable")
        else:
            age_days = max(0, (now - report_date).days)
            if age_days > STALE_DOCUMENT_DAYS:
                stale_holdings += 1
                freshness_issues.append("Stale portfolio data")

        matching_history = []
        for record in history_records:
            if not isinstance(record, dict):
                continue
            record_isin = _normalized_identifier(record.get("isin"))
            record_folio = _normalized_identifier(record.get("folio_number"))
            if isin:
                matches = record_isin == isin and (
                    not folio or record_folio == folio
                )
            elif folio:
                matches = (
                    record_folio == folio
                    and _normalized_name(record.get("name")) == _normalized_name(name)
                )
            else:
                matches = _normalized_name(record.get("name")) == _normalized_name(name)
            if matches:
                matching_history.append(record)

        history_dates = [
            parsed for parsed in (
                parse_date(record.get("date") or record.get("report_date"))
                for record in matching_history
            ) if parsed is not None
        ]

        history_days = (
            (max(history_dates) - min(history_dates)).days
            if len(history_dates) >= 2 else None
        )

        if history_days is None or history_days < MIN_HISTORY_DAYS:
            insufficient_history += 1
            history_issues.append("Insufficient historical data")
        else:
            sufficient_history_count += 1

        if not document_issues:
            complete_documents += 1

        current_value = holding.get("current_value")
        weight_percentage = (
            round(current_value / total_current_value * 100, 2)
            if weights_available else None
        )

        holding_results.append({
            "name": name,
            "weight_percentage": weight_percentage,
            "history_days": history_days,
            "document_issues": document_issues,
            "history_issues": history_issues,
            "freshness_issues": freshness_issues,
            "document_status": "Complete" if not document_issues else "Needs Review",
            "history_status": "Sufficient" if not history_issues else "Insufficient History"
        })

    document_completeness = (
        round(complete_documents / total_holdings * 100, 2)
        if total_holdings else 0
    )
    historical_coverage = (
        round(sufficient_history_count / total_holdings * 100, 2)
        if total_holdings else 0
    )

    issue_counts = {
        "Cost Basis": missing_cost_basis,
        "Sector Information": missing_sector,
        "Asset Classification": unknown_asset_class,
        "Instrument Identifier": missing_identifier,
        "Report Date": missing_report_date,
        "Data Freshness": stale_holdings,
        "Historical Coverage": insufficient_history
    }
    messages = {
        "Cost Basis": "Some holdings have no recorded cost basis.",
        "Sector Information": "Sector exposure cannot be fully evaluated.",
        "Asset Classification": "Some holdings have unknown asset classifications.",
        "Instrument Identifier": "Some holdings lack instrument identifiers.",
        "Report Date": "Some holdings have no report date.",
        "Data Freshness": "Some holdings are based on outdated documents.",
        "Historical Coverage": (
            "Historical coverage is insufficient for reliable "
            "volatility and trend analysis."
        )
    }

    for issue_type, count in issue_counts.items():
        if count:
            issues.append({
                "type": issue_type,
                "severity": ISSUE_SEVERITY[issue_type],
                "count": count,
                "message": messages[issue_type]
            })

    return {
        "holding_count": total_holdings,
        "document_completeness_percentage": document_completeness,
        "historical_coverage_percentage": historical_coverage,
        "summary": {
            "missing_cost_basis": missing_cost_basis,
            "missing_sector": missing_sector,
            "unknown_asset_class": unknown_asset_class,
            "missing_identifier": missing_identifier,
            "missing_report_date": missing_report_date,
            "stale_holdings": stale_holdings,
            "insufficient_history": insufficient_history
        },
        "issues": issues,
        "holdings": holding_results,
        "thresholds": {
            "stale_document_days": STALE_DOCUMENT_DAYS,
            "minimum_history_days": MIN_HISTORY_DAYS,
            "limited_history_concentration_pct": LIMITED_HISTORY_CONCENTRATION_PCT
        },
        "interpretation": (
            "Document completeness and historical coverage are "
            "independent measurements. Insufficient history "
            "indicates uncertainty, not low investment risk."
        )
    }
