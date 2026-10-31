
from portfolio_analytics import calculate_portfolio_metrics

result = calculate_portfolio_metrics()

print("\nWEALTHWISE AI - PORTFOLIO ANALYSIS")
print("=" * 45)

print("Total Portfolio:", result["total_value"])

print("\nASSET ALLOCATION")

for item in result["asset_allocation"]:

    print(
        item["asset_class"],
        ":", item["percentage"], "%"
    )

print("\nLARGEST HOLDING")

print(result["largest_holding"])

print("\nCONCENTRATION")

print(result["concentration"])

print("\nLIQUIDITY")

print(result["liquidity"])

print("\nRISK FLAGS")

for flag in result["risk_flags"]:
    print(flag)
