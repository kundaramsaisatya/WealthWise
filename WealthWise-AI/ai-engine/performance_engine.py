
from datetime import datetime
from typing import Any


def parse_report_date(value: Any):
    """Convert a report date into a date object."""
    if not value:
        return None

    if isinstance(value, datetime):
        return value.date()

    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return None


def calculate_portfolio_performance(snapshots: list):
    """
    Calculate changes in portfolio value across dated snapshots.

    These are portfolio value changes, not time-weighted returns or XIRR.
    """

    if not isinstance(snapshots, list) or not snapshots:
        return {
            "status": "insufficient_data",
            "message": "No historical portfolio snapshots available.",
            "snapshot_count": 0,
            "history": [],
            "summary": None
        }

    valid_snapshots = []
    rejected_snapshots = []

    for snapshot in snapshots:
        report_date = parse_report_date(snapshot.get("report_date"))
        total_value = snapshot.get("total_value")

        try:
            total_value = float(total_value)
        except (ValueError, TypeError):
            rejected_snapshots.append({
                "reason": "Invalid portfolio value"
            })
            continue

        if report_date is None or total_value < 0:
            rejected_snapshots.append({
                "reason": "Invalid report date or negative portfolio value"
            })
            continue

        valid_snapshots.append({
            "date": report_date,
            "total_value": total_value
        })

    # Sort snapshots chronologically
    valid_snapshots.sort(key=lambda item: item["date"])

    # Avoid silently choosing between conflicting snapshots on the same date
    dates = [item["date"] for item in valid_snapshots]

    if len(dates) != len(set(dates)):
        return {
            "status": "ambiguous_data",
            "message": (
                "Multiple snapshots exist for the same report date. "
                "Consolidate them before calculating performance."
            ),
            "snapshot_count": len(valid_snapshots),
            "rejected_snapshots": rejected_snapshots,
            "history": [],
            "summary": None
        }

    history = []

    for index, snapshot in enumerate(valid_snapshots):
        previous_value = (
            valid_snapshots[index - 1]["total_value"]
            if index > 0 else None
        )

        change = None
        change_percentage = None

        if previous_value is not None:
            change = snapshot["total_value"] - previous_value

            if previous_value > 0:
                change_percentage = (change / previous_value) * 100

        history.append({
            "report_date": snapshot["date"].isoformat(),
            "portfolio_value": round(snapshot["total_value"], 2),
            "change_from_previous": (
                round(change, 2) if change is not None else None
            ),
            "change_percentage": (
                round(change_percentage, 2)
                if change_percentage is not None else None
            )
        })

    if len(valid_snapshots) < 2:
        return {
            "status": "insufficient_data",
            "message": "At least two valid dated snapshots are required.",
            "snapshot_count": len(valid_snapshots),
            "rejected_snapshots": rejected_snapshots,
            "history": history,
            "summary": None
        }

    first = valid_snapshots[0]
    latest = valid_snapshots[-1]

    absolute_change = latest["total_value"] - first["total_value"]

    percentage_change = None
    if first["total_value"] > 0:
        percentage_change = (
            absolute_change / first["total_value"]
        ) * 100

    total_days = (latest["date"] - first["date"]).days

    return {
        "status": "success",
        "message": (
            "Portfolio value history calculated. "
            "External cash flows are not adjusted."
        ),
        "snapshot_count": len(valid_snapshots),
        "rejected_snapshots": rejected_snapshots,
        "history": history,
        "summary": {
            "starting_value": round(first["total_value"], 2),
            "latest_value": round(latest["total_value"], 2),
            "absolute_change": round(absolute_change, 2),
            "percentage_change": (
                round(percentage_change, 2)
                if percentage_change is not None else None
            ),
            "period_days": total_days,
            "xirr_available": False
        }
    }
