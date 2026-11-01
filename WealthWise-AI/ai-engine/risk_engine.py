
from portfolio_analytics import calculate_portfolio_metrics


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

# Illustrative thresholds, not universal financial standards.

MAX_SINGLE_HOLDING = 25
MAX_TOP_THREE_HOLDINGS = 60
MIN_LIQUIDITY = 10


# --------------------------------------------------
# PORTFOLIO RISK ANALYSIS
# --------------------------------------------------

def analyze_portfolio_risk(portfolio_data):

    portfolio = calculate_portfolio_metrics(portfolio_data)

    holdings = portfolio.get("holdings", [])

    if not holdings:
        raise ValueError(
            "Cannot calculate portfolio risk without valid holdings."
        )

    # --------------------------------------------------
    # CONCENTRATION
    # --------------------------------------------------

    sorted_holdings = sorted(
        holdings,
        key=lambda item: item["current_value"],
        reverse=True
    )

    largest = sorted_holdings[0]

    concentration = portfolio.get("concentration", {})

    top_three_weight = concentration.get(
        "top_three_concentration"
    )

    if top_three_weight is None:

        top_three_weight = sum(
            item["weight_percentage"]
            for item in sorted_holdings[:3]
        )

    top_three_weight = round(
        float(top_three_weight),
        2
    )

    # --------------------------------------------------
    # LIQUIDITY
    # --------------------------------------------------

    liquidity_data = portfolio.get("liquidity", {})

    liquidity = float(
        liquidity_data.get("percentage", 0)
    )

    # --------------------------------------------------
    # RISK FLAGS
    # --------------------------------------------------

    risk_flags = []

    if largest["weight_percentage"] > MAX_SINGLE_HOLDING:

        risk_flags.append({
            "type": "High Individual Concentration",
            "severity": "Warning",
            "message": (
                f"{largest['name']} represents "
                f"{largest['weight_percentage']}% "
                "of the portfolio."
            )
        })

    if top_three_weight > MAX_TOP_THREE_HOLDINGS:

        risk_flags.append({
            "type": "Top Holdings Concentration",
            "severity": "Warning",
            "message": (
                "The three largest holdings represent "
                f"{top_three_weight}% of the portfolio."
            )
        })

    if liquidity < MIN_LIQUIDITY:

        risk_flags.append({
            "type": "Low Liquidity",
            "severity": "Warning",
            "message": (
                "Cash and liquid allocation is only "
                f"{round(liquidity, 2)}%."
            )
        })

    # --------------------------------------------------
    # RISK RESULT
    # --------------------------------------------------

    return {

        "client_id": portfolio["client_id"],

        "total_value": portfolio["total_value"],

        "largest_holding": {
            "name": largest["name"],
            "weight": largest["weight_percentage"]
        },

        "top_three_concentration": top_three_weight,

        "hhi": concentration.get("hhi", 0),

        "normalized_hhi": concentration.get(
            "normalized_hhi",
            0
        ),

        "liquidity_percentage": round(liquidity, 2),

        "risk_flags": risk_flags,

        "risk_flag_count": len(risk_flags),

        "thresholds": {
            "max_single_holding": MAX_SINGLE_HOLDING,
            "max_top_three_holdings": MAX_TOP_THREE_HOLDINGS,
            "min_liquidity": MIN_LIQUIDITY
        },

        "interpretation": (
            "These are illustrative concentration and liquidity "
            "checks. They do not measure total investment risk, "
            "investment suitability, volatility or future losses."
        )
    }
