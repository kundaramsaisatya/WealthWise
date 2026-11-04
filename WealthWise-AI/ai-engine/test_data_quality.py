
from data_quality import analyze_data_quality


portfolio = {
    "holdings": [
        {
            "name": "Reliance Industries",
            "isin": "INE002A01018",
            "asset_class": "Equity",
            "sector": "Energy",
            "invested_value": 50000,
            "current_value": 60000,
            "report_date": "2026-10-01"
        },
        {
            "name": "New Startup Fund",
            "isin": "NEW123",
            "asset_class": "Other",
            "invested_value": None,
            "current_value": 20000,
            "report_date": "2026-10-01"
        }
    ]
}

history_records = [
    {
        "isin": "INE002A01018",
        "date": "2025-01-01"
    },
    {
        "isin": "INE002A01018",
        "date": "2026-10-01"
    },
    {
        "isin": "NEW123",
        "date": "2026-10-01"
    }
]

result = analyze_data_quality(
    portfolio,
    history_records
)

print(result)
