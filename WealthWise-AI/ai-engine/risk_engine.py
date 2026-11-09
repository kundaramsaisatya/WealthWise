from math import isfinite

from portfolio_analytics import calculate_portfolio_metrics
from data_quality import analyze_data_quality


# Illustrative, configurable limits. These are not investment advice
# or a suitability assessment and require compliance approval.
PROFILE_THRESHOLDS = {
    "conservative": {
        "max_single_holding_pct": 15,
        "max_top_three_pct": 45,
        "min_liquidity_pct": 10,
        "max_equity_pct": 40,
    },
    "moderate": {
        "max_single_holding_pct": 25,
        "max_top_three_pct": 60,
        "min_liquidity_pct": 10,
        "max_equity_pct": 70,
    },
    "aggressive": {
        "max_single_holding_pct": 30,
        "max_top_three_pct": 70,
        "min_liquidity_pct": 5,
        "max_equity_pct": 90,
    },
}

VALID_SEVERITIES = {"High", "Medium", "Low"}

GOAL_HORIZON_EQUITY_LIMITS = [
    {"max_horizon_years": 1, "max_equity_pct": 20, "severity": "High"},
    {"max_horizon_years": 3, "max_equity_pct": 40, "severity": "Medium"},
    {"max_horizon_years": 5, "max_equity_pct": 60, "severity": "Medium"},
]

ALREADY_COVERED_ISSUE_TYPES = {
    "Cost Basis",
    "Sector Information",
    "Asset Classification",
}


def resolve_profile(profile):
    """Return validated thresholds and a transparent profile summary."""
    if profile is None:
        return None, None

    if not isinstance(profile, dict):
        raise ValueError("Invalid investor profile.")

    tolerance = str(profile.get("risk_tolerance") or "").strip().lower()
    thresholds = {}

    if tolerance:
        if tolerance not in PROFILE_THRESHOLDS:
            raise ValueError(
                "risk_tolerance must be one of: "
                + ", ".join(sorted(PROFILE_THRESHOLDS))
            )
        thresholds.update(PROFILE_THRESHOLDS[tolerance])

    overrides = profile.get("thresholds")
    if overrides is not None:
        if not isinstance(overrides, dict):
            raise ValueError("Invalid profile thresholds.")
        thresholds.update(overrides)

    horizon = profile.get("horizon_years")
    if horizon is not None:
        if isinstance(horizon, bool):
            raise ValueError("horizon_years must be a finite non-negative number.")
        try:
            horizon = float(horizon)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("horizon_years must be a finite non-negative number.")
        if not isfinite(horizon) or horizon < 0:
            raise ValueError("horizon_years must be a finite non-negative number.")

    profile_used = {
        "risk_tolerance": tolerance or None,
        "goal": profile.get("goal"),
        "horizon_years": horizon,
        "used_in_calculation": [
            "risk_tolerance thresholds" if tolerance else "custom thresholds only"
        ],
    }

    return thresholds or None, profile_used


def analyze_portfolio_risk(
    portfolio_data,
    history_records=None,
    as_of_date=None,
    profile=None
):
    thresholds, profile_used = resolve_profile(profile)

    portfolio = calculate_portfolio_metrics(
        portfolio_data,
        thresholds=thresholds
    )

    holdings = portfolio.get("holdings", [])
    if not holdings:
        raise ValueError(
            "Cannot calculate portfolio risk without valid holdings."
        )

    concentration = portfolio.get("concentration", {})
    liquidity_data = portfolio.get("liquidity", {})
    largest = portfolio.get("largest_holding", {})

    data_quality = analyze_data_quality(
        portfolio_data,
        history_records=history_records,
        as_of_date=as_of_date
    )

    risk_flags = list(portfolio.get("risk_flags", []))

    if profile_used and profile_used.get("horizon_years") is not None:
        horizon_years = profile_used["horizon_years"]

        for rule in GOAL_HORIZON_EQUITY_LIMITS:
            if horizon_years <= rule["max_horizon_years"]:
                equity_pct = portfolio.get("equity_percentage", 0)

                if equity_pct > rule["max_equity_pct"]:
                    risk_flags.append({
                        "type": "Goal Horizon Risk",
                        "severity": rule["severity"],
                        "message": (
                            f"Equity exposure is {equity_pct}% for a goal "
                            f"with {horizon_years:.2f} years remaining. "
                            f"This exceeds the illustrative "
                            f"{rule['max_equity_pct']}% equity limit "
                            "for this time horizon."
                        )
                    })
                break

    for issue in data_quality.get("issues", []):
        if issue.get("type") in ALREADY_COVERED_ISSUE_TYPES:
            continue

        severity = issue.get("severity")
        if severity not in VALID_SEVERITIES:
            severity = "Low"

        risk_flags.append({
            "type": "Data Quality",
            "severity": severity,
            "message": issue.get(
                "message",
                "Data quality issue detected."
            )
        })

    return {
        "client_id": portfolio.get("client_id"),
        "currency": portfolio.get("currency"),
        "total_value": portfolio.get("total_value"),
        "total_invested": portfolio.get("total_invested"),
        "profit_loss": portfolio.get("profit_loss"),
        "profit_loss_percentage": portfolio.get("profit_loss_percentage"),
        "holding_count": portfolio.get("holding_count"),
        "largest_holding": {
            "name": largest.get("name"),
            "weight": largest.get("weight_percentage")
        },
        "concentration": concentration,
        "liquidity": liquidity_data,
        "asset_allocation": portfolio.get("asset_allocation", []),
        "sector_allocation": portfolio.get("sector_allocation", []),
        "equity_percentage": portfolio.get("equity_percentage"),
        "thresholds": portfolio.get("thresholds", {}),
        "profile_used": profile_used,
        "data_quality": data_quality,
        "consolidation": (
            portfolio_data.get("consolidation")
            if isinstance(portfolio_data, dict) else None
        ),
        "risk_flags": risk_flags,
        "risk_flag_count": len(risk_flags),
        "interpretation": (
            "This assessment evaluates portfolio concentration, liquidity, "
            "asset allocation and data quality against configured thresholds. "
            "Insufficient historical data indicates uncertainty, not low "
            "investment risk. This is not a complete risk or suitability "
            "assessment."
        )
    }
