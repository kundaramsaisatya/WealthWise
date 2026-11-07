import re
from datetime import datetime


NUMBER = r"(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d+)?"
ROW_RE = re.compile(
    rf"^\s*(?P<folio>\d{{6,}})\s+(?P<isin>[A-Z0-9]{{12}})\s+"
    rf"(?P<name>.+?)\s+(?P<cost>{NUMBER})\s+"
    rf"(?P<quantity>{NUMBER})\s+(?P<nav_date>\d{{2}}-[A-Za-z]{{3}}-\d{{4}})\s+"
    rf"(?P<nav>{NUMBER})\s+(?P<market>{NUMBER})\s+(?P<registrar>CAMS|KFINTECH)\s*$",
    re.IGNORECASE,
)


def _number(value):
    return float(value.replace(",", ""))


def extract_cams_cas(pages):
    """Deterministically parse text-based CAMS/KFintech Consolidated Account Summary rows."""
    # pypdf's default extraction can reorder table columns. Layout text keeps
    # each CAS row aligned so the labelled values remain associated correctly.
    def page_text(page):
        layout = page.get("layout_text") or ""
        # Some PDF layouts are incomplete. Use layout mode only when it
        # actually contains a recognizable CAS holding row.
        if any(ROW_RE.match(line) for line in layout.splitlines()):
            return layout
        return page.get("text", "")

    full_text = "\n".join(page_text(page) for page in pages)
    if not re.search(r"Consolidated Account Summary", full_text, re.IGNORECASE):
        return None

    holder = None
    # Use ordinary extracted text for identity. Layout mode can merge the
    # investor column with the explanatory right column into a long line.
    excluded_starters = {"the", "if", "this", "please", "email", "phone", "mobile"}
    for page in pages:
        for line in page.get("text", "").splitlines():
            candidate = " ".join(line.strip().split())
            if not candidate or len(candidate) > 80:
                continue
            # The document title is title-cased too, so exclude it explicitly
            # rather than treating it as the investor's name.
            if candidate.casefold() in {
                "consolidated account summary",
                "loads and fees",
            }:
                continue
            words = candidate.split()
            if not 2 <= len(words) <= 6:
                continue
            if words[0].casefold() in excluded_starters:
                continue
            if re.fullmatch(r"[A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*){1,5}", candidate):
                holder = candidate
                break
        if holder:
            break

    date_match = re.search(r"As on\s+(\d{1,2}-[A-Za-z]{3}-\d{4})", full_text, re.IGNORECASE)
    report_date = None
    if date_match:
        report_date = datetime.strptime(date_match.group(1), "%d-%b-%Y").date().isoformat()

    holdings = []
    for page in pages:
        lines = page_text(page).splitlines()
        for index, line in enumerate(lines):
            match = ROW_RE.match(line)
            if not match:
                continue
            values = match.groupdict()
            name = values["name"].strip()
            # CAS may wrap the scheme name onto the immediately following line.
            if index + 1 < len(lines):
                continuation = lines[index + 1].strip()
                if continuation and not re.match(r"^(?:Total|Loads and Fees|Page\s+\d+)", continuation, re.IGNORECASE):
                    if not re.match(r"^\d{6,}\s+", continuation):
                        name = f"{name} {continuation}".strip()
            holdings.append({
                "name": re.sub(r"^[A-Z0-9]+\s+-\s+", "", name).strip(),
                "asset_class": "Unclassified",
                "sub_category": None,
                "isin": values["isin"].upper(),
                "folio_number": values["folio"],
                "quantity": _number(values["quantity"]),
                "invested_value": round(_number(values["cost"]), 2),
                "current_value": round(_number(values["market"]), 2),
                "profit_loss": None,
                "profit_loss_percentage": None,
                "source": values["registrar"].upper(),
                "average_nav": None,
                "current_nav": _number(values["nav"]),
                "page": int(page.get("page") or 1),
            })

    if not holdings:
        return None

    # A CAS total row is not treated as another holding. Sum its parsed
    # instrument market values; do not fabricate missing instrument data.
    total_value = round(sum(item["current_value"] for item in holdings), 2)
    return {
        "currency": "INR",
        "total_value": total_value,
        "report_date": report_date,
        "account_holder": holder,
        "holdings": holdings,
    }
