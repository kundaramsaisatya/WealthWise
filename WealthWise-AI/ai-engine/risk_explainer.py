import json
import os
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise RuntimeError(
        "GROQ_API_KEY is missing from environment."
    )

client = Groq(api_key=GROQ_API_KEY)

MODEL_NAME = "openai/gpt-oss-120b"

# gpt-oss is a reasoning model: reasoning tokens count toward this limit.
MAX_COMPLETION_TOKENS = 2000


# --------------------------------------------------
# INDIAN CURRENCY FORMATTING
# --------------------------------------------------

def format_inr(amount):

    amount = float(amount)

    if not amount == amount or abs(amount) == float("inf"):
        raise ValueError("Invalid portfolio amount.")

    negative = amount < 0

    amount = abs(amount)

    integer_part, decimal_part = f"{amount:.2f}".split(".")

    if len(integer_part) <= 3:
        formatted = integer_part

    else:

        last_three = integer_part[-3:]
        remaining = integer_part[:-3]

        groups = []

        while remaining:
            groups.insert(0, remaining[-2:])
            remaining = remaining[:-2]

        formatted = ",".join(
            groups + [last_three]
        )

    sign = "-" if negative else ""

    return f"{sign}{formatted}.{decimal_part}"


# --------------------------------------------------
# PROMPTS
# --------------------------------------------------

SYSTEM_PROMPT = """
You are WealthWise AI, a financial analytics assistant.

Your task is to explain supplied portfolio analytics
in clear, professional and understandable language.

STRICT RULES:

1. Currency is INR. Always use the ₹ symbol.
2. Use only the supplied portfolio facts.
3. Never invent financial values or currency conversions.
4. Never change or estimate supplied numerical values.
5. Explain HHI only as a concentration measurement.
6. Do not classify HHI as low, moderate or high.
7. Liquidity percentage covers only the holdings described in
   liquidity_basis. Do not assume assets can be sold immediately.
   Do not describe how quickly or slowly other assets can be sold,
   and do not state consequences of a flag beyond the flag's own
   message.
8. Do not claim the portfolio is safe or risk-free.
9. An empty risk_flags list means only that the configured
   thresholds were not breached.
10. State that a threshold was breached only when it appears in
    risk_flags. Quote thresholds exactly as supplied.
11. Do not provide investment recommendations. You may describe
    flagged items as points the reader may want to review with a
    qualified financial adviser.
12. Begin Portfolio Overview with one line saying which thresholds
    were used. If investor_profile says none was supplied, say the
    default thresholds were used and the analysis is not personalised.
    Only risk tolerance (if given) changed the thresholds; goal and
    horizon were not used in any calculation.
13. Do not mention equity limits or whether the equity share was
    tested. A fixed note about this is appended separately.
14. sub_category_allocation_top lists fund categories or styles
    (for example Mid Cap, Index Fund), NOT industry sectors. Never
    call them sectors, and say industry-sector exposure is not
    available.
15. In Analysis Limitations list ONLY the items in limitations_known.
    Do not claim any other data is missing. Cost basis is available
    when cost_basis_available is true.
16. If normalized HHI is unavailable, explicitly mention that it
    was not available.
17. Do not introduce external financial data or invent missing
    portfolio information.
18. Do not comment on these rules or on what you were or were not
    asked to interpret. Just give the explanation.
19. Never mention internal field names such as risk_flags,
    liquidity_basis or equity_limit_configured. Use plain words.
20. If data_sources is present, say in one short line in the Portfolio
    Overview how many reports were consolidated and how many duplicate
    records were counted once.
21. When you describe a risk flag, repeat only what its message says.
    Do not add other analyses it supposedly limits (for example, do not
    link historical coverage to sector exposure).

Use these sections:

1. Portfolio Overview (include the asset allocation percentages)
2. Concentration Analysis
3. Liquidity Allocation
4. Risk Observations
5. Analysis Limitations

Keep the explanation concise and professional.
"""


def build_risk_prompt(risk_data):
    """Validate the risk data and build (system_prompt, user_prompt)."""

    required_fields = [
        "total_value",
        "largest_holding",
        "risk_flags"
    ]

    for field in required_fields:
        if field not in risk_data:
            raise ValueError(
                f"Missing risk metric: {field}"
            )

    concentration = risk_data.get("concentration", {})
    liquidity = risk_data.get("liquidity", {})

    for field in ("hhi", "normalized_hhi", "top_three_concentration"):
        if field not in concentration:
            raise ValueError(
                f"Missing concentration metric: {field}"
            )

    if "percentage" not in liquidity:
        raise ValueError(
            "Missing liquidity percentage."
        )

    largest = risk_data["largest_holding"]
    normalized_hhi = concentration["normalized_hhi"]

    asset_allocation = [
        {
            "category": item.get("category"),
            "percentage": item.get("percentage"),
            "value": f"₹{format_inr(item.get('value', 0))}"
        }
        for item in risk_data.get("asset_allocation", [])
    ]

    sub_category_allocation = [
        {
            "category": item.get("category"),
            "percentage": item.get("percentage")
        }
        for item in risk_data.get("sector_allocation", [])[:6]
    ]

    thresholds = risk_data.get("thresholds", {})
    data_quality = risk_data.get("data_quality", {})
    dq_summary = data_quality.get("summary", {})

    total_invested = risk_data.get("total_invested")
    cost_basis_available = total_invested is not None

    consolidation = risk_data.get("consolidation") or {}

    data_sources = (
        {
            "reports_consolidated": consolidation.get("reports_used"),
            "report_date": consolidation.get("report_date"),
            "duplicate_records_counted_once": consolidation.get(
                "duplicates_removed"
            ),
            "valuation_differences_found": len(
                consolidation.get("valuation_differences") or []
            ),
        }
        if consolidation else None
    )

    # Limitations are decided by code, not by the model.
    limitations_known = [
        "No purchase dates or transaction history",
        "No NAV or price history, so no volatility or trend analysis",
        "No benchmark or peer-fund comparison",
        "No news or market data",
        "No industry-sector breakdown",
    ]

    if not cost_basis_available:
        limitations_known.append(
            "Cost basis is missing for some holdings"
        )

    if dq_summary.get("missing_report_date"):
        limitations_known.append(
            "Report date is missing for some holdings"
        )

    facts = {
        "currency": "INR",
        "portfolio_value": f"₹{format_inr(risk_data['total_value'])}",
        "holding_count": risk_data.get("holding_count"),

        "largest_holding": {
            "name": largest.get("name"),
            "weight_percent": largest.get("weight")
        },

        "top_three_concentration_percent": (
            concentration["top_three_concentration"]
        ),
        "hhi": concentration["hhi"],
        "normalized_hhi": (
            normalized_hhi if normalized_hhi is not None
            else "Not available"
        ),

        "cash_liquid_allocation_percent": liquidity["percentage"],
        "liquidity_basis": liquidity.get("basis", "Not provided"),

        "asset_allocation": asset_allocation,
        "equity_percentage": risk_data.get("equity_percentage"),
        "equity_limit_configured": (
            thresholds.get("max_equity_pct") is not None
        ),
        "sub_category_allocation_top": sub_category_allocation,

        "cost_basis_available": cost_basis_available,
        "total_invested": (
            f"₹{format_inr(total_invested)}"
            if cost_basis_available else None
        ),
        "unrealized_profit_loss": (
            f"₹{format_inr(risk_data['profit_loss'])}"
            if risk_data.get("profit_loss") is not None else None
        ),
        "unrealized_profit_loss_percent": risk_data.get(
            "profit_loss_percentage"
        ),

        "limitations_known": limitations_known,
        "data_sources": data_sources,

        "configured_thresholds": thresholds,
        "investor_profile": (
            risk_data.get("profile_used")
            or "None supplied (default thresholds, not personalised)"
        ),

        "risk_flags": risk_data["risk_flags"],
        "data_quality": data_quality,
        "interpretation": risk_data.get("interpretation", "Not provided"),
    }

    user_prompt = (
        "Explain the following portfolio analytics.\n\n"
        "PORTFOLIO FACTS (JSON, all values verified by code):\n"
        + json.dumps(facts, indent=2, ensure_ascii=False, default=str)
        + "\n\nExplain what these metrics indicate. "
          "Do not change the supplied figures. "
          "Do not introduce external financial information."
    )

    return SYSTEM_PROMPT, user_prompt


# --------------------------------------------------
# MODEL CALL
# --------------------------------------------------

def _call_model(messages):
    arguments = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": 0.1,
        "max_completion_tokens": MAX_COMPLETION_TOKENS,
    }

    try:
        return client.chat.completions.create(
            reasoning_effort="low",
            **arguments
        )
    except TypeError:
        # Older groq SDK without the reasoning_effort argument.
        return client.chat.completions.create(**arguments)


# --------------------------------------------------
# RISK EXPLANATION
# --------------------------------------------------

def generate_risk_explanation(risk_data):

    system_prompt, user_prompt = build_risk_prompt(risk_data)

    response = _call_model([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ])

    choice = response.choices[0]

    explanation = (choice.message.content or "").strip()

    if not explanation:
        raise ValueError(
            "AI returned an empty risk explanation."
        )

    if choice.finish_reason == "length":
        explanation += (
            "\n\n(The explanation was cut short. "
            "Please try again.)"
        )

    # Fixed notes appended from code, so they never depend on the model.
    thresholds = risk_data.get("thresholds", {})
    equity_percentage = risk_data.get("equity_percentage")

    if (
        thresholds.get("max_equity_pct") is None
        and equity_percentage is not None
    ):
        explanation += (
            "\n\nNote: no equity-share limit was configured, so the "
            f"equity weight of {equity_percentage}% was not tested "
            "against any threshold."
        )

    # Verified portfolio value, appended from code (not model output).
    explanation += (
        "\n\nVerified portfolio value: "
        f"₹{format_inr(risk_data['total_value'])}"
    )

    return explanation