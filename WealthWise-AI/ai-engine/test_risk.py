
from risk_engine import analyze_portfolio_risk


portfolio_data = {
    "client_id": "CLIENT-TEST",
    "currency": "INR",
    "holdings": [
        {
            "name": "Reliance Industries",
            "asset_class": "Equity",
            "sector": "Energy",
            "isin": "INE002A01018",
            "current_value": 60000,
            "invested_value": 50000,
            "report_date": "2026-10-01"
        },
        {
            "name": "HDFC Bank",
            "asset_class": "Equity",
            "sector": "Banking",
            "isin": "INE040A01034",
            "current_value": 20000,
            "invested_value": 18000,
            "report_date": "2026-10-01"
        },
        {
            "name": "Liquid Fund",
            "asset_class": "Cash / Liquid",
            "sector": "Unknown",
            "isin": "TEST123",
            "current_value": 20000,
            "invested_value": 19000,
            "report_date": "2026-10-01"
        }
    ]
}

result = analyze_portfolio_risk(portfolio_data)

print("\nPORTFOLIO RISK ANALYSIS")
print(result)
