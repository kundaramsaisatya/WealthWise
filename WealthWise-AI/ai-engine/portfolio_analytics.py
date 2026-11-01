
import math


MAX_SINGLE_HOLDING = 25
MIN_LIQUIDITY_PERCENTAGE = 10


def validate_number(value, field, holding_name, allow_none=False):
    if value is None and allow_none:
        return None

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Invalid {field} for {holding_name}.")

    try:
        if not math.isfinite(value) or value < 0:
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"Invalid {field} for {holding_name}.")

    return float(value)


def normalize_asset_class(asset_class):
    value = str(asset_class or "").strip().lower()

    aliases = {
        "equity": "Equity",
        "stocks": "Equity",
        "stock": "Equity",
        "mutual fund equity": "Equity",
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


def calculate_portfolio_metrics(portfolio):

    if not isinstance(portfolio, dict):
        raise ValueError("Invalid portfolio data.")

    holdings = portfolio.get("holdings")

    if not isinstance(holdings, list) or not holdings:
        raise ValueError("Portfolio has no holdings.")

    currency = portfolio.get("currency", "INR")

    if not isinstance(currency, str) or not currency.strip():
        raise ValueError("Invalid portfolio currency.")

    validated_holdings = []

    for holding in holdings:

        if not isinstance(holding, dict):
            raise ValueError("Invalid holding record.")

        name = holding.get("name")

        if not isinstance(name, str) or not name.strip():
            raise ValueError("Holding name is missing.")

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

        asset_class = normalize_asset_class(
            holding.get("asset_class")
        )

        validated_holdings.append({
            **holding,
            "name": name.strip(),
            "asset_class": asset_class,
            "current_value": current_value,
            "invested_value": invested_value
        })

    total_value = sum(
        item["current_value"]
        for item in validated_holdings
    )

    if not math.isfinite(total_value) or total_value <= 0:
        raise ValueError("Portfolio total must be positive.")

    # Asset allocation

    allocation = {}

    for holding in validated_holdings:

        asset = holding["asset_class"]

        allocation[asset] = (
            allocation.get(asset, 0)
            + holding["current_value"]
        )

    allocation_result = []

    for asset, value in allocation.items():

        allocation_result.append({
            "asset_class": asset,
            "value": round(value, 2),
            "percentage": round(
                (value / total_value) * 100,
                2
            )
        })

    # Holding weights and profit/loss

    enriched_holdings = []

    total_invested = 0
    known_invested_value = True

    exact_weights = []

    for holding in validated_holdings:

        exact_weight = (
            holding["current_value"] / total_value
        ) * 100

        exact_weights.append(exact_weight)

        invested_value = holding["invested_value"]

        profit_loss = None
        profit_loss_percentage = None

        if invested_value is not None:

            total_invested += invested_value

            profit_loss = round(
                holding["current_value"] - invested_value,
                2
            )

            if invested_value > 0:

                profit_loss_percentage = round(
                    (profit_loss / invested_value) * 100,
                    2
                )

        else:
            known_invested_value = False

        enriched_holdings.append({
            **holding,
            "weight_percentage": round(exact_weight, 2),
            "profit_loss": profit_loss,
            "profit_loss_percentage": profit_loss_percentage
        })

    # Concentration calculations

    sorted_holdings = sorted(
        enriched_holdings,
        key=lambda item: item["current_value"],
        reverse=True
    )

    largest_holding = sorted_holdings[0]

    hhi = sum(
        weight ** 2
        for weight in exact_weights
    )

    top_three_concentration = sum(
        item["weight_percentage"]
        for item in sorted_holdings[:3]
    )

    # Liquidity

    liquid_value = allocation.get("Cash / Liquid", 0)

    liquidity_percentage = (
        liquid_value / total_value
    ) * 100

    # Risk flags

    risk_flags = []

    if largest_holding["weight_percentage"] > MAX_SINGLE_HOLDING:

        risk_flags.append({
            "type": "Concentration",
            "message": (
                f"{largest_holding['name']} represents "
                f"{largest_holding['weight_percentage']}% "
                "of the portfolio."
            )
        })

    if top_three_concentration > 60:

        risk_flags.append({
            "type": "Concentration",
            "message": (
                f"The top three holdings represent "
                f"{round(top_three_concentration, 2)}% "
                "of the portfolio."
            )
        })

    if liquidity_percentage < MIN_LIQUIDITY_PERCENTAGE:

        risk_flags.append({
            "type": "Liquidity",
            "message": (
                "Cash and liquid allocation is below 10%."
            )
        })

    # Portfolio profit/loss

    portfolio_profit_loss = None
    portfolio_profit_loss_percentage = None

    if known_invested_value:

        portfolio_profit_loss = round(
            total_value - total_invested,
            2
        )

        if total_invested > 0:

            portfolio_profit_loss_percentage = round(
                (portfolio_profit_loss / total_invested) * 100,
                2
            )

    return {
        "client_id": str(portfolio.get("client_id", "")),
        "currency": currency.strip().upper(),

        "total_value": round(total_value, 2),

        "total_invested": (
            round(total_invested, 2)
            if known_invested_value
            else None
        ),

        "profit_loss": portfolio_profit_loss,

        "profit_loss_percentage": (
            portfolio_profit_loss_percentage
        ),

        "holding_count": len(enriched_holdings),

        "asset_allocation": allocation_result,

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
            "normalized_hhi": round(hhi / 10000, 4),
            "top_three_concentration": round(
                top_three_concentration, 2
            )
        },

        "liquidity": {
            "value": round(liquid_value, 2),
            "percentage": round(liquidity_percentage, 2)
        },

        "risk_flags": risk_flags,

        "disclaimer": (
            "Illustrative analytics based on portfolio data. "
            "Risk thresholds are configurable and are not "
            "investment advice or a suitability assessment."
        )
    }
