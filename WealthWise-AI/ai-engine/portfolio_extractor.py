
import os
import json
import time
import math
import re
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

from document_processor import extract_text_from_pdf


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise ValueError("GROQ_API_KEY is missing from the .env file.")

client = Groq(api_key=api_key)

MODEL_NAME = "openai/gpt-oss-120b"

BATCH_SIZE = 1
BATCH_DELAY = 20


# --------------------------------------------------
# PAGE BATCHING
# --------------------------------------------------

def create_page_batches(pages, batch_size=BATCH_SIZE):
    return [
        pages[i:i + batch_size]
        for i in range(0, len(pages), batch_size)
    ]


# --------------------------------------------------
# DATE VALIDATION
# --------------------------------------------------

def normalize_report_date(value):

    if value is None:
        return None

    if not isinstance(value, str):
        return None

    value = value.strip()

    if not value:
        return None

    # Accept only unambiguous ISO date format.
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None

    try:
        parsed = date.fromisoformat(value)
        return parsed.isoformat()

    except ValueError:
        return None


# --------------------------------------------------
# VALIDATION HELPERS
# --------------------------------------------------

def validate_number(value, field_name, holding_name):

    if value is None:
        return None

    if isinstance(value, bool):
        raise ValueError(
            f"Invalid {field_name} for {holding_name}."
        )

    if not isinstance(value, (int, float)):
        raise ValueError(
            f"Non-numeric {field_name} for {holding_name}: {value}"
        )

    if not math.isfinite(value):
        raise ValueError(
            f"Non-finite {field_name} for {holding_name}."
        )

    if field_name in ("current_value", "invested_value") and value < 0:
        raise ValueError(
            f"Negative {field_name} for {holding_name}."
        )

    return round(float(value), 2)


# --------------------------------------------------
# EXTRACT HOLDINGS FROM ONE BATCH
# --------------------------------------------------

def extract_batch_from_groq(batch_pages):

    document_text = "\n\n".join(
        f"PAGE {page['page']}:\n{page['text']}"
        for page in batch_pages
    )

    prompt = f"""
Extract individual investment holdings from this financial document.

Return ONLY valid JSON in this structure:

{{
    "report_date": "2026-10-31",
    "holdings": [
        {{
            "name": "HDFC Bank",
            "asset_class": "Equity",
            "sub_category": "Large Cap",
            "isin": "INE040A01034",
            "folio_number": "123456",
            "quantity": 10,
            "invested_value": 100000,
            "current_value": 115000,
            "profit_loss": 15000,
            "profit_loss_percentage": 15,
            "source": "Mutual Fund Statement",
            "average_nav": 100,
            "current_nav": 115,
            "page": 1
        }}
    ]
}}

STRICT EXTRACTION RULES:

1. Extract only investments actually belonging to the investor.

2. Do not extract benchmark data, market statistics, sector
   totals, asset allocation percentages or summary totals
   as individual holdings.

3. Extract individual investment records wherever available.

4. Do not invent, estimate or calculate missing financial values.

5. Return null for unavailable fields.

6. Use market value or current valuation as current_value.

7. Use cost value, purchase value or invested amount as
   invested_value only when explicitly available.

8. Extract ISIN, folio number and quantity exactly as printed.

9. Extract profit/loss and its percentage only when explicitly
   available in the document.

10. Preserve the original page number.

11. Do not extract underlying stocks of mutual funds as
    separately owned investments.

12. Do not combine different investments into one holding.

13. Do not remove records merely because their names are
    identical. Different folios or accounts may represent
    separate investments.

14. Do not treat a repeated investment name as proof that
    two records are duplicates.

15. Do not extract scheme names from loads, fees, exit load
    descriptions, disclaimers or explanatory text.

16. A scheme name alone is not an investment record.
    It must have actual holding-related financial information.

17. Do not interpret investor names, account holder names,
    nominees or contact details as investment names.

18. Return numeric values without currency symbols or commas.

19. Use INR as the document currency unless another currency
    is explicitly identified. Do not convert currencies.

20. Return an empty holdings array if the pages contain no
    actual individual investment records.

21. Return report_date as the statement's valuation date,
    portfolio as-of date, or statement generation date,
    only when explicitly identifiable.

22. Do not use transaction dates, purchase dates, due dates,
    financial year dates, or upload dates as report_date.

23. If the statement date cannot be identified confidently,
    return null.

24. Return report_date in YYYY-MM-DD format only.

25. Do not include explanatory text outside the JSON.

DOCUMENT:

{document_text}
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a financial document extraction system. "
                    "Extract only explicitly supported investment data. "
                    "Never invent financial values or dates. "
                    "Return valid JSON only."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0,
        max_completion_tokens=4000
    )

    choice = response.choices[0]

    print("FINISH REASON:", choice.finish_reason)

    raw_response = choice.message.content

    if not raw_response:
        raise ValueError("Groq returned an empty response.")

    try:
        result = json.loads(raw_response)

    except json.JSONDecodeError as error:
        print("INVALID GROQ RESPONSE:")
        print(raw_response)

        raise ValueError(
            "Groq returned invalid JSON."
        ) from error

    if not isinstance(result, dict):
        raise ValueError("Invalid batch response.")

    if not isinstance(result.get("holdings"), list):
        raise ValueError("Invalid batch holdings.")

    for holding in result["holdings"]:

        if not isinstance(holding, dict):
            raise ValueError("Invalid holding returned by Groq.")

    report_date = normalize_report_date(
        result.get("report_date")
    )

    print("EXTRACTED BATCH HOLDINGS:", result["holdings"])
    print("EXTRACTED REPORT DATE:", report_date)

    return {
        "holdings": result["holdings"],
        "report_date": report_date
    }


# --------------------------------------------------
# NORMALIZE AND VALIDATE HOLDINGS
# --------------------------------------------------

def normalize_holding(holding):

    name = holding.get("name")

    if not isinstance(name, str) or not name.strip():
        raise ValueError("Invalid holding name.")

    asset_class = holding.get("asset_class")

    if not isinstance(asset_class, str) or not asset_class.strip():
        raise ValueError(
            f"Invalid asset class for {name}."
        )

    page = holding.get("page")

    if (
        isinstance(page, bool)
        or not isinstance(page, int)
        or page < 1
    ):
        raise ValueError(
            f"Invalid page number for {name}."
        )

    normalized = {
        "name": name.strip(),
        "asset_class": asset_class.strip(),
        "sub_category": holding.get("sub_category"),
        "isin": holding.get("isin"),
        "folio_number": holding.get("folio_number"),

        "quantity": validate_number(
            holding.get("quantity"),
            "quantity",
            name
        ),

        "invested_value": validate_number(
            holding.get("invested_value"),
            "invested_value",
            name
        ),

        "current_value": validate_number(
            holding.get("current_value"),
            "current_value",
            name
        ),

        "profit_loss": validate_number(
            holding.get("profit_loss"),
            "profit_loss",
            name
        ),

        "profit_loss_percentage": validate_number(
            holding.get("profit_loss_percentage"),
            "profit_loss_percentage",
            name
        ),

        "source": holding.get("source"),

        "average_nav": validate_number(
            holding.get("average_nav"),
            "average_nav",
            name
        ),

        "current_nav": validate_number(
            holding.get("current_nav"),
            "current_nav",
            name
        ),

        "page": page
    }

    for field in [
        "sub_category",
        "isin",
        "folio_number",
        "source"
    ]:

        value = normalized[field]

        if isinstance(value, str):
            normalized[field] = value.strip() or None

    return normalized


# --------------------------------------------------
# EXTRACT PORTFOLIO FROM COMPLETE PDF
# --------------------------------------------------

def extract_portfolio_from_pdf(file_path):

    pages = extract_text_from_pdf(file_path)

    if not pages:
        raise ValueError("No readable text found in PDF.")

    batches = create_page_batches(
        pages,
        batch_size=BATCH_SIZE
    )

    all_holdings = []
    report_dates = []

    for index, batch in enumerate(batches):

        print(
            f"Processing batch {index + 1}/{len(batches)}"
        )

        batch_result = extract_batch_from_groq(batch)

        all_holdings.extend(
            batch_result["holdings"]
        )

        if batch_result["report_date"]:
            report_dates.append(
                batch_result["report_date"]
            )

        if index < len(batches) - 1:

            print(
                f"Waiting {BATCH_DELAY} seconds before next batch..."
            )

            time.sleep(BATCH_DELAY)

    if not all_holdings:
        raise ValueError("No portfolio holdings found.")

    # --------------------------------------------------
    # NORMALIZE RECORDS
    # --------------------------------------------------

    normalized_holdings = []

    for holding in all_holdings:
        normalized_holdings.append(
            normalize_holding(holding)
        )

    # Do not deduplicate here.
    # Reconciliation belongs in the Node backend.

    # --------------------------------------------------
    # RESOLVE REPORT DATE
    # --------------------------------------------------

    distinct_dates = set(report_dates)

    if len(distinct_dates) == 1:
        report_date = distinct_dates.pop()
    else:
        # Conflicting or unavailable dates must not be guessed.
        report_date = None

    # --------------------------------------------------
    # CALCULATE TOTAL ONLY WHEN COMPLETE
    # --------------------------------------------------

    all_values_available = all(
        holding["current_value"] is not None
        for holding in normalized_holdings
    )

    if all_values_available:

        calculated_total = sum(
            holding["current_value"]
            for holding in normalized_holdings
        )

        total_value = round(calculated_total, 2)

    else:
        total_value = None

    # --------------------------------------------------
    # BUILD RESULT
    # --------------------------------------------------

    result = {
        "currency": "INR",
        "total_value": total_value,
        "report_date": report_date,
        "holdings": normalized_holdings
    }

    print("EXTRACTION COMPLETED")
    print("Total extracted records:", len(normalized_holdings))
    print("Portfolio value:", result["total_value"])
    print("Statement date:", result["report_date"])

    return result
