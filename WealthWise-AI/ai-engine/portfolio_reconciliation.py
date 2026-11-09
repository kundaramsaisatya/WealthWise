"""
Portfolio snapshot reconciliation for WealthWise AI.

Consolidates portfolio snapshots from multiple uploaded statements without
summing repeated copies of the same investment.

Expected document shape:
{
    "document_id": "...",
    "filename": "...",
    "report_date": "YYYY-MM-DD",
    "currency": "INR",
    "statement_type": "cas | mutual_fund | demat | transactions | None",
    "holdings": [{...}]
}

`statement_type` should be set at upload time from the document content.
The filename is only a fallback and is never trusted over an explicit type.
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from datetime import date
from typing import Any

# Documents dated within this many days BEFORE the selected valuation date are
# still treated as part of the snapshot (e.g. demat valued 30-Oct, CAS 31-Oct).
DATE_TOLERANCE_DAYS = 7
VALUE_TOLERANCE_PCT = 0.01   # units x NAV vs value
ABS_TOLERANCE = 1.0          # rupees

# Rows that are totals/summaries. Anchored or phrase-based so that real fund
# names such as "Total Return Fund" are never mistaken for a summary row.
SUMMARY_START = re.compile(r"^\s*(grand\s+|sub[\s-]*|portfolio\s+)?total\b", re.I)
SUMMARY_PHRASES = re.compile(
    r"\b(grand total|sub[\s-]?total|portfolio total|total investment|total value)\b", re.I
)
SUMMARY_WORD = re.compile(r"^\s*summary\b", re.I)
# AMC / fund-house labels. Only treated as summary rows when there is no ISIN.
AMC_LABEL = re.compile(r"\b(mutual fund|asset management|amc)\b", re.I)

TYPE_ALIASES = {
    "cas": "cas",
    "consolidated account statement": "cas",
    "mutual_fund": "mutual_fund",
    "mf": "mutual_fund",
    "mutual fund": "mutual_fund",
    "demat": "demat",
    "demat holding": "demat",
    "holding statement": "demat",
    "transaction": "transactions",
    "transactions": "transactions",
    "transaction statement": "transactions",
}


# ---------------------------------------------------------------- helpers
def _clean(value: Any) -> str:
    if value is None:
        return ""
    value = unicodedata.normalize("NFKC", str(value))
    return " ".join(value.strip().split())


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", _clean(value).casefold())


def _normalise_isin(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", _clean(value).upper())


def _normalise_folio(value: Any) -> str:
    return _norm(value)


def _date_obj(value: Any) -> date | None:
    text = _clean(value)
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


# ---------------------------------------------------------------- classification
def classify_statement_type(
    filename: str = "",
    extracted_text: str = "",
    explicit_type: str | None = None,
) -> str:
    """Return cas, mutual_fund, demat, transactions, or unknown.

    An explicit type always wins. Otherwise separators in the filename are
    normalised, and holdings-type documents take precedence over the word
    "transaction" (e.g. "Demat Holding and Transaction Statement" is a
    holdings document).
    """
    if explicit_type:
        alias = _clean(explicit_type).casefold()
        if alias in TYPE_ALIASES:
            return TYPE_ALIASES[alias]

    raw = f"{filename} {extracted_text[:12000]}".casefold()
    text = re.sub(r"[_\-./\\]+", " ", raw)
    text = " ".join(text.split())

    if "consolidated account statement" in text or re.search(r"\b(nsdl|cdsl)\s+cas\b", text) \
            or re.search(r"\bcas\b", text):
        return "cas"
    if any(t in text for t in ("demat", "holding statement", "beneficiary account", "dp id")):
        return "demat"
    if any(t in text for t in ("mutual fund", "folio number", "scheme name", "nav as on")) \
            or re.search(r"\bmf\b", text):
        return "mutual_fund"
    if any(t in text for t in (
        "transaction statement", "trade date", "buy/sell", "settlement", "transactions"
    )):
        return "transactions"
    return "unknown"


def _source_priority(statement_type: str) -> int:
    # Lower is more authoritative for a current snapshot.
    return {
        "cas": 0,
        "demat": 0,
        "mutual_fund": 1,
        "unknown": 2,
        "transactions": 9,
    }.get(statement_type, 2)


# ---------------------------------------------------------------- row checks
def _is_summary_row(holding: dict[str, Any]) -> bool:
    name = _clean(holding.get("name"))
    if not name:
        return True
    if SUMMARY_START.search(name) or SUMMARY_PHRASES.search(name) or SUMMARY_WORD.search(name):
        return True
    # Bare AMC / fund-house labels (no ISIN) are not positions.
    if not _normalise_isin(holding.get("isin")) and AMC_LABEL.search(name):
        return True
    return False


def _is_mutual_fund(holding: dict[str, Any]) -> bool:
    isin = _normalise_isin(holding.get("isin"))
    if isin.startswith("INF"):
        return True
    if isin.startswith("INE"):
        return False
    return bool(holding.get("folio_number") or holding.get("current_nav") is not None)


def _hard_flags(holding: dict[str, Any]) -> list[str]:
    """Flags that make a row unreliable as a source of truth."""
    flags = []
    qty, nav, value = (_num(holding.get(k)) for k in ("quantity", "current_nav", "current_value"))
    if qty is not None and nav is not None and value is not None:
        expected = qty * nav
        if abs(expected - value) > max(ABS_TOLERANCE, VALUE_TOLERANCE_PCT * abs(value)):
            flags.append("units_x_nav_mismatch")
    return flags


def _identity_key(holding: dict[str, Any]) -> tuple:
    isin = _normalise_isin(holding.get("isin"))
    folio = _normalise_folio(
        holding.get("folio_number")
        or holding.get("account_number")
        or holding.get("demat_account")
    )
    if isin:
        # ISIN alone is not unique for mutual funds: different folios are
        # separate investments and must never be collapsed.
        return ("isin", isin, folio)
    return ("name", _norm(holding.get("name")), folio)


# ---------------------------------------------------------------- main
def reconcile_portfolio_documents(
    documents: list[dict[str, Any]],
    *,
    target_report_date: str | None = None,
) -> dict[str, Any]:
    """
    Reconcile documents into one current snapshot.

    * CAS is authoritative for mutual funds, Demat for listed securities.
    * Individual MF statements are used where CAS has no matching position.
    * Transaction-only documents never contribute current holdings.
    * Documents dated up to DATE_TOLERANCE_DAYS before the selected date are
      included; anything else is reported in `unreconciled_documents`.
    """
    valid_docs = [d for d in documents if isinstance(d, dict)]
    dated = [(d, _date_obj(d.get("report_date"))) for d in valid_docs]
    known_dates = [dd for _, dd in dated if dd]

    selected = _date_obj(target_report_date) if target_report_date else None
    if selected is None and known_dates:
        selected = max(known_dates)

    warnings: list[str] = []
    excluded: list[dict[str, Any]] = []
    flagged: list[dict[str, Any]] = []
    unreconciled: list[dict[str, Any]] = []
    source_documents: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []

    selected_docs = []
    for doc, doc_date in dated:
        if selected is None:
            selected_docs.append((doc, doc_date))     # nothing is dated
            continue
        if doc_date is None:
            unreconciled.append({"document_id": doc.get("document_id"), "filename": doc.get("filename"),
                                 "report_date": None, "reason": "No report date."})
            continue
        gap = (selected - doc_date).days
        if 0 <= gap <= DATE_TOLERANCE_DAYS:
            selected_docs.append((doc, doc_date))
        else:
            unreconciled.append({"document_id": doc.get("document_id"), "filename": doc.get("filename"),
                                 "report_date": doc_date.isoformat(),
                                 "reason": f"Dated {abs(gap)} day(s) {'before' if gap > 0 else 'after'} the "
                                           f"snapshot date {selected.isoformat()}; outside the "
                                           f"{DATE_TOLERANCE_DAYS}-day tolerance."})

    if selected is None:
        warnings.append("No valuation date was available; undated records were reconciled together.")
    for item in unreconciled:
        warnings.append(f"{item['filename']} was not included in the snapshot: {item['reason']}")

    for doc, doc_date in selected_docs:
        statement_type = classify_statement_type(
            doc.get("filename", ""), doc.get("extracted_text", ""), doc.get("statement_type")
        )
        source_documents.append({
            "document_id": doc.get("document_id"),
            "filename": doc.get("filename"),
            "statement_type": statement_type,
            "report_date": doc.get("report_date"),
        })
        if statement_type == "unknown":
            warnings.append(
                f"{doc.get('filename')}: statement type could not be determined; "
                f"set statement_type at upload for reliable source priority."
            )

        for raw in doc.get("holdings") or []:
            if not isinstance(raw, dict):
                continue
            holding = dict(raw)
            holding.setdefault("document_id", doc.get("document_id"))
            holding.setdefault("filename", doc.get("filename"))
            holding.setdefault("report_date", doc.get("report_date"))
            holding["statement_type"] = statement_type
            holding["_date_ord"] = doc_date.toordinal() if doc_date else 0

            if statement_type == "transactions":
                excluded.append({"name": holding.get("name"), "document_id": doc.get("document_id"),
                                 "reason": "Transaction history is not a current holdings snapshot."})
                continue
            if _is_summary_row(holding):
                excluded.append({"name": holding.get("name"), "document_id": doc.get("document_id"),
                                 "reason": "Statement summary/AMC total is not an instrument-level holding."})
                continue
            holding["_hard_flags"] = _hard_flags(holding)
            candidates.append(holding)

    # ---- group by identity (ISIN + folio)
    grouped: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for holding in candidates:
        grouped[_identity_key(holding)].append(holding)

    # A row with an ISIN but no folio is merged into a foliod position only
    # when exactly one folio holds this ISIN AND the quantity or value agrees.
    # Otherwise it stays a separate position and is flagged for review, so two
    # genuinely different folios are never collapsed.
    def _same_position(a: dict[str, Any], b: dict[str, Any]) -> bool:
        qa, qb = _num(a.get("quantity")), _num(b.get("quantity"))
        va, vb = _num(a.get("current_value")), _num(b.get("current_value"))
        if qa is not None and qb is not None and abs(qa - qb) <= 0.001:
            return True
        return va is not None and vb is not None and abs(va - vb) <= 0.01

    folios_by_isin: dict[str, list[tuple]] = defaultdict(list)
    for key in grouped:
        if key[0] == "isin" and key[2]:
            folios_by_isin[key[1]].append(key)
    for key in list(grouped):
        if key[0] == "isin" and not key[2] and key in grouped:
            targets = folios_by_isin.get(key[1], [])
            remaining = []
            for row in grouped[key]:
                matches = [t for t in targets if any(_same_position(row, r) for r in grouped[t])]
                if len(matches) == 1:
                    grouped[matches[0]].append(row)
                else:
                    remaining.append(row)
            if remaining:
                grouped[key] = remaining
                if targets:
                    warnings.append(
                        f"{remaining[0].get('name')}: a record has no folio number and could not be "
                        f"matched safely to a folio; it was kept as a separate position and needs review."
                    )
            else:
                del grouped[key]

    reconciled: list[dict[str, Any]] = []
    duplicate_groups = []
    valuation_differences = []

    for key, rows in grouped.items():
        rows.sort(key=lambda h: (_source_priority(h["statement_type"]), -h["_date_ord"]))
        usable = [r for r in rows if not r["_hard_flags"]] or rows
        preferred = "cas" if _is_mutual_fund(usable[0]) else "demat"
        preferred_rows = [r for r in usable if r["statement_type"] == preferred]
        chosen = dict((preferred_rows or usable)[0])

        flags = list(chosen["_hard_flags"])
        invested, current = _num(chosen.get("invested_value")), _num(chosen.get("current_value"))
        if invested is not None and current is not None:
            pl = round(current - invested, 2)
            old_pl = _num(chosen.get("profit_loss"))
            if old_pl is not None and abs(old_pl - pl) > ABS_TOLERANCE:
                flags.append("profit_loss_recomputed")
            chosen["profit_loss"] = pl
            chosen["profit_loss_percentage"] = round(pl / invested * 100, 2) if invested else None

        if chosen["_hard_flags"]:
            flagged.append({"name": chosen.get("name"), "document_id": chosen.get("document_id"),
                            "flags": chosen["_hard_flags"]})
            warnings.append(f"{chosen.get('name')}: units x NAV does not match the reported value; verify against the source.")

        chosen["quality_flags"] = flags
        chosen["reconciliation_key"] = "|".join(str(p) for p in key)
        chosen["source_documents"] = sorted({_clean(r.get("document_id")) for r in rows if r.get("document_id")})
        for helper in ("_date_ord", "_hard_flags"):
            chosen.pop(helper, None)
        reconciled.append(chosen)

        if len(rows) > 1:
            duplicate_groups.append({
                "identity": list(key),
                "selected_document_id": chosen.get("document_id"),
                "source_document_ids": chosen["source_documents"],
                "record_count": len(rows),
            })
            values = [_num(r.get("current_value")) for r in rows if _num(r.get("current_value")) is not None]
            quantities = [_num(r.get("quantity")) for r in rows if _num(r.get("quantity")) is not None]
            value_diff = len(values) > 1 and max(values) - min(values) > 0.01
            qty_diff = len(quantities) > 1 and max(quantities) - min(quantities) > 0.001
            if value_diff or qty_diff:
                valuation_differences.append({
                    "name": chosen.get("name"),
                    "values": values,
                    "quantities": quantities,
                    "selected_value": chosen.get("current_value"),
                    "selected_source": chosen.get("statement_type"),
                })

    if valuation_differences:
        warnings.append(f"{len(valuation_differences)} repeated positions have differing reported valuations.")

    with_value = [h for h in reconciled if _num(h.get("current_value")) is not None]
    with_cost = [h for h in with_value if _num(h.get("invested_value")) is not None]
    total_value = round(sum(float(h["current_value"]) for h in with_value), 2)
    total_invested = round(sum(float(h["invested_value"]) for h in with_cost), 2)
    comparable_value = round(sum(float(h["current_value"]) for h in with_cost), 2)
    missing_cost = len(reconciled) - len(with_cost)
    if missing_cost:
        warnings.append(f"{missing_cost} holdings have no cost basis; total P/L covers only holdings with cost.")

    return {
        "report_date": selected.isoformat() if selected else None,
        "holdings": reconciled,
        "holding_count": len(reconciled),
        "total_current_value": total_value,
        "total_invested_value": total_invested,
        "comparable_current_value": comparable_value,   # value of holdings that have a cost basis
        "total_profit_loss": round(comparable_value - total_invested, 2),
        "missing_cost_count": missing_cost,
        "duplicate_groups": duplicate_groups,
        "valuation_differences": valuation_differences,
        "excluded_records": excluded,
        "flagged_records": flagged,
        "unreconciled_documents": unreconciled,
        "documents": source_documents,
        "warnings": warnings,
    }