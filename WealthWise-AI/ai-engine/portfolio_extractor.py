import os
import json
import time
import math
import re
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv
from groq import (
    Groq,
    RateLimitError,
    APIStatusError,
    BadRequestError,
)

from document_processor import extract_text_from_pdf
from cams_cas_extractor import extract_cams_cas


# ==================================================
# CONFIGURATION
# ==================================================

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise ValueError("GROQ_API_KEY is missing from the .env file.")

client = Groq(api_key=api_key)
app = FastAPI()

MODEL_NAME = "openai/gpt-oss-120b"

BATCH_SIZE = 1
BATCH_DELAY = 10
MAX_COMPLETION_TOKENS = 1500
MAX_RETRIES = 4
MAX_SPLIT_DEPTH = 5

# Page splitting configuration
LINE_OVERLAP = 2
CHAR_OVERLAP = 500
MIN_LINES_TO_SPLIT = 4
MIN_CHARS_TO_SPLIT = 1000

ALLOWED_ASSET_CLASSES = {
    "Equity",
    "Debt",
    "Hybrid",
    "Liquid",
    "Gold",
    "Real Estate",
    "Cash",
    "Unclassified",
}

ALLOWED_CURRENCIES = {
    "INR", "USD", "EUR", "GBP", "JPY",
    "CAD", "AUD", "SGD", "CHF", "AED",
}


# ==================================================
# CUSTOM EXCEPTIONS
# ==================================================

class TruncatedResponseError(Exception):
    pass


class RequestTooLargeError(Exception):
    pass


# ==================================================
# ERROR DETECTION
# ==================================================

def is_truncation_error(error):
    message = str(error).lower()

    return (
        "json_validate_failed" in message
        or "max completion tokens reached" in message
        or "maximum completion tokens" in message
    )


# ==================================================
# PAGE BATCHING
# ==================================================

def create_page_batches(pages, batch_size=BATCH_SIZE):

    return [
        pages[i:i + batch_size]
        for i in range(0, len(pages), batch_size)
    ]


# ==================================================
# VALIDATION
# ==================================================

def normalize_report_date(value):

    if not isinstance(value, str):
        return None

    value = value.strip()

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None

    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def validate_number(value, field_name, holding_name):

    if value is None:
        return None

    if isinstance(value, bool):
        raise ValueError(
            f"Invalid {field_name} for {holding_name}: {value}"
        )

    if not isinstance(value, (int, float)):
        raise ValueError(
            f"Invalid {field_name} for {holding_name}: {value}"
        )

    if not math.isfinite(value):
        raise ValueError(
            f"Non-finite {field_name} for {holding_name}."
        )

    if field_name in ("current_value", "invested_value") and value < 0:
        raise ValueError(
            f"Negative {field_name} for {holding_name}."
        )

    number = float(value)

    # Preserve fractional units and NAV precision. Rounding every numeric
    # field to two decimals turned CAS quantities such as 0.025 into 0.03.
    precision = {
        "quantity": 8,
        "average_nav": 6,
        "current_nav": 6,
    }.get(field_name, 2)

    return round(number, precision)


def normalize_currency(value):

    if not isinstance(value, str):
        return None

    currency = value.strip().upper()

    if currency in ALLOWED_CURRENCIES:
        return currency

    return None


# ==================================================
# NORMALIZE HOLDING
# ==================================================

def normalize_holding(holding):

    name = holding.get("name")

    if not isinstance(name, str) or not name.strip():
        raise ValueError("Invalid holding name.")

    name = name.strip()

    asset_class = holding.get("asset_class")

    if isinstance(asset_class, str):
        asset_class = asset_class.strip().title()

    if asset_class not in ALLOWED_ASSET_CLASSES:
        asset_class = "Unclassified"

    page = holding.get("page")

    if (
        isinstance(page, bool)
        or not isinstance(page, int)
        or page < 1
    ):
        raise ValueError(
            f"Invalid page number for {name}: {page}"
        )

    normalized = {
        "name": name,
        "asset_class": asset_class,
        "sub_category": holding.get("sub_category"),
        "isin": holding.get("isin"),
        "folio_number": holding.get("folio_number"),

        "quantity": validate_number(
            holding.get("quantity"),
            "quantity",
            name,
        ),

        "invested_value": validate_number(
            holding.get("invested_value"),
            "invested_value",
            name,
        ),

        "current_value": validate_number(
            holding.get("current_value"),
            "current_value",
            name,
        ),

        "profit_loss": validate_number(
            holding.get("profit_loss"),
            "profit_loss",
            name,
        ),

        "profit_loss_percentage": validate_number(
            holding.get("profit_loss_percentage"),
            "profit_loss_percentage",
            name,
        ),

        "source": holding.get("source"),

        "average_nav": validate_number(
            holding.get("average_nav"),
            "average_nav",
            name,
        ),

        "current_nav": validate_number(
            holding.get("current_nav"),
            "current_nav",
            name,
        ),

        "page": page,
    }

    for field in (
        "sub_category",
        "isin",
        "folio_number",
        "source",
    ):
        value = normalized[field]

        if isinstance(value, str):
            normalized[field] = value.strip() or None

    return normalized


# ==================================================
# GROQ REQUEST WITH RETRY
# ==================================================

def call_groq_with_retry(messages):

    last_error = None

    for attempt in range(MAX_RETRIES):

        try:
            print(
                f"Groq request attempt {attempt + 1}, "
                f"completion limit: {MAX_COMPLETION_TOKENS}",
                flush=True,
            )

            return client.chat.completions.create(
                model=MODEL_NAME,
                response_format={"type": "json_object"},
                messages=messages,
                temperature=0,
                max_completion_tokens=MAX_COMPLETION_TOKENS,
            )

        except RateLimitError as error:

            last_error = error

            wait_time = 15 * (attempt + 1)

            print(
                f"Groq rate limit reached. "
                f"Retrying in {wait_time} seconds.",
                flush=True,
            )

            if attempt < MAX_RETRIES - 1:
                time.sleep(wait_time)

        except APIStatusError as error:

            if error.status_code == 413:
                raise RequestTooLargeError(
                    "Groq request exceeded the allowed request size."
                ) from error

            if error.status_code == 429:

                last_error = error
                wait_time = 15 * (attempt + 1)

                print(
                    f"Groq temporarily unavailable. "
                    f"Retrying in {wait_time} seconds.",
                    flush=True,
                )

                if attempt < MAX_RETRIES - 1:
                    time.sleep(wait_time)

            else:
                raise

    raise RuntimeError(
        f"Groq request failed after {MAX_RETRIES} attempts: "
        f"{last_error}"
    )


# ==================================================
# EXTRACT ONE BATCH
# ==================================================

def extract_batch_from_groq(batch_pages):

    document_text = "\n\n".join(
        f"PAGE {page['page']}:\n{page['text']}"
        for page in batch_pages
    )

    prompt = f"""
Extract investment holdings from this financial statement.

Return ONLY valid JSON in this structure:

{{
    "currency": "USD",
    "report_date": "2021-03-31",
    "account_holder": "Example Account Holder",
    "reported_portfolio_value": 1656064.53,
    "holdings": [
        {{
            "name": "AMAZON.COM INC",
            "asset_class": "Equity",
            "sub_category": null,
            "isin": null,
            "folio_number": null,
            "quantity": 30,
            "invested_value": 101830.90,
            "current_value": 92822.40,
            "profit_loss": -9008.50,
            "profit_loss_percentage": null,
            "source": "J.P. Morgan Self-Directed Investing",
            "average_nav": null,
            "current_nav": null,
            "page": 6
        }}
    ]
}}

EXTRACTION RULES:

1. Extract only investments actually owned by the account holder.
2. Do not extract benchmarks, market statistics, allocation percentages,
    sector totals, transactions, fees or explanatory text as holdings.
3. Never invent, estimate or calculate missing values. Use null.
4. current_value means the holding's market value.
5. invested_value means cost basis or purchase value only when printed.
6. Extract quantity, prices and identifiers only when explicitly available.
7. Do not put ticker symbols in ISIN.
8. Preserve the actual page number shown in the document.
9. Do not extract underlying securities of funds as separate holdings.
10. Do not combine unrelated holdings or separate investment lots.
11. A name alone is not a holding; financial holding information is required.
12. Do not duplicate a fully reported holding on an adjacent continuation page.
13. Return numbers without currency symbols or commas.
14. Currency must be explicitly identified. Never assume INR.
15. report_date must be the current statement period's ending date
    or explicit current valuation date.
16. Never use previous statement dates, transaction dates, purchase dates,
    trade dates, financial-year dates or upload dates.
17. For a period such as February 27 - March 31, 2021,
    use 2021-03-31.
18. reported_portfolio_value must be the explicitly printed current
    total account or portfolio value.
19. Do not use previous-period value, cash balance, equity total
    or year-to-date deposits as portfolio value.
20. If the current total portfolio value is not identifiable, use null.
21. Use YYYY-MM-DD for report_date.
22. Extract account_holder only when an explicit account holder, investor name,
    or account name is printed. Preserve the name exactly; otherwise use null.
23. Asset class must be one of:
    Equity, Debt, Hybrid, Liquid, Gold, Real Estate, Cash, Unclassified.
24. If asset class cannot be confidently determined, use null.
25. If no holdings appear on a page, return an empty holdings array.
26. Return no explanatory text outside JSON.

DOCUMENT:

{document_text}
"""

    messages = [
        {
            "role": "system",
            "content": (
                "You are a precise financial statement extraction engine. "
                "Never invent financial values, dates, currencies or holdings. "
                "Return valid JSON only."
            ),
        },
        {
            "role": "user",
            "content": prompt,
        },
    ]

    response = call_groq_with_retry(messages)

    choice = response.choices[0]

    print(
        "FINISH REASON:",
        choice.finish_reason,
        flush=True,
    )

    raw_response = choice.message.content

    if not raw_response:
        raise ValueError("Groq returned an empty response.")

    if choice.finish_reason == "length":
        raise TruncatedResponseError(
            "Groq response was truncated."
        )

    try:
        result = json.loads(raw_response)

    except json.JSONDecodeError as error:

        print(
            "INVALID GROQ RESPONSE:",
            raw_response,
            flush=True,
        )

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

    account_holder = result.get("account_holder")
    if not isinstance(account_holder, str) or not account_holder.strip():
        account_holder = None
    else:
        account_holder = " ".join(account_holder.strip().split())

    currency = normalize_currency(
        result.get("currency")
    )

    reported_value = validate_number(
        result.get("reported_portfolio_value"),
        "reported_portfolio_value",
        "portfolio",
    )

    print(
        "EXTRACTED BATCH HOLDINGS:",
        len(result["holdings"]),
        flush=True,
    )

    print("EXTRACTED REPORT DATE:", report_date, flush=True)
    print("EXTRACTED CURRENCY:", currency, flush=True)
    print("REPORTED PORTFOLIO VALUE:", reported_value, flush=True)

    return {
        "holdings": result["holdings"],
        "report_date": report_date,
        "account_holder": account_holder,
        "currency": currency,
        "reported_portfolio_value": reported_value,
    }


# ==================================================
# METADATA MERGING
# ==================================================

def merge_metadata_value(left, right, field_name):

    if left is None:
        return right

    if right is None:
        return left

    if left == right:
        return left

    print(
        f"WARNING: Conflicting {field_name}: {left} vs {right}",
        flush=True,
    )

    return None


def merge_batch_results(left, right):

    return {
        "holdings": left["holdings"] + right["holdings"],

        "report_date": merge_metadata_value(
            left["report_date"],
            right["report_date"],
            "report dates",
        ),

        "currency": merge_metadata_value(
            left["currency"],
            right["currency"],
            "currencies",
        ),

        "reported_portfolio_value": merge_metadata_value(
            left["reported_portfolio_value"],
            right["reported_portfolio_value"],
            "portfolio values",
        ),

        "account_holder": merge_metadata_value(
            left.get("account_holder"),
            right.get("account_holder"),
            "account holders",
        ),
    }


# ==================================================
# SAFE PAGE SPLITTING
# ==================================================

def split_page_text(page):

    text = page["text"]

    lines = text.splitlines()

    if len(lines) >= MIN_LINES_TO_SPLIT:

        middle = len(lines) // 2
        overlap = min(LINE_OVERLAP, middle - 1)

        first_text = "\n".join(
            lines[:middle + overlap]
        )

        second_text = "\n".join(
            lines[middle - overlap:]
        )

        if (
            first_text
            and second_text
            and len(first_text) < len(text)
            and len(second_text) < len(text)
        ):
            return (
                {
                    "page": page["page"],
                    "text": first_text,
                },
                {
                    "page": page["page"],
                    "text": second_text,
                },
            )

    # Fall back to character-based splitting.
    if len(text) < MIN_CHARS_TO_SPLIT:
        raise ValueError(
            f"Cannot safely split page {page['page']} further."
        )

    middle = len(text) // 2

    first_text = text[:middle + CHAR_OVERLAP]
    second_text = text[middle - CHAR_OVERLAP:]

    if (
        len(first_text) >= len(text)
        or len(second_text) >= len(text)
    ):
        raise ValueError(
            f"Cannot safely split page {page['page']} further."
        )

    return (
        {
            "page": page["page"],
            "text": first_text,
        },
        {
            "page": page["page"],
            "text": second_text,
        },
    )


# ==================================================
# RECURSIVE EXTRACTION
# ==================================================

def extract_batch_with_splitting(batch_pages):

    if not batch_pages:
        return {
            "holdings": [],
            "report_date": None,
            "currency": None,
            "reported_portfolio_value": None,
            "account_holder": None,
        }

    try:

        return extract_batch_from_groq(batch_pages)

    except TruncatedResponseError:

        print(
            "Response truncated. Splitting batch...",
            flush=True,
        )

    except RequestTooLargeError:

        print(
            "Request too large. Splitting batch...",
            flush=True,
        )

    except BadRequestError as error:

        if not is_truncation_error(error):
            raise

        print(
            "Groq JSON generation failed. "
            "Splitting batch into smaller sections...",
            flush=True,
        )

    # Split multiple pages first.
    if len(batch_pages) > 1:

        middle = len(batch_pages) // 2

        left = extract_batch_with_splitting(
            batch_pages[:middle]
        )

        time.sleep(BATCH_DELAY)

        right = extract_batch_with_splitting(
            batch_pages[middle:]
        )

        return merge_batch_results(left, right)

    # A single page is still too large.
    page = batch_pages[0]

    first_half, second_half = split_page_text(page)

    left = extract_batch_with_splitting(
        [first_half]
    )

    time.sleep(BATCH_DELAY)

    right = extract_batch_with_splitting(
        [second_half]
    )

    return merge_batch_results(left, right)


# ==================================================
# CONTINUATION RECONCILIATION
# ==================================================

def reconcile_continuation_rows(holdings):

    result = []
    seen = set()

    for holding in holdings:

        identity = (
            holding.get("isin") or "",
            holding["name"].strip().upper(),
            holding.get("page"),
            holding.get("quantity"),
            holding.get("invested_value"),
            holding.get("current_value"),
            holding.get("profit_loss"),
            holding.get("average_nav"),
            holding.get("current_nav"),
        )

        # Remove only exact duplicates from overlapping
        # extraction of the same page.
        if identity in seen:
            print(
                "Duplicate overlapping record skipped:",
                holding["name"],
                "Page:",
                holding["page"],
                flush=True,
            )
            continue

        seen.add(identity)
        result.append(holding)

    return result


# ==================================================
# COMPLETE PDF EXTRACTION
# ==================================================

def extract_portfolio_from_pdf(file_path):

    pages = extract_text_from_pdf(file_path)

    if not pages:
        raise ValueError(
            "No readable text found in PDF."
        )

    # CAMS/KFintech CAS tables have stable, labelled columns. Parse them
    # deterministically before using an LLM, preserving exact ISINs,
    # fractional units, NAV and market values.
    cas_result = extract_cams_cas(pages)
    if cas_result is not None:
        normalized_holdings = [
            normalize_holding(holding)
            for holding in cas_result["holdings"]
        ]
        cas_result["holdings"] = normalized_holdings
        print("DETERMINISTIC CAS EXTRACTION:", len(normalized_holdings), flush=True)
        return cas_result

    batches = create_page_batches(
        pages,
        batch_size=BATCH_SIZE,
    )

    all_holdings = []
    report_dates = []
    currencies = []
    reported_values = []
    account_holders = []

    for index, batch in enumerate(batches):

        print(
            f"\nProcessing batch {index + 1}/{len(batches)}",
            flush=True,
        )

        try:

            batch_result = extract_batch_with_splitting(
                batch
            )

        except Exception as error:

            print(
                f"FAILED BATCH {index + 1}: {error}",
                flush=True,
            )

            raise

        all_holdings.extend(
            batch_result["holdings"]
        )

        if batch_result["report_date"]:
            report_dates.append(
                batch_result["report_date"]
            )

        if batch_result["currency"]:
            currencies.append(
                batch_result["currency"]
            )

        if batch_result.get("account_holder"):
            account_holders.append(batch_result["account_holder"])

        if batch_result["reported_portfolio_value"] is not None:
            reported_values.append(
                batch_result["reported_portfolio_value"]
            )

        if index < len(batches) - 1:
            time.sleep(BATCH_DELAY)

    if not all_holdings:
        raise ValueError(
            "No portfolio holdings found."
        )

    normalized_holdings = [
        normalize_holding(holding)
        for holding in all_holdings
    ]

    normalized_holdings = reconcile_continuation_rows(
        normalized_holdings
    )

    # Resolve metadata only when values agree.
    distinct_dates = set(report_dates)
    distinct_currencies = set(currencies)
    distinct_values = set(reported_values)

    report_date = (
        next(iter(distinct_dates))
        if len(distinct_dates) == 1
        else None
    )

    currency = (
        next(iter(distinct_currencies))
        if len(distinct_currencies) == 1
        else None
    )

    total_value = (
        next(iter(distinct_values))
        if len(distinct_values) == 1
        else None
    )

    distinct_holders = set(account_holders)
    account_holder = (
        next(iter(distinct_holders))
        if len(distinct_holders) == 1
        else None
    )

    if len(distinct_dates) > 1:
        print(
            "WARNING: Conflicting report dates:",
            distinct_dates,
            flush=True,
        )

    if len(distinct_currencies) > 1:
        print(
            "WARNING: Conflicting currencies:",
            distinct_currencies,
            flush=True,
        )

    if len(distinct_values) > 1:
        print(
            "WARNING: Conflicting portfolio totals:",
            distinct_values,
            flush=True,
        )

    result = {
        "currency": currency,
        "total_value": total_value,
        "report_date": report_date,
        "account_holder": account_holder,
        "holdings": normalized_holdings,
    }

    # Final extraction logs.
    print("\nEXTRACTION COMPLETED", flush=True)

    print(
        "TOTAL HOLDINGS:",
        len(normalized_holdings),
        flush=True,
    )

    print(
        "PORTFOLIO VALUE:",
        total_value,
        flush=True,
    )

    print(
        "CURRENCY:",
        currency,
        flush=True,
    )

    print(
        "STATEMENT DATE:",
        report_date,
        flush=True,
    )

    print("\nEXTRACTED HOLDINGS:", flush=True)

    for holding in normalized_holdings:

        print(
            holding["page"],
            holding["name"],
            "Quantity:",
            holding["quantity"],
            "Current value:",
            holding["current_value"],
            flush=True,
        )

    return result


# ==================================================
# FASTAPI ENDPOINTS
# ==================================================

app = FastAPI()


@app.post("/analytics")
def analytics_endpoint():
    return {"status": "success", "message": "Analytics processed."}


@app.post("/risk")
def risk_endpoint():
    return {"status": "success", "message": "Risk processed."}


@app.delete("/documents/{document_id}")
def delete_document(document_id: str, client_id: str, stored_filename: str):
    file_path = BASE_DIR / "data" / "uploads" / client_id / stored_filename

    try:
        if file_path.exists():
            # Retry unlinking to avoid WinError 32 if background process has temporary lock
            for attempt in range(3):
                try:
                    file_path.unlink()
                    break
                except PermissionError:
                    if attempt == 2:
                        raise
                    time.sleep(0.5)

        print("FAISS index and documents saved successfully.", flush=True)
        return {
            "status": "success",
            "message": "Document deleted successfully.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 