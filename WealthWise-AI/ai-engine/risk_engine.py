from portfolio_analytics import calculate_portfolio_metrics

# Demonstration thresholds, not universal financial standards.
MAX_SINGLE_HOLDING = 25
MAX_TOP_THREE_HOLDINGS = 60
MIN_LIQUIDITY = 10


def analyze_portfolio_risk(portfolio_data):

    portfolio = calculate_portfolio_metrics(portfolio_data)

    holdings = sorted(
        portfolio["holdings"],
        key=lambda item: item["value"],
        reverse=True
    )

    largest = holdings[0]

    top_three_weight = sum(
        holding["weight_percentage"]
        for holding in holdings[:3]
    )

    liquidity = portfolio["liquidity"]["percentage"]

    risk_flags = []

    if largest["weight_percentage"] > MAX_SINGLE_HOLDING:
        risk_flags.append({
            "type": "High Individual Concentration",
            "severity": "Warning",
            "message": (
                f"{largest['name']} represents "
                f"{largest['weight_percentage']}% of the portfolio."
            )
        })

    if top_three_weight > MAX_TOP_THREE_HOLDINGS:
        risk_flags.append({
            "type": "Top Holdings Concentration",
            "severity": "Warning",
            "message": (
                f"The three largest holdings represent "
                f"{round(top_three_weight, 2)}% of the portfolio."
            )
        })

    if liquidity < MIN_LIQUIDITY:
        risk_flags.append({
            "type": "Low Liquidity",
            "severity": "Warning",
            "message": (
                f"Cash and liquid allocation is only {liquidity}%."
            )
        })

    return {
        "client_id": portfolio["client_id"],
        "total_value": portfolio["total_value"],

        "largest_holding": {
            "name": largest["name"],
            "weight": largest["weight_percentage"]
        },

        "top_three_concentration": round(top_three_weight, 2),
        "hhi": portfolio["concentration"]["hhi"],
        "normalized_hhi": portfolio["concentration"]["normalized_hhi"],
        "liquidity_percentage": liquidity,
        "risk_flags": risk_flags,

        "thresholds": {
            "max_single_holding": MAX_SINGLE_HOLDING,
            "max_top_three_holdings": MAX_TOP_THREE_HOLDINGS,
            "min_liquidity": MIN_LIQUIDITY
        },

        "interpretation": (
            "These are illustrative concentration and liquidity checks. "
            "They do not measure total investment risk or suitability."
        )
    }