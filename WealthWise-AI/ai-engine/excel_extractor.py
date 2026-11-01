
import re
import math
from datetime import date, datetime
import pandas as pd


# --------------------------------------------------
# COLUMN ALIASES
# --------------------------------------------------

COLUMN_ALIASES = {
    "name": [
        "name", "symbol", "scrip name", "stock name",
        "security name", "scheme name", "mutual fund",
        "instrument", "fund name"
    ],

    "isin": ["isin", "isin code"],

    "quantity": [
        "quantity", "qty", "units", "unit balance"
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
        "overall gain/loss"
    ],

    "profit_loss_percentage": [
        "unrealized p&l %", "unrealised p&l %",
        "profit/loss %", "gain/loss %",
        "overall gain/loss %"
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
        "source", "broker", "fund house"
    ],

    "average_nav": [
        "average nav", "purchase nav", "average cost nav"
    ],

    "current_nav": [
        "nav as on", "current nav", "latest nav"
    ]
}


# --------------------------------------------------
# COLUMN NORMALIZATION
# --------------------------------------------------

def normalize_column(column):

    column = str(column).strip().lower()

    column = re.sub(
        r"[^a-z0-9]+",
        " ",
        column
    )

    return " ".join(column.split())


NORMALIZED_ALIASES = {
    field: {
        normalize_column(alias)
        for alias in aliases
    }
    for field, aliases in COLUMN_ALIASES.items()
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

    if not isinstance(value, str):
        return None

    value = value.strip()

    if not value:
        return None

    # Accept unambiguous ISO dates.
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        pass

    # Accept DD-MM-YYYY and DD/MM/YYYY.
    for pattern in ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            continue

    # Accept YYYY/MM/DD.
    try:
        return datetime.strptime(value, "%Y/%m/%d").date().isoformat()
    except ValueError:
        return None


def extract_date_from_text(value):

    if not isinstance(value, str):
        return None

    text = value.strip()

    # Look for a date only when a recognized statement
    # date label appears in the same cell.
    normalized = normalize_column(text)

    if not any(label in normalized for label in DATE_LABELS):
        return None

    patterns = [
        r"\b\d{4}-\d{2}-\d{2}\b",
        r"\b\d{2}[-/.]\d{2}[-/.]\d{4}\b",
        r"\b\d{4}/\d{2}/\d{2}\b"
    ]

    for pattern in patterns:

        match = re.search(pattern, text)

        if match:
            result = normalize_report_date(match.group())

            if result:
                return result

    return None


def extract_sheet_report_date(df):

    candidates = []

    # Inspect the first 30 rows, where statement metadata
    # is normally located.
    for row_index in range(min(len(df), 30)):

        row = df.iloc[row_index].tolist()

        for column_index, value in enumerate(row):

            if pd.isna(value):
                continue

            # A labelled date may be inside one cell.
            embedded_date = extract_date_from_text(str(value))

            if embedded_date:
                candidates.append(embedded_date)
                continue

            # A recognized date label may have its date
            # in the next cell.
            normalized = normalize_column(value)

            if any(label in normalized for label in DATE_LABELS):

                if column_index + 1 < len(row):

                    adjacent_date = normalize_report_date(
                        row[column_index + 1]
                    )

                    if adjacent_date:
                        candidates.append(adjacent_date)

    unique_dates = set(candidates)

    # If multiple different statement dates are found,
    # do not guess which one represents the portfolio.
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

    if normalized.startswith("nav as on"):
        return "current_nav"

    return None


def map_columns(columns):

    mapped = {}

    for column in columns:

        field = identify_column(column)

        if field:
            mapped[column] = field

    return mapped


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
            "rows": df.fillna("").astype(str).to_dict(
                orient="records"
            ),
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

    unique_mapping = {}
    used_fields = set()

    for original_column, field in column_mapping.items():

        if field not in used_fields:

            unique_mapping[original_column] = field
            used_fields.add(field)

    data = data.rename(columns=unique_mapping)

    if "name" not in data.columns:

        return {
            "status": "name_column_missing",
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

        record = {
            "name": name,

            "asset_class": clean_text(
                row.get("asset_class")
            ),

            "sub_category": clean_text(
                row.get("sub_category")
            ),

            "isin": clean_text(
                row.get("isin")
            ),

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

        records.append(record)

    return {
        "status": "processed",
        "report_date": report_date,
        "column_mapping": unique_mapping,
        "holdings": records
    }


# --------------------------------------------------
# MAIN EXCEL EXTRACTION FUNCTION
# --------------------------------------------------

def extract_excel(file_path):

    workbook = pd.ExcelFile(file_path)

    extracted_data = {}
    report_dates = []

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
        unique_dates.pop()
        if len(unique_dates) == 1
        else None
    )

    return {
        "report_date": report_date,
        "sheets": extracted_data
    }
