import pandas as pd


def calculate_portfolio(df):
    required = [
        "Fund Name",
        "Invested Value",
        "Value as on 31/10/2026",
        "Unrealized P&L",
        "Category",
    ]

    missing = [col for col in required if col not in df.columns]

    if missing:
        raise ValueError(f"Missing columns: {missing}")

    df = df.copy()

    numeric_columns = [
        "Invested Value",
        "Value as on 31/10/2026",
        "Unrealized P&L",
    ]

    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["Fund Name"])

    return {
        "holding_count": len(df),
        "total_invested": round(df["Invested Value"].sum(), 2),
        "current_value": round(
            df["Value as on 31/10/2026"].sum(), 2
        ),
        "total_profit_loss": round(
            df["Unrealized P&L"].sum(), 2
        ),
        "asset_class_totals": (
            df.groupby("Category")["Invested Value"]
            .sum()
            .round(2)
            .to_dict()
        ),
        "largest_investment": (
            df.loc[df["Invested Value"].idxmax(), "Fund Name"]
        ),
    }