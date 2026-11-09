"""Helpers for preparing chat portfolio calculations safely."""


def build_chat_portfolio(client_id, holdings, consolidation):
    """Return calculation input only when the snapshot currency is verified."""
    if not isinstance(holdings, list) or not holdings:
        return None

    if not isinstance(consolidation, dict):
        return None

    currency = consolidation.get("currency")
    if not isinstance(currency, str) or not currency.strip():
        return None

    return {
        "client_id": client_id,
        "currency": currency.strip().upper(),
        "report_date": consolidation.get("report_date"),
        "holdings": holdings,
    }
