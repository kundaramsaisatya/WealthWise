
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
# RISK EXPLANATION
# --------------------------------------------------

def generate_risk_explanation(risk_data):

    print("RISK EXPLAINER INPUT:", risk_data)

    required_fields = [
        "total_value",
        "largest_holding",
        "top_three_concentration",
        "hhi",
        "normalized_hhi",
        "liquidity_percentage",
        "risk_flags"
    ]

    for field in required_fields:

        if field not in risk_data:
            raise ValueError(
                f"Missing risk metric: {field}"
            )

    portfolio_value = format_inr(
        risk_data["total_value"]
    )

    largest = risk_data["largest_holding"]

    risk_flags = risk_data["risk_flags"]

    # --------------------------------------------------
    # SYSTEM PROMPT
    # --------------------------------------------------

    system_prompt = """
You are WealthWise AI, a financial analytics assistant.

Your task is to explain supplied portfolio analytics
in clear, professional and understandable language.

STRICT RULES:

1. Currency is INR. Always use the ₹ symbol.
2. Use only the supplied portfolio metrics.
3. Never invent financial values or currency conversions.
4. Never change or estimate supplied numerical values.
5. Explain HHI only as a concentration measurement.
6. Do not classify HHI as low, moderate or high.
7. Liquidity percentage represents the reported Cash / Liquid
   allocation only.
8. Do not assume assets can be sold immediately.
9. Do not claim the portfolio is safe or risk-free.
10. An empty risk_flags list means only that configured
    thresholds were not breached.
11. Do not provide investment recommendations.
12. Mention limitations of the available information.
13. Do not introduce external financial data.
14. Do not invent missing portfolio information.

Explain the metrics in simple language.

Use these sections:

1. Portfolio Overview
2. Concentration Analysis
3. Liquidity Allocation
4. Risk Observations
5. Analysis Limitations

Keep the explanation concise and professional.
"""


    # --------------------------------------------------
    # USER PROMPT
    # --------------------------------------------------

    user_prompt = f"""
Explain the following portfolio analytics.

Currency: INR

Portfolio value: ₹{portfolio_value}

Largest holding:
{largest}

Top three concentration:
{risk_data["top_three_concentration"]}%

HHI:
{risk_data["hhi"]}

Normalized HHI:
{risk_data["normalized_hhi"]}

Cash / Liquid allocation:
{risk_data["liquidity_percentage"]}%

Risk flags:
{risk_flags}

Configured thresholds:
{risk_data.get("thresholds", {})}

Interpretation:
{risk_data.get("interpretation", "Not provided")}

Explain what these metrics indicate.

Do not change the supplied figures.

Do not introduce external financial information.
"""


    # --------------------------------------------------
    # GROQ RESPONSE
    # --------------------------------------------------

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ],
        temperature=0.1,
        max_completion_tokens=900
    )

    explanation = (
        response.choices[0].message.content or ""
    ).strip()

    if not explanation:
        raise ValueError(
            "AI returned an empty risk explanation."
        )

    # --------------------------------------------------
    # VERIFIED PORTFOLIO VALUE
    # --------------------------------------------------

    # This value is formatted by Python, not generated by AI.

    explanation += (
        "\n\nVerified portfolio value: "
        f"₹{portfolio_value}"
    )

    return explanation
