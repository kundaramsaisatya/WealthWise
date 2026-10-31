def calculate_portfolio_metrics(portfolio):

    if not portfolio:
        raise ValueError("Portfolio not found")

    holdings = portfolio["holdings"]

    if not holdings:
        raise ValueError("Portfolio has no holdings")

    if any(h["value"] < 0 for h in holdings):
        raise ValueError("Negative holding values are not supported")

    total_value = sum(h["value"] for h in holdings)

    if total_value <= 0:
        raise ValueError("Portfolio total must be positive")

    allocation = {}

    for holding in holdings:
        asset = holding["asset_class"]

        allocation[asset] = (
            allocation.get(asset, 0) + holding["value"]
        )

    allocation_result = []

    for asset, value in allocation.items():
        percentage = (value / total_value) * 100

        allocation_result.append({
            "asset_class": asset,
            "value": value,
            "percentage": round(percentage, 2)
        })

    enriched_holdings = []

    for holding in holdings:
        weight = (holding["value"] / total_value) * 100

        enriched_holdings.append({
            **holding,
            "weight_percentage": round(weight, 2)
        })

    largest_holding = max(
        enriched_holdings,
        key=lambda h: h["value"]
    )

    hhi = sum(
        h["weight_percentage"] ** 2
        for h in enriched_holdings
    )

    liquid_value = allocation.get("Cash / Liquid", 0)

    liquidity_percentage = (
        liquid_value / total_value
    ) * 100

    risk_flags = []

    if largest_holding["weight_percentage"] > 25:
        risk_flags.append({
            "type": "Concentration",
            "message": "A single holding exceeds 25% of the portfolio."
        })

    if liquidity_percentage < 10:
        risk_flags.append({
            "type": "Liquidity",
            "message": "Cash and liquid allocation is below 10%."
        })

    return {
        "client_id": str(portfolio["client_id"]),
        "currency": portfolio["currency"],
        "total_value": total_value,
        "asset_allocation": allocation_result,

        "largest_holding": {
            "name": largest_holding["name"],
            "value": largest_holding["value"],
            "weight_percentage": largest_holding["weight_percentage"]
        },

        "holdings": enriched_holdings,

        "concentration": {
            "hhi": round(hhi, 2),
            "normalized_hhi": round(hhi / 10000, 4)
        },

        "liquidity": {
            "value": liquid_value,
            "percentage": round(liquidity_percentage, 2)
        },

        "risk_flags": risk_flags,

        "disclaimer": (
            "Illustrative analytics based on portfolio data. "
            "Not investment advice or a suitability assessment."
        )
    }