from risk_engine import analyze_portfolio_risk
from risk_explainer import generate_risk_explanation

risk_data = analyze_portfolio_risk()

explanation = generate_risk_explanation(risk_data)

print("\nWEALTHWISE AI - AI RISK EXPLANATION")
print("=" * 45)
print(explanation)