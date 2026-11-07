import re
import math
from datetime import date, datetime
import pandas as pd


# --------------------------------------------------
# COLUMN ALIASES
# --------------------------------------------------
# Aliases are listed in priority order. When two columns in a sheet
# map to the same field (for example "Security" and "Symbol"), the
# column whose alias appears earliest in the list wins.

COLUMN_ALIASES = {
    "name": [
        "fund name", "scheme name", "scheme",
        "security name", "security",
        "scrip name", "stock name", "mutual fund",
        "instrument", "name", "symbol"
    ],

    "symbol": ["symbol", "ticker"],

    "isin": ["isin", "isin code"],

    "quantity": [
        "closing units", "total qty", "quantity",
        "qty", "units", "unit balance"
    ],

    "invested_value": [
        "invested value", "investment value", "buy value",
        "cost value", "cost of acquisition",
        "purchase value", "invested amount"
    ],

    "current_value": [
        "market value", "current value", "valuation",
        "present value", "market amount", "value as on",
        "value as of"
    ],

    "profit_loss": [
        "p&l", "pnl", "gain/loss", "profit/loss",
        "unrealised p&l", "unrealized p&l",
        "unrealised gain/loss", "unrealized gain/loss",
        "overall gain/loss"
    ],

    "profit_loss_percentage": [
        "unrealized p&l %", "unrealised p&l %",
        "profit/loss %", "gain/loss %",
        "overall gain/loss %", "return", "returns"
    ],

    "asset_class": [
        "asset class", "category", "instrument type"
    ],

    "sub_category": [
        "sub category", "subcategory"
    ],

    "folio_number": [
        "folio no", "folio number", "folio"
    ],

    "source": [
        "source", "broker", "fund house", "amc"
    ],

    "average_nav": [
        "average nav", "purchase nav", "average cost nav",
        "avg cost", "average cost"
    ],

    "current_nav": [
        "nav as on", "current nav", "latest nav",
        "closing price"
    ]
}


# --------------------------------------------------
# COLUMN NORMALIZATION
# --------------------------------------------------

# Currency tokens such as "(INR)" in "Cost Value (INR)" are ignored.
CURRENCY_TOKENS = {"inr", "rs"}


def normalize_column(column):

    column = str(column).strip().lower()

    column = re.sub(
        r"[^a-z0-9]+",
        " ",
        column
    )

    tokens = [
        token for token in column.split()
        if token not in CURRENCY_TOKENS
    ]

    return " ".join(tokens)


ALIAS_ORDER = {
    field: [normalize_column(alias) for alias in aliases]
    for field, aliases in COLUMN_ALIASES.items()
}

NORMALIZED_ALIASES = {
    field: set(ordered)
    for field, ordered in ALIAS_ORDER.items()
}


# --------------------------------------------------
# STATEMENT DATE EXTRACTION
# --------------------------------------------------


DATE_LABELS = [
    "statement date",
    "valuation date",
    "portfolio date",
    "portfolio as of",
    "portfolio as on",
    "valued as of",
    "valued as on",
    "market value as of",
    "market value as on",
    "as of date",
    "as on date",
    "as of",
    "as on",
    "report date",
    "reporting date",
    "date of statement"
]


def normalize_report_date(value):

    if value is None:
        return None

    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()

    if isinstance(value, datetime):
        return value.date().isoformat()

    if isinstance(value, date):
        return value.isoformat()

    # Handle Excel serial date values.
    if isinstance(value, (int, float)) and not isinstance(value, bool):

        if not math.isfinite(float(value)):
            return None

        if 20000 <= value <= 80000:
            try:
                converted = pd.to_datetime(
                    value,
                    unit="D",
                    origin="1899-12-30"
                )
                return converted.date().isoformat()
            except (ValueError, OverflowError):
                return None

        return None

    if not isinstance(value, str):
        return None

    value = value.strip()

    if not value:
        return None

    # Standard ISO format.
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        pass

    # Numeric date formats.
    numeric_formats = [
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d.%m.%Y",
        "%Y/%m/%d",
        "%d-%m-%y",
        "%d/%m/%y"
    ]

    for pattern in numeric_formats:
        try:
            return datetime.strptime(
                value, pattern
            ).date().isoformat()
        except ValueError:
            continue

    # Month-name formats.
    month_formats = [
        "%d-%b-%Y",
        "%d %b %Y",
        "%d-%B-%Y",
        "%d %B %Y",
        "%d-%b-%y",
        "%d %b %y",
        "%d/%b/%Y"
    ]

    for pattern in month_formats:
        try:
            return datetime.strptime(
                value, pattern
            ).date().isoformat()
        except ValueError:
            continue

    return None


def extract_date_from_text(value):

    if not isinstance(value, str):
        return None

    text = value.strip()

    if not text:
        return None

    normalized = normalize_column(text)

    if not any(
        label in normalized
        for label in DATE_LABELS
    ):
        return None

    patterns = [
        r"\b\d{4}-\d{2}-\d{2}\b",
        r"\b\d{2}[-/.]\d{2}[-/.]\d{2,4}\b",
        r"\b\d{4}/\d{2}/\d{2}\b",
        r"\b\d{1,2}[-/\s][A-Za-z]{3,9}[-/\s]\d{2,4}\b"
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            result = normalize_report_date(
                match.group()
            )

            if result:
                return result

    return None


def extract_sheet_report_date(df):

    candidates = []

    # Inspect the first 30 rows for statement metadata.
    for row_index in range(min(len(df), 30)):

        row = df.iloc[row_index].tolist()

        for column_index, value in enumerate(row):

            if pd.isna(value):
                continue

            # Date and label in the same cell.
            embedded_date = extract_date_from_text(
                str(value)
            )

            if embedded_date:
                candidates.append(embedded_date)
                continue

            # Date label in one cell, date in the next.
            normalized = normalize_column(value)

            if any(
                label in normalized
                for label in DATE_LABELS
            ):

                if column_index + 1 < len(row):

                    adjacent_date = normalize_report_date(
                        row[column_index + 1]
                    )

                    if adjacent_date:
                        candidates.append(adjacent_date)

    unique_dates = set(candidates)

    # Never guess when multiple different dates exist.
    if len(unique_dates) == 1:
        return unique_dates.pop()

    return None


# --------------------------------------------------
# MAP EXCEL COLUMNS
# --------------------------------------------------

def identify_column(column):

    normalized = normalize_column(column)

    if "%" in str(column) or "percent" in normalized:

        if any(
            term in normalized
            for term in ["p l", "profit loss", "gain loss"]
        ):
            return "profit_loss_percentage"

    for field, aliases in NORMALIZED_ALIASES.items():

        if normalized in aliases:
            return field

    if normalized.startswith("value as on"):
        return "current_value"

    if normalized.startswith("value as of"):
        return "current_value"

    # "NAV as on 31-Oct-2026", "NAV 31-Oct-2026"
    if normalized.startswith("nav "):
        return "current_nav"

    return None


def map_columns(columns):

    mapped = {}

    for column in columns:

        field = identify_column(column)

        if field:
            mapped[column] = field

    return mapped


def alias_rank(field, column):
    """Lower rank = higher priority alias."""

    ordered = ALIAS_ORDER.get(field, [])
    normalized = normalize_column(column)

    if normalized in ordered:
        return ordered.index(normalized)

    return len(ordered)


def choose_unique_mapping(column_mapping):
    """
    One column per field. If several columns map to the same field,
    the highest-priority alias wins. A losing "Symbol" column is kept
    as the separate 'symbol' field instead of being discarded.
    """

    best = {}

    for column, field in column_mapping.items():

        rank = alias_rank(field, column)

        if field not in best or rank < best[field][0]:
            best[field] = (rank, column)

    unique_mapping = {
        column: field
        for field, (_, column) in best.items()
    }

    for column, field in column_mapping.items():

        if (
            field == "name"
            and column not in unique_mapping
            and normalize_column(column) == "symbol"
            and "symbol" not in unique_mapping.values()
        ):
            unique_mapping[column] = "symbol"

    return unique_mapping


# --------------------------------------------------
# HEADER DETECTION
# --------------------------------------------------

def detect_header_row(df):

    best_index = None
    best_score = 0

    for index, row in df.iterrows():

        values = [
            value
            for value in row.tolist()
            if pd.notna(value)
        ]

        if not values:
            continue

        mapped_fields = set()

        for value in values:

            field = identify_column(value)

            if field:
                mapped_fields.add(field)

        has_name = "name" in mapped_fields

        financial_fields = {
            "isin",
            "quantity",
            "invested_value",
            "current_value",
            "folio_number"
        }

        has_financial_field = bool(
            mapped_fields.intersection(financial_fields)
        )

        if not has_name or not has_financial_field:
            continue

        score = len(mapped_fields)

        if score > best_score:
            best_score = score
            best_index = index

    return best_index


# --------------------------------------------------
# NUMERIC VALUE NORMALIZATION
# --------------------------------------------------

def parse_numeric(value):

    if pd.isna(value):
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):

        if not math.isfinite(float(value)):
            return None

        return float(value)

    text = str(value).strip()

    if not text or text.lower() in {
        "nan", "none", "null", "na", "n/a", "-"
    }:
        return None

    negative = (
        text.startswith("(")
        and text.endswith(")")
    )

    text = text.replace(",", "")
    text = text.replace("₹", "")
    text = text.replace("Rs.", "")
    text = text.replace("Rs", "")
    text = text.replace("INR", "")
    text = text.replace("%", "")
    text = text.replace("(", "")
    text = text.replace(")", "")
    text = text.strip()

    try:

        number = float(text)

        if not math.isfinite(number):
            return None

        if negative:
            number = -abs(number)

        return number

    except (ValueError, TypeError):
        return None


# --------------------------------------------------
# CLEAN TEXT
# --------------------------------------------------

def clean_text(value):

    if pd.isna(value):
        return None

    text = str(value).strip()

    if not text or text.lower() in {
        "nan", "none", "null"
    }:
        return None

    return text


# --------------------------------------------------
# IDENTIFY TOTAL ROWS
# --------------------------------------------------

def is_total_row(name):

    if not isinstance(name, str):
        return False

    normalized = normalize_column(name)

    return normalized in {
        "total",
        "grand total",
        "subtotal",
        "sub total",
        "portfolio total",
        "total investment",
        "total value"
    }


# --------------------------------------------------
# CATEGORY AND PROFIT / LOSS CLEANUP
# --------------------------------------------------

def split_category(asset_class, sub_category, isin):
    """
    Turn "Equity - Large Cap" into asset class "Equity" and
    sub-category "Large Cap". Listed shares (ISIN starting with INE)
    with no category are treated as Equity.
    """

    if asset_class:

        parts = re.split(r"\s+[-–—]\s+", asset_class, maxsplit=1)

        if len(parts) == 2:
            asset_class = parts[0].strip()

            if not sub_category:
                sub_category = parts[1].strip()

    elif isin and str(isin).upper().startswith("INE"):
        asset_class = "Equity"

        if not sub_category:
            sub_category = "Listed Shares"

    return asset_class, sub_category


def reconcile_profit_loss(record):
    """
    Profit/loss and its percentage are recalculated from the invested
    and current values, so a statement that stores returns as fractions
    (0.1418 instead of 14.18) or labels them oddly cannot corrupt them.
    """

    invested = record["invested_value"]
    current = record["current_value"]

    if invested is None or current is None:
        return

    profit_loss = round(current - invested, 2)

    record["profit_loss"] = profit_loss

    record["profit_loss_percentage"] = (
        round(profit_loss / invested * 100, 2)
        if invested > 0 else None
    )


# --------------------------------------------------
# EXTRACT ONE SHEET
# --------------------------------------------------

def extract_sheet(workbook, sheet_name):

    df = pd.read_excel(
        workbook,
        sheet_name=sheet_name,
        header=None,
        dtype=object
    )

    df = df.dropna(
        how="all"
    ).dropna(
        axis=1,
        how="all"
    )

    if df.empty:

        return {
            "status": "empty_sheet",
            "report_date": None,
            "column_mapping": {},
            "holdings": []
        }

    report_date = extract_sheet_report_date(df)

    header_index = detect_header_row(df)

    if header_index is None:

        return {
            "status": "headers_not_detected",
            "report_date": report_date,
            "column_mapping": {},
            "holdings": []
        }

    headers = df.loc[header_index].tolist()

    data = df.loc[header_index + 1:].copy()

    data["_source_row"] = data.index + 1

    data.columns = [
        clean_text(header) or f"Unnamed_{index}"
        for index, header in enumerate(headers)
    ] + ["_source_row"]

    data = data.reset_index(drop=True)

    column_mapping = map_columns([
        column
        for column in data.columns
        if column != "_source_row"
    ])

    unique_mapping = choose_unique_mapping(column_mapping)

    data = data.rename(columns=unique_mapping)

    if "name" not in data.columns:

        return {
            "status": "name_column_missing",
            "report_date": report_date,
            "column_mapping": unique_mapping,
            "holdings": []
        }

    # Only sheets that report a market/current value are holdings.
    # Trades, transactions, realised P&L, dividends and corporate
    # actions have no current value and must never be counted as
    # holdings.
    if "current_value" not in data.columns:

        return {
            "status": "not_a_holdings_sheet",
            "report_date": report_date,
            "column_mapping": unique_mapping,
            "holdings": []
        }

    records = []

    for _, row in data.iterrows():

        name = clean_text(row.get("name"))

        if not name:
            continue

        if is_total_row(name):
            continue

        isin = clean_text(row.get("isin"))

        asset_class, sub_category = split_category(
            clean_text(row.get("asset_class")),
            clean_text(row.get("sub_category")),
            isin
        )

        record = {
            "name": name,

            "symbol": clean_text(
                row.get("symbol")
            ),

            "asset_class": asset_class,

            "sub_category": sub_category,

            "isin": isin,

            "quantity": parse_numeric(
                row.get("quantity")
            ),

            "invested_value": parse_numeric(
                row.get("invested_value")
            ),

            "current_value": parse_numeric(
                row.get("current_value")
            ),

            "profit_loss": parse_numeric(
                row.get("profit_loss")
            ),

            "profit_loss_percentage": parse_numeric(
                row.get("profit_loss_percentage")
            ),

            "folio_number": clean_text(
                row.get("folio_number")
            ),

            "source": clean_text(
                row.get("source")
            ),

            "average_nav": parse_numeric(
                row.get("average_nav")
            ),

            "current_nav": parse_numeric(
                row.get("current_nav")
            ),

            "row_number": int(row.get("_source_row"))
        }

        has_investment_data = any(
            record[field] is not None
            for field in [
                "isin",
                "quantity",
                "invested_value",
                "current_value",
                "folio_number"
            ]
        )

        if not has_investment_data:
            continue

        reconcile_profit_loss(record)

        # Cost values are on an average-cost basis, so cost / units is the
        # average cost per unit when the statement does not print it.
        if (
            record["average_nav"] is None
            and record["invested_value"]
            and record["quantity"]
        ):
            record["average_nav"] = record["invested_value"] / record["quantity"]

        if record["average_nav"] is not None:
            record["average_nav"] = round(record["average_nav"], 4)

        records.append(record)

    return {
        "status": "processed",
        "report_date": report_date,
        "column_mapping": unique_mapping,
        "holdings": records
    }


# --------------------------------------------------
# WORKBOOK ACCOUNT HOLDER METADATA
# --------------------------------------------------

def extract_workbook_account_holder(workbook):
    """
    Read an explicitly labelled account-holder field from statement
    metadata sheets. Never infer a person from an investment row.
    """
    labels = {
        "account holder",
        "account holders name",
        "investor name",
        "name of investor",
        "primary holder",
        "first holder",
    }
    candidates = set()

    for sheet_name in workbook.sheet_names:
        try:
            metadata = pd.read_excel(
                workbook,
                sheet_name=sheet_name,
                header=None,
                nrows=30,
                dtype=object,
            )
        except Exception:
            continue

        for _, row in metadata.iterrows():
            values = row.tolist()
            for index, value in enumerate(values):
                label = normalize_column(value) if pd.notna(value) else ""
                if label not in labels or index + 1 >= len(values):
                    continue
                holder = clean_text(values[index + 1])
                if holder:
                    candidates.add(holder)

    # Conflicting names across metadata sheets are not guessed.
    return next(iter(candidates)) if len(candidates) == 1 else None


def extract_folio_metadata(workbook):
    """Extract explicitly reported nominee and KYC status by folio."""
    results = []
    for sheet_name in workbook.sheet_names:
        try:
            df = pd.read_excel(
                workbook, sheet_name=sheet_name, header=None,
                nrows=40, dtype=object
            )
        except Exception:
            continue

        header_index = None
        columns = {}
        for row_index, row in df.iterrows():
            normalized = [normalize_column(v) if pd.notna(v) else "" for v in row.tolist()]
            folio_col = next((i for i, v in enumerate(normalized) if v in {"folio no", "folio number", "folio"}), None)
            nominee_col = next((i for i, v in enumerate(normalized) if v == "nominee"), None)
            kyc_col = next((i for i, v in enumerate(normalized) if v in {"kyc pan status", "kyc status", "pan status"}), None)
            amc_col = next((i for i, v in enumerate(normalized) if v in {"amc", "fund house"}), None)
            if folio_col is not None and nominee_col is not None and kyc_col is not None:
                header_index = row_index
                columns = {"folio": folio_col, "nominee": nominee_col, "kyc": kyc_col, "amc": amc_col}
                break

        if header_index is None:
            continue

        for _, row in df.iloc[header_index + 1:].iterrows():
            values = row.tolist()
            folio_index = columns["folio"]
            if folio_index >= len(values):
                continue
            folio = clean_text(values[folio_index])
            if not folio:
                continue
            nominee = clean_text(values[columns["nominee"]]) if columns["nominee"] < len(values) else None
            kyc = clean_text(values[columns["kyc"]]) if columns["kyc"] < len(values) else None
            amc_index = columns["amc"]
            amc = clean_text(values[amc_index]) if amc_index is not None and amc_index < len(values) else None
            results.append({
                "folio_number": folio,
                "amc": amc,
                "nominee_status": nominee,
                "kyc_status": kyc,
                "source_sheet": sheet_name,
            })

    # Preserve the most specific unique record per folio; do not guess
    # when two source rows disagree.
    grouped = {}
    for item in results:
        grouped.setdefault(item["folio_number"], []).append(item)

    output = []
    for folio, records in grouped.items():
        signatures = {
            (r["nominee_status"], r["kyc_status"], r["amc"])
            for r in records
        }
        if len(signatures) == 1:
            output.append(records[0])
        else:
            output.append({
                "folio_number": folio,
                "amc": None,
                "nominee_status": None,
                "kyc_status": None,
                "source_sheet": records[0]["source_sheet"],
                "verification_note": "Conflicting folio metadata across source rows; manual review required.",
            })
    return output


# --------------------------------------------------
# MAIN EXCEL EXTRACTION FUNCTION
# --------------------------------------------------

def extract_excel(file_path):

    extracted_data = {}
    report_dates = []

    with pd.ExcelFile(file_path) as workbook:

        account_holder = extract_workbook_account_holder(workbook)
        folio_metadata = extract_folio_metadata(workbook)

        for sheet_name in workbook.sheet_names:

            try:
                sheet_result = extract_sheet(
                    workbook,
                    sheet_name
                )

                extracted_data[sheet_name] = sheet_result

                if sheet_result.get("report_date"):
                    report_dates.append(
                        sheet_result["report_date"]
                    )

            except Exception as error:

                extracted_data[sheet_name] = {
                    "status": "extraction_error",
                    "report_date": None,
                    "error": str(error),
                    "column_mapping": {},
                    "holdings": []
                }

    unique_dates = set(report_dates)

    report_date = (
        next(iter(unique_dates))
        if len(unique_dates) == 1
        else None
    )

    return {
        "report_date": report_date,
        "account_holder": account_holder,
        "folio_metadata": folio_metadata,
        "sheets": extracted_data
    }