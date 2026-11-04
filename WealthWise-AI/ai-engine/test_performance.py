
from performance_engine import calculate_portfolio_performance

snapshots = [
    {
        "report_date": "2025-01-01",
        "total_value": 100000
    },
    {
        "report_date": "2025-06-01",
        "total_value": 115000
    },
    {
        "report_date": "2026-01-01",
        "total_value": 130000
    }
]

result = calculate_portfolio_performance(snapshots)

print(result)
