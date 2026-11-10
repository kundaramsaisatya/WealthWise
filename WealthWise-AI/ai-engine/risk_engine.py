from math import isfinite

from portfolio_analytics import calculate_portfolio_metrics
from instrument_risk import analyze_instrument_nav_history
from data_quality import (
    analyze_data_quality,
    LIMITED_HISTORY_CONCENTRATION_PCT,
    MIN_HISTORY_DAYS,
)


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

    used_in_calculation = [
        "risk-tolerance profile thresholds" if tolerance
        else "default portfolio thresholds"
    ]
    if overrides:
        used_in_calculation.append("custom threshold overrides")

    horizon_rule = next(
        (
            rule for rule in GOAL_HORIZON_EQUITY_LIMITS
            if horizon is not None and horizon <= rule["max_horizon_years"]
        ),
        None,
    )
    if horizon_rule:
        used_in_calculation.append("illustrative goal-horizon equity exposure rule")

    profile_used = {
        "risk_tolerance": tolerance or None,
        "goal": profile.get("goal"),
        "horizon_years": horizon,
        "goal_horizon_equity_limit_pct": (
            horizon_rule["max_equity_pct"] if horizon_rule else None
        ),
        "used_in_calculation": used_in_calculation,
    }

    return thresholds or None, profile_used



# Transparent assessment rules. These are product heuristics, not validated
# financial-industry standards. Scores are intentionally unavailable when
# the relevant source metric or configured comparison limit is missing.
RISK_SCORE_RULES = {
    "version": "1.0",
    "concentration": "50 points at the configured limit; 100 points at or above twice the limit, using the higher of single-holding and top-three ratios.",
    "allocation": "50 points at the configured maximum equity allocation; 100 points at or above twice that limit.",
    "liquidity": "Linear shortfall score: 0 at or above the configured minimum and 100 at zero reported liquid allocation.",
    "data_quality": "100 minus the mean of document completeness and historical coverage percentages.",
}


def _bounded_score(value):
    return round(max(0.0, min(100.0, value)), 2)


def calculate_transparent_risk_score(portfolio, data_quality, instrument_history):
    """Return an explainable heuristic score and explicitly report coverage."""
    dimensions = []

    concentration = portfolio.get("concentration") or {}
    limits = portfolio.get("thresholds") or {}
    largest_weight = (portfolio.get("largest_holding") or {}).get("weight_percentage")
    top_three = concentration.get("top_three_concentration")
    single_limit = limits.get("max_single_holding_pct")
    top_three_limit = limits.get("max_top_three_pct")

    concentration_ratios = []
    if isinstance(largest_weight, (int, float)) and single_limit:
        concentration_ratios.append(largest_weight / single_limit)
    if isinstance(top_three, (int, float)) and top_three_limit:
        concentration_ratios.append(top_three / top_three_limit)
    if concentration_ratios:
        ratio = max(concentration_ratios)
        score = _bounded_score(ratio * 50)
        dimensions.append({
            "id": "concentration",
            "label": "Concentration",
            "score": score,
            "status": "scored",
            "evidence": {
                "largest_holding_percentage": largest_weight,
                "single_holding_limit_percentage": single_limit,
                "top_three_percentage": top_three,
                "top_three_limit_percentage": top_three_limit,
                "highest_limit_utilization": round(ratio * 100, 2),
            },
            "rule": RISK_SCORE_RULES["concentration"],
        })

    sector_exposure = portfolio.get("sector_exposure") or {}
    sector_limit = limits.get("max_sector_pct")
    largest_sector = sector_exposure.get("largest")
    if sector_limit is not None and largest_sector and sector_limit > 0:
        sector_ratio = largest_sector.get("portfolio_percentage", 0) / sector_limit
        dimensions.append({
            "id": "sector_concentration",
            "label": "Sector concentration",
            "score": _bounded_score(sector_ratio * 50),
            "status": "scored",
            "evidence": {
                "largest_sector": largest_sector.get("name"),
                "largest_sector_percentage": largest_sector.get("portfolio_percentage"),
                "configured_limit_percentage": sector_limit,
                "identified_sector_coverage_percentage": sector_exposure.get("coverage_percentage"),
            },
            "rule": "Score 50 at the explicitly configured sector limit and 100 at or above twice that limit; only identified sector values are grouped.",
        })
    else:
        dimensions.append({
            "id": "sector_concentration",
            "label": "Sector concentration",
            "score": None,
            "status": "not_scored",
            "reason": "No sector limit is configured or no identified sector exposure is available.",
        })

    issuer_exposure = portfolio.get("issuer_exposure") or {}
    dimensions.append({
        "id": "issuer_exposure",
        "label": "Issuer exposure",
        "score": None,
        "status": "informational_only",
        "evidence": {
            "identified_issuer_coverage_percentage": issuer_exposure.get("coverage_percentage"),
            "largest_identified_issuer": (issuer_exposure.get("largest") or {}).get("name"),
            "largest_identified_issuer_percentage": (issuer_exposure.get("largest") or {}).get("portfolio_percentage"),
        },
        "reason": "Issuer exposure is displayed only when explicit issuer metadata is supplied; it is not scored without a validated issuer taxonomy and thresholds.",
    })

    equity = portfolio.get("equity_percentage")
    equity_limit = limits.get("max_equity_pct")
    if isinstance(equity, (int, float)) and isinstance(equity_limit, (int, float)) and equity_limit > 0:
        ratio = equity / equity_limit
        dimensions.append({
            "id": "allocation",
            "label": "Equity allocation",
            "score": _bounded_score(ratio * 50),
            "status": "scored",
            "evidence": {
                "equity_percentage": equity,
                "configured_limit_percentage": equity_limit,
            },
            "rule": RISK_SCORE_RULES["allocation"],
        })
    else:
        dimensions.append({
            "id": "allocation",
            "label": "Equity allocation",
            "score": None,
            "status": "not_scored",
            "reason": "No configured maximum equity allocation is available; no allocation risk score is inferred.",
        })

    liquidity = portfolio.get("liquidity") or {}
    liquid_pct = liquidity.get("percentage")
    min_liquidity = limits.get("min_liquidity_pct")
    if isinstance(liquid_pct, (int, float)) and isinstance(min_liquidity, (int, float)) and min_liquidity > 0:
        shortfall = max(0.0, min_liquidity - liquid_pct)
        score = _bounded_score(shortfall / min_liquidity * 100)
        dimensions.append({
            "id": "liquidity",
            "label": "Reported liquidity",
            "score": score,
            "status": "scored",
            "evidence": {
                "reported_liquid_percentage": liquid_pct,
                "configured_minimum_percentage": min_liquidity,
                "shortfall_percentage_points": round(shortfall, 2),
                "liquidity_basis": liquidity.get("basis"),
            },
            "rule": RISK_SCORE_RULES["liquidity"],
        })
    else:
        dimensions.append({
            "id": "liquidity",
            "label": "Reported liquidity",
            "score": None,
            "status": "not_scored",
            "reason": "Reported liquidity or its configured minimum is unavailable.",
        })

    document_pct = data_quality.get("document_completeness_percentage")
    history_pct = data_quality.get("historical_coverage_percentage")
    if all(isinstance(value, (int, float)) for value in (document_pct, history_pct)):
        quality = (document_pct + history_pct) / 2
        dimensions.append({
            "id": "data_quality",
            "label": "Data quality",
            "score": _bounded_score(100 - quality),
            "status": "scored",
            "evidence": {
                "document_completeness_percentage": document_pct,
                "historical_coverage_percentage": history_pct,
                "quality_average_percentage": round(quality, 2),
            },
            "rule": RISK_SCORE_RULES["data_quality"],
        })
    else:
        dimensions.append({
            "id": "data_quality",
            "label": "Data quality",
            "score": None,
            "status": "not_scored",
            "reason": "Document completeness and historical coverage are required.",
        })

    instruments = (instrument_history or {}).get("instruments", [])
    usable_volatility = [
        item.get("volatility_per_observation_percentage")
        for item in instruments
        if item.get("volatility_status") == "available"
        and isinstance(item.get("volatility_per_observation_percentage"), (int, float))
    ]
    dimensions.append({
        "id": "historical_volatility",
        "label": "Historical volatility",
        "score": None,
        "status": "informational_only",
        "evidence": {
            "instruments_with_volatility": len(usable_volatility),
            "highest_volatility_per_observation_percentage": (
                max(usable_volatility) if usable_volatility else None
            ),
        },
        "reason": (
            "Volatility is shown as an observation-level statistic, not scored: "
            "observation frequency and instrument risk characteristics are not "
            "standardized sufficiently for a comparable portfolio score."
        ),
    })

    scored = [item for item in dimensions if item["status"] == "scored"]
    score = round(sum(item["score"] for item in scored) / len(scored), 2) if scored else None
    return {
        "version": RISK_SCORE_RULES["version"],
        "score": score,
        "label": (
            "Illustrative risk indicator" if score is not None
            else "Insufficient evidence"
        ),
        "status": "available" if score is not None else "insufficient_data",
        "scored_dimension_count": len(scored),
        "total_dimension_count": len(dimensions),
        "coverage_percentage": round(len(scored) / len(dimensions) * 100, 2),
        "dimensions": dimensions,
        "aggregation_method": "Unweighted arithmetic mean of available dimension scores; unavailable dimensions are excluded and shown explicitly.",
        "rules": RISK_SCORE_RULES,
        "limitations": [
            "This is an illustrative heuristic, not a validated industry score, credit rating, forecast or suitability assessment.",
            "The score depends on configured portfolio thresholds and the supplied data; changing either can change the result.",
            "Historical volatility is not included in the aggregate because observation frequencies may differ and values are not annualized.",
            "Sector, issuer, duration, credit and instrument overlap risks are not scored unless reliable source data and explicit rules are added.",
            "A higher score indicates more threshold pressure or weaker data quality under these rules; it does not predict loss probability.",
        ],
    }


def analyze_portfolio_risk(
    portfolio_data,
    history_records=None,
    as_of_date=None,
    profile=None,
    external_nav_status=None,
    data_quality_history_records=None
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
        history_records=(
            data_quality_history_records
            if data_quality_history_records is not None else history_records
        ),
        as_of_date=as_of_date
    )
    instrument_history_analysis = analyze_instrument_nav_history(history_records)

    risk_flags = list(portfolio.get("risk_flags", []))

    # Flag material allocations when the available history is too short
    # to support reliable historical risk estimates.
    for holding in data_quality.get("holdings", []):
        weight = holding.get("weight_percentage")
        if (
            holding.get("history_status") == "Insufficient History"
            and isinstance(weight, (int, float))
            and not isinstance(weight, bool)
            and weight >= LIMITED_HISTORY_CONCENTRATION_PCT
        ):
            name = holding.get("name") or "A holding"
            risk_flags.append({
                "type": "Limited-History Concentration",
                "severity": "Medium",
                "holding_name": name,
                "holding_percentage": weight,
                "configured_limit": LIMITED_HISTORY_CONCENTRATION_PCT,
                "message": (
                    f"{name} represents {weight}% of the portfolio but has "
                    f"less than {MIN_HISTORY_DAYS} days of available history. "
                    "Its risk cannot be reliably estimated from the available "
                    "historical data; review the allocation and obtain more evidence."
                )
            })


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

    transparent_risk_score = calculate_transparent_risk_score(
        portfolio,
        data_quality,
        instrument_history_analysis
    )

    return {
        "transparent_risk_score": transparent_risk_score,
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
        "instrument_history_analysis": instrument_history_analysis,
        "external_nav_status": external_nav_status,
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
