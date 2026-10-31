
import os
import json
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq

from document_processor import extract_text_from_pdf

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODEL_NAME = "openai/gpt-oss-120b"


def extract_portfolio_from_pdf(file_path):

    pages = extract_text_from_pdf(file_path)

    if not pages:
        raise ValueError("No readable text found in PDF.")

    document_text = "\n\n".join(
        f"PAGE {page['page']}:\n{page['text']}"
        for page in pages
    )

    prompt = f"""
    Extract structured portfolio information from this financial report.

    Return ONLY valid JSON in this format:

    {{
        "currency": "INR",
        "total_value": 1000000,
        "report_date": "31 October 2026",
        "holdings": [
            {{
                "name": "HDFC Bank",
                "asset_class": "Equity",
                "value": 300000,
                "page": 1
            }}
        ]
    }}

   STRICT RULES:
    1. Extract only information explicitly present in the document.
    2. Never invent missing investment names or values.
    3. Values must be numeric, without currency symbols or commas.
    4. Preserve the currency stated in the document.
    5. Include the correct source page for every holding.
    6. Do not treat totals or subtotals as individual holdings.
    7. If information is missing, use null.
    8. Do not include explanatory text outside JSON.

    9. For portfolio statements, use MARKET VALUE as the holding value.
    10. NEVER use Cost Value when Market Value is available.
    11. For CAS statements, total_value must represent the
        total market value of the investments.
    12. If individual market values are available but the total
        is missing, calculate total_value by summing those
        market values.
    13. Do not extract industry-wide statistics as personal holdings.

    FINANCIAL DOCUMENT:

    {document_text}
    """

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": "Return only valid JSON. No markdown, no explanations. Never invent financial information."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0,
        max_completion_tokens=8000
    )
    print("FINISH REASON:", response.choices[0].finish_reason)
    print("GROQ RESPONSE:", repr(response.choices[0].message.content))

    raw_response = response.choices[0].message.content

    print("GROQ RAW RESPONSE:", repr(raw_response))

    if not raw_response or not raw_response.strip():
        raise ValueError("Groq returned an empty response.")

    try:
        result = json.loads(raw_response)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Groq returned invalid JSON: {raw_response[:500]}"
        ) from error
    

    if not isinstance(result.get("holdings"), list):
        raise ValueError("Invalid portfolio holdings format.")

    return result
