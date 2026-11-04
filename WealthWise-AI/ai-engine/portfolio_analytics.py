import math
import re


# --------------------------------------------------
# DEFAULT THRESHOLDS (configurable per call)
# --------------------------------------------------

MAX_SINGLE_HOLDING = 25
MAX_TOP_THREE_CONCENTRATION = 60
MIN_LIQUIDITY_PERCENTAGE = 10

DEFAULT_THRESHOLDS = {
    "max_single_holding_pct": MAX_SINGLE_HOLDING,
    "max_top_three_pct": MAX_TOP_THREE_CONCENTRATION,
    "min_liquidity_pct": MIN_LIQUIDITY_PERCENTAGE,
    # No equity limit unless an investor profile supplies one.
    "max_equity_pct": None,
}

# Sub-categories that count as liquid even though their asset class
# is "Debt" (for example a liquid mutual fund).
LIQUID_SUB_CATEGORIES = {"liquid", "overnight", "money market"}


def resolve_thresholds(thresholds):
    """Merge caller thresholds over the defaults and validate them."""
    merged = dict(DEFAULT_THRESHOLDS)

    if thresholds is None:
        return merged

    if not isinstance(thresholds, dict):
        raise ValueError("Invalid thresholds.")

    for key, value in thresholds.items():

        if key not in DEFAULT_THRESHOLDS:
            continue

        if value is None:
            if key == "max_equity_pct":
                merged[key] = None
                continue
            raise ValueError(f"Invalid threshold: {key}.")

        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError(f"Invalid threshold: {key}.")

        merged[key] = float(value) if isinstance(value, float) else value

    return merged


# --------------------------------------------------
# VALIDATION HELPERS
# --------------------------------------------------

def validate_number(value, field, holding_name, allow_none=False):
    if value is None and allow_none:
        return None

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Invalid {field} for {holding_name}.")

    if not math.isfinite(value) or value < 0:
        raise ValueError(f"Invalid {field} for {holding_name}.")

    return float(value)


def normalize_asset_class(asset_class):
    value = str(asset_class or "").strip().lower()

    # "Equity - Large Cap" -> "equity"
    value = re.split(r"\s+[-\u2013\u2014]\s+", value, maxsplit=1)[0].strip()

    aliases = {
        "equity": "Equity",
        "stocks": "Equity",
        "stock": "Equity",
        "mutual fund equity": "Equity",
        "hybrid": "Hybrid",
        "debt": "Debt",
        "fixed income": "Debt",
        "bonds": "Debt",
        "gold": "Gold",
        "precious metals": "Gold",
        "cash": "Cash / Liquid",
        "liquid": "Cash / Liquid",
        "liquid fund": "Cash / Liquid",
        "cash / liquid": "Cash / Liquid",
        "cash and equivalents": "Cash / Liquid",
        "real estate": "Real Estate",
        "reit": "Real Estate",
    }

    return aliases.get(value, "Other")


def calculate_hhi(weights):
    return sum(weight ** 2 for weight in weights)


def calculate_normalized_hhi(hhi, holding_count):
    if holding_count <= 1:
        return None

    minimum_hhi = 10000 / holding_count

    return round(
        (hhi - minimum_hhi) / (10000 - minimum_hhi),
        4
    )


def calculate_allocation(holdings, total_value, field):
    allocation = {}

    for holding in holdings:
        category = str(holding.get(field) or "Unknown").strip()

        if not category:
            category = "Unknown"

        allocation[category] = (
            allocation.get(category, 0)
            + holding["current_value"]
        )

    return [
        {
            "category": category,
            "value": round(value, 2),
            "percentage": round(value / total_value * 100, 2)
        }
        for category, value in sorted(
            allocation.items(),
            key=lambda item: item[1],
            reverse=True
        )
    ]


# --------------------------------------------------
# MAIN METRICS
# --------------------------------------------------

def calculate_portfolio_metrics(portfolio, thresholds=None):

    if not isinstance(portfolio, dict):
        raise ValueError("Invalid portfolio data.")

    limits = resolve_thresholds(thresholds)

    holdings = portfolio.get("holdings")

    if not isinstance(holdings, list) or not holdings:
        raise ValueError("Portfolio has no holdings.")

    currency = portfolio.get("currency", "INR")

    if not isinstance(currency, str) or not currency.strip():
        raise ValueError("Invalid portfolio currency.")

    currency = currency.strip().upper()

    validated_holdings = []

    for holding in holdings:

        if not isinstance(holding, dict):
            raise ValueError("Invalid holding record.")

        name = holding.get("name")

        if not isinstance(name, str) or not name.strip():
            raise ValueError("Holding name is missing.")

        holding_currency = holding.get("currency")

        if holding_currency:
            if str(holding_currency).strip().upper() != currency:
                raise ValueError(
                    f"Mixed currencies detected for {name}. "
                    "Convert holdings into one currency before analysis."
                )

        current_value = validate_number(
            holding.get("current_value"),
            "current value",
            name
        )

        invested_value = validate_number(
            holding.get("invested_value"),
            "invested value",
            name,
            allow_none=True
        )

        asset_class_raw = str(
            holding.get("asset_class") or ""
        ).strip()

        asset_class = normalize_asset_class(asset_class_raw)

        # The Excel extractor provides "sub_category", not "sector".
        sector = str(
            holding.get("sector")
            or holding.get("sub_category")
            or "Unknown"
        ).strip()

        validated_holdings.append({
            **holding,
            "name": name.strip(),
            "asset_class": asset_class,
            "sector": sector or "Unknown",
            "current_value": current_value,
            "invested_value": invested_value
        })

    total_value = sum(
        holding["current_value"]
        for holding in validated_holdings
    )

    if not math.isfinite(total_value) or total_value <= 0:
        raise ValueError("Portfolio total must be positive.")

    # Asset allocation

    asset_allocation = calculate_allocation(
        validated_holdings,
        total_value,
        "asset_class"
    )

    # Sector allocation

    sector_allocation = calculate_allocation(
        validated_holdings,
        total_value,
        "sector"
    )

    # Holding weights and returns

    enriched_holdings = []

    total_invested = 0
    known_invested_value = 0
    missing_cost_basis_count = 0

    for holding in validated_holdings:

        weight = (
            holding["current_value"] / total_value
        ) * 100

        invested_value = holding["invested_value"]

        profit_loss = None
        profit_loss_percentage = None

        if invested_value is not None:

            known_invested_value += invested_value
            total_invested += invested_value

            profit_loss = round(
                holding["current_value"] - invested_value,
                2
            )

            if invested_value > 0:
                profit_loss_percentage = round(
                    profit_loss / invested_value * 100,
                    2
                )

        else:
            missing_cost_basis_count += 1

        enriched_holdings.append({
            **holding,
            "weight_percentage": round(weight, 2),
            "profit_loss": profit_loss,
            "profit_loss_percentage": profit_loss_percentage
        })

    # Concentration

    sorted_holdings = sorted(
        enriched_holdings,
        key=lambda item: item["current_value"],
        reverse=True
    )

    largest_holding = sorted_holdings[0]

    # Weights must be sorted largest-first so that the top-three figure
    # really is the three largest holdings, not the first three rows.
    exact_weights = sorted(
        (
            holding["current_value"] / total_value * 100
            for holding in enriched_holdings
        ),
        reverse=True
    )

    hhi = calculate_hhi(exact_weights)

    top_three_concentration = sum(exact_weights[:3])

    normalized_hhi = calculate_normalized_hhi(
        hhi,
        len(enriched_holdings)
    )

    # Liquidity: the Cash / Liquid asset class plus liquid-type funds.

    liquid_value = sum(
        holding["current_value"]
        for holding in enriched_holdings
        if holding["asset_class"] == "Cash / Liquid"
        or str(holding.get("sub_category") or "").strip().lower()
        in LIQUID_SUB_CATEGORIES
    )

    liquidity_percentage = (
        liquid_value / total_value
    ) * 100

    # Equity share

    equity_percentage = next(
        (
            item["percentage"]
            for item in asset_allocation
            if item["category"] == "Equity"
        ),
        0.0
    )

    # Portfolio profit and loss

    complete_cost_basis = missing_cost_basis_count == 0

    portfolio_profit_loss = None
    portfolio_profit_loss_percentage = None

    if complete_cost_basis:

        portfolio_profit_loss = round(
            total_value - total_invested,
            2
        )

        if total_invested > 0:
            portfolio_profit_loss_percentage = round(
                portfolio_profit_loss / total_invested * 100,
                2
            )

    # Data quality

    unknown_asset_count = sum(
        1 for holding in validated_holdings
        if holding["asset_class"] == "Other"
    )

    unknown_sector_count = sum(
        1 for holding in validated_holdings
        if holding["sector"] == "Unknown"
    )

    # Risk flags

    risk_flags = []

    if largest_holding["weight_percentage"] > limits["max_single_holding_pct"]:
        risk_flags.append({
            "type": "Concentration",
            "severity": "High",
            "message": (
                f"{largest_holding['name']} represents "
                f"{largest_holding['weight_percentage']}% "
                "of the portfolio, above the configured limit of "
                f"{limits['max_single_holding_pct']}%."
            )
        })

    if top_three_concentration > limits["max_top_three_pct"]:
        risk_flags.append({
            "type": "Concentration",
            "severity": "Medium",
            "message": (
                f"The top three holdings represent "
                f"{round(top_three_concentration, 2)}% "
                "of the portfolio, above the configured limit of "
                f"{limits['max_top_three_pct']}%."
            )
        })

    if liquidity_percentage < limits["min_liquidity_pct"]:
        risk_flags.append({
            "type": "Liquidity",
            "severity": "Medium",
            "message": (
                "Cash and liquid allocation is "
                f"{round(liquidity_percentage, 2)}%, below the "
                f"configured minimum of {limits['min_liquidity_pct']}%."
            )
        })

    if (
        limits["max_equity_pct"] is not None
        and equity_percentage > limits["max_equity_pct"]
    ):
        risk_flags.append({
            "type": "Allocation",
            "severity": "Medium",
            "message": (
                f"Equity represents {equity_percentage}% of the "
                "portfolio, above the configured limit of "
                f"{limits['max_equity_pct']}%."
            )
        })

    if missing_cost_basis_count:
        risk_flags.append({
            "type": "Data Quality",
            "severity": "Medium",
            "message": (
                f"Cost basis is missing for "
                f"{missing_cost_basis_count} holdings. "
                "Complete portfolio returns cannot be calculated."
            )
        })

    if unknown_asset_count:
        risk_flags.append({
            "type": "Data Quality",
            "severity": "Medium",
            "message": (
                f"{unknown_asset_count} holdings have "
                "unclassified asset types."
            )
        })

    if unknown_sector_count:
        risk_flags.append({
            "type": "Data Quality",
            "severity": "Low",
            "message": (
                f"Sector information is unavailable for "
                f"{unknown_sector_count} holdings."
            )
        })

    return {
        "client_id": str(portfolio.get("client_id", "")),
        "currency": currency,

        "total_value": round(total_value, 2),

        "total_invested": (
            round(total_invested, 2)
            if complete_cost_basis else None
        ),

        "known_invested_value": round(
            known_invested_value, 2
        ),

        "profit_loss": portfolio_profit_loss,

        "profit_loss_percentage": (
            portfolio_profit_loss_percentage
        ),

        "holding_count": len(enriched_holdings),

        "asset_allocation": asset_allocation,

        "sector_allocation": sector_allocation,

        "largest_holding": {
            "name": largest_holding["name"],
            "value": largest_holding["current_value"],
            "weight_percentage": (
                largest_holding["weight_percentage"]
            )
        },

        "holdings": enriched_holdings,

        "concentration": {
            "hhi": round(hhi, 2),
            "normalized_hhi": normalized_hhi,
            "top_three_concentration": round(
                top_three_concentration, 2
            )
        },

        "liquidity": {
            "value": round(liquid_value, 2),
            "percentage": round(liquidity_percentage, 2),
            "basis": (
                "Cash / Liquid asset class plus liquid, overnight "
                "and money market sub-categories"
            )
        },

        "equity_percentage": equity_percentage,

        "thresholds": limits,

        "data_quality": {
            "cost_basis_complete": complete_cost_basis,
            "missing_cost_basis_count": missing_cost_basis_count,
            "unknown_asset_count": unknown_asset_count,
            "unknown_sector_count": unknown_sector_count,
            "data_completeness_percentage": round(
                (
                    (len(enriched_holdings) - missing_cost_basis_count)
                    / len(enriched_holdings)
                ) * 100,
                2
            )
        },

        "risk_flags": risk_flags,

        "return_method": "Simple return based on current value and cost basis",

        "xirr_available": False,

        "disclaimer": (
            "Illustrative analytics based on supplied portfolio data. "
            "Risk thresholds are configurable and are not investment "
            "advice or a suitability assessment."
        )
    }