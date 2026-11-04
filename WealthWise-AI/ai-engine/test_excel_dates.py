
from excel_extractor import normalize_report_date

test_dates = [
    "2026-03-31",
    "31-03-2026",
    "31/03/2026",
    "31-Mar-2026",
    "31 Mar 2026",
    "31-Mar-26"
]

for value in test_dates:
    print(value, "=>", normalize_report_date(value))
