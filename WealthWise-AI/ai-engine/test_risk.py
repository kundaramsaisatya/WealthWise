
from risk_engine import analyze_portfolio_risk

result = analyze_portfolio_risk()

print("\nWEALTHWISE AI - RISK ANALYSIS")
print("=" * 40)

print("Portfolio:", result["total_value"])
print("Largest holding:", result["largest_holding"])
print("Top 3 concentration:", result["top_three_concentration"], "%")
print("HHI:", result["hhi"])
print("Normalized HHI:", result["normalized_hhi"])
print("Liquidity:", result["liquidity_percentage"], "%")

print("\nRISK FLAGS")

if not result["risk_flags"]:
    print("No configured risk thresholds were breached.")

for flag in result["risk_flags"]:
    print(flag["type"], "-", flag["message"])

print("\n", result["interpretation"])
