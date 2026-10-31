import re
import os
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODEL_NAME = "openai/gpt-oss-120b"
def format_inr(amount):
    amount = float(amount)

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

        formatted = ",".join(groups + [last_three])

    return f"{formatted}.{decimal_part}"
def generate_risk_explanation(risk_data):

    print("RISK EXPLAINER INPUT:", risk_data)
    
    system_prompt = """
    You are WealthWise AI, a financial analytics assistant.

    Explain portfolio metrics accurately using only supplied data.

    STRICT RULES:
    1. Currency is INR. Always use ₹, never $.
    2. Never invent financial values or currency conversions.
    3. Never classify HHI as low, moderate or high unless
    explicit classification thresholds are supplied.
    4. Explain HHI as a concentration measurement only.
    5. Liquidity percentage represents the Cash / Liquid
    allocation in the supplied portfolio data.
    6. Do not assume assets can be sold without price impact.
    7. An empty risk_flags list means only that configured
    thresholds were not breached.
    8. Never claim the portfolio is safe or risk-free.
    9. Do not provide investment recommendations.
    10. Mention limitations of the available data.
    11. NEVER use words such as low, moderate, or high
    to classify HHI concentration.
    12. NEVER claim cash or liquid assets are immediately
    accessible or can be sold without price impact.
    13. Describe liquidity strictly as the reported allocation.
    14. Always preserve the exact portfolio value supplied. 

    Keep the explanation concise and structured.
    """

    user_prompt = f"""
    Explain these portfolio metrics.

    Currency: INR
    Portfolio value: ₹{format_inr(risk_data["total_value"])}
    Largest holding: {risk_data["largest_holding"]}
    Top three concentration: {risk_data["top_three_concentration"]}%
    HHI: {risk_data["hhi"]}
    Normalized HHI: {risk_data["normalized_hhi"]}
    Cash / Liquid allocation: {risk_data["liquidity_percentage"]}%

    Risk flags: {risk_data["risk_flags"]}

    Explain:
    1. Portfolio concentration.
    2. Liquidity allocation.
    3. Configured risk observations.
    4. Limitations of the analysis.

    Do not introduce external financial data.
    """

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.2,
        max_completion_tokens=700
    )

    explanation = response.choices[0].message.content or ""

    # Remove incorrect portfolio value statements
    explanation = re.sub(
        r"The portfolio value is reported as ₹0[^.\n]*[.]?",
        "",
        explanation,
        flags=re.IGNORECASE
    )

    # Add the verified value from Python
    portfolio_value = format_inr(risk_data["total_value"])

    explanation += (
        f"\n\nVerified portfolio value: ₹{portfolio_value}"
    )

    return explanation