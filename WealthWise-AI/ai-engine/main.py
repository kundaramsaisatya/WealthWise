import os
import json
import math
import re
import secrets
import shutil
import traceback
import uuid

from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import (
    FastAPI,
    UploadFile,
    File,
    Form,
    HTTPException,
    Header,
    Depends,
    Query,
)
from pydantic import BaseModel

from performance_engine import calculate_portfolio_performance
from portfolio_analytics import calculate_portfolio_metrics
from excel_extractor import extract_excel
from portfolio_extractor import extract_portfolio_from_pdf
from risk_engine import analyze_portfolio_risk
from risk_explainer import generate_risk_explanation
from document_processor import process_pdf
from vector_store import VectorStore
from rag import generate_answer, is_listing_question
from account_holder_selection import select_account_holder_documents


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

AI_SERVICE_SECRET = os.getenv("AI_SERVICE_SECRET")

if not AI_SERVICE_SECRET:
    raise RuntimeError("AI_SERVICE_SECRET is missing from environment.")

UPLOAD_DIR = BASE_DIR / "data" / "uploads"
VECTOR_DIR = BASE_DIR / "data" / "vector_data"
PORTFOLIO_DIR = BASE_DIR / "data" / "portfolios"

for directory in (UPLOAD_DIR, VECTOR_DIR, PORTFOLIO_DIR):
    directory.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="WealthWise AI",
    description="AI-powered Wealth Management Assistant",
    version="1.3.0",
)


# --------------------------------------------------
# AUTHENTICATION
# --------------------------------------------------

def verify_service_secret(x_service_secret: str = Header(...)):
    if not secrets.compare_digest(x_service_secret, AI_SERVICE_SECRET):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized service request.",
        )


# --------------------------------------------------
# CLIENT DATA / STORAGE HELPERS
# --------------------------------------------------

vector_stores = {}


def validate_client_id(client_id: str):
    if not re.fullmatch(r"CLIENT-[a-fA-F0-9-]{36}", client_id or ""):
        raise HTTPException(status_code=400, detail="Invalid client ID.")


def validate_document_id(document_id: str):
    if not re.fullmatch(r"[a-fA-F0-9]{24}", document_id or ""):
        raise HTTPException(status_code=400, detail="Invalid document ID.")


def get_client_vector_store(client_id: str):
    validate_client_id(client_id)

    if client_id not in vector_stores:
        store = VectorStore()
        client_folder = VECTOR_DIR / client_id

        index_file = client_folder / "index.faiss"
        documents_file = client_folder / "documents.json"

        if index_file.exists() and documents_file.exists():
            store.load(str(client_folder))

        vector_stores[client_id] = store

    return vector_stores[client_id]


def get_portfolio_client_folder(client_id: str) -> Path:
    validate_client_id(client_id)
    return PORTFOLIO_DIR / client_id


def get_portfolio_file(client_id: str, document_id: str) -> Path:
    validate_document_id(document_id)
    return get_portfolio_client_folder(client_id) / f"{document_id}.json"


def save_portfolio_data(client_id: str, document_id: str, data: dict):
    """Atomically save structured holdings for one uploaded document."""
    client_folder = get_portfolio_client_folder(client_id)
    client_folder.mkdir(parents=True, exist_ok=True)

    file_path = get_portfolio_file(client_id, document_id)
    temporary_path = file_path.with_suffix(".json.tmp")

    # saved_at lets us pick the newest upload when two reports share a date.
    data = {
        **data,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }

    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False, allow_nan=False)

    temporary_path.replace(file_path)

    print(f"PORTFOLIO SAVED: {file_path}")
    print(f"HOLDINGS SAVED: {len(data.get('holdings', []))}")


def load_all_portfolio_holdings(client_id: str):
    """Load structured holdings from every saved Excel document for this client."""
    client_folder = get_portfolio_client_folder(client_id)

    print(f"PORTFOLIO FOLDER EXISTS: {client_folder.exists()}")

    if not client_folder.exists():
        return [], []

    all_holdings = []
    documents = []

    for file_path in sorted(client_folder.glob("*.json")):
        try:
            with file_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(
                f"Could not read structured portfolio file "
                f"{file_path.name}: {error}"
            ) from error

        holdings = data.get("holdings", [])

        if not isinstance(holdings, list):
            raise RuntimeError(
                f"Invalid holdings data in {file_path.name}."
            )

        # Every holding carries its document id and report date, so
        # downstream data-quality checks never lose them.
        for holding in holdings:
            if isinstance(holding, dict):
                holding.setdefault("document_id", data.get("document_id"))
                holding.setdefault("report_date", data.get("report_date"))

        all_holdings.extend(holdings)

        documents.append({
            "document_id": data.get("document_id"),
            "filename": data.get("filename"),
            "document_type": data.get("document_type", "excel"),
            "currency": data.get("currency"),
            "total_value": data.get("total_value"),
            "record_count": len(holdings),
            "report_date": data.get("report_date"),
            "account_holder": data.get("account_holder"),
            "saved_at": data.get("saved_at"),
        })

    print(f"STRUCTURED HOLDINGS LOADED: {len(all_holdings)}")
    print(f"STRUCTURED DOCUMENTS LOADED: {len(documents)}")

    return all_holdings, documents


def _holding_key(holding: dict):
    """
    Identity of a holding across documents.
    Mutual funds: ISIN + folio (two folios of one fund stay separate).
    Listed shares: ISIN. Without an ISIN: name + folio.
    """
    isin = str(holding.get("isin") or "").strip().upper()
    folio = str(holding.get("folio_number") or "").strip()

    if isin:
        return ("isin", isin, folio)

    return ("name", str(holding.get("name") or "").strip().lower(), folio)


def _completeness(holding: dict) -> int:
    fields = (
        "invested_value", "current_value", "quantity",
        "profit_loss", "asset_class", "sub_category", "folio_number",
    )
    return sum(1 for field in fields if holding.get(field) not in (None, ""))


def consolidate_holdings(holdings: list, documents: list):
    """
    Merge holdings from several documents that describe the same
    valuation date (for example a fund-house statement, a CAS and a
    demat statement). The same holding found in more than one document
    is counted once, and large value differences are reported.
    """
    filenames = {d["document_id"]: d.get("filename") for d in documents}
    saved_at = {d["document_id"]: d.get("saved_at") or "" for d in documents}

    groups = {}

    for holding in holdings:
        groups.setdefault(_holding_key(holding), []).append(holding)

    consolidated = []
    differences = []
    duplicates_removed = 0

    for records in groups.values():

        # Prefer the most complete record, then the newest upload.
        records = sorted(
            records,
            key=lambda r: (
                _completeness(r),
                saved_at.get(r.get("document_id"), ""),
            ),
            reverse=True,
        )

        chosen = dict(records[0])

        if len(records) > 1:
            duplicates_removed += len(records) - 1

            chosen["found_in"] = sorted({
                filenames.get(r.get("document_id")) or "unknown"
                for r in records
            })

            values = [
                r.get("current_value") for r in records
                if isinstance(r.get("current_value"), (int, float))
            ]

            if values:
                spread = max(values) - min(values)

                if spread > max(1.0, 0.005 * max(values)):
                    differences.append({
                        "name": chosen.get("name"),
                        "values": sorted(set(values)),
                    })

        consolidated.append(chosen)

    info = {
        "reports_used": len(documents),
        "records_before_dedupe": len(holdings),
        "records_after_dedupe": len(consolidated),
        "duplicates_removed": duplicates_removed,
        "valuation_differences": differences,
    }

    return consolidated, info


def load_latest_portfolio(client_id: str, document_type: str | None = None):
    """
    Return the newest valuation snapshot for the most recently identified
    account holder. This prevents unrelated people’s statements from being
    combined in analytics, risk, or document-grounded portfolio answers.
    """
    holdings, documents = load_all_portfolio_holdings(client_id)

    if document_type:
        documents = [
            d for d in documents
            if (d.get("document_type") or "").lower() == document_type.lower()
        ]

    if not documents:
        return [], [], {}

    all_documents_before_account_filter = list(documents)
    documents, active_account_holder = select_account_holder_documents(documents)

    if not documents:
        return [], [], {}

    latest_date = max(d.get("report_date") or "" for d in documents)

    selected = [
        d for d in documents
        if (d.get("report_date") or "") == latest_date
    ]

    selected_ids = {d["document_id"] for d in selected}

    selected_holdings = [
        h for h in holdings
        if h.get("document_id") in selected_ids
    ]

    consolidated, info = consolidate_holdings(selected_holdings, selected)
    info["report_date"] = latest_date or None
    info["account_holder"] = (
        selected[0].get("account_holder") if selected else active_account_holder
    )
    info["excluded_account_document_count"] = (
        len(all_documents_before_account_filter) - len(documents)
        if active_account_holder else 0
    )

    return consolidated, selected, info


def build_history_records(client_id: str):
    """One record per holding per saved report for the active account only."""
    holdings, documents = load_all_portfolio_holdings(client_id)

    identified = [
        document for document in documents
        if isinstance(document.get("account_holder"), str)
        and document["account_holder"].strip()
    ]

    if identified:
        latest = max(
            identified,
            key=lambda d: (d.get("report_date") or "", d.get("saved_at") or ""),
        )
        active_holder = " ".join(
            latest["account_holder"].strip().casefold().split()
        )
        active_document_ids = {
            document.get("document_id")
            for document in documents
            if " ".join(
                str(document.get("account_holder") or "").strip().casefold().split()
            ) == active_holder
        }
        holdings = [
            holding for holding in holdings
            if holding.get("document_id") in active_document_ids
        ]

    return [
        {
            "isin": holding.get("isin"),
            "folio_number": holding.get("folio_number"),
            "name": holding.get("name"),
            "report_date": holding.get("report_date"),
            "current_value": holding.get("current_value"),
        }
        for holding in holdings
    ]


def build_portfolio_for_analysis(request):
    """Prefer the client's latest saved report; fall back to posted holdings."""
    validate_client_id(request.client_id)

    holdings, documents, consolidation = load_latest_portfolio(
        request.client_id
    )

    if holdings:
        return {
            "client_id": request.client_id,
            "currency": request.currency,
            "report_date": consolidation.get("report_date"),
            "holdings": holdings,
            "profile": request.profile,
            "consolidation": consolidation,
        }

    portfolio = request.model_dump()

    if not portfolio.get("holdings"):
        raise HTTPException(
            status_code=400,
            detail="No saved report or holdings supplied.",
        )

    return portfolio


# --------------------------------------------------
# EXCEL TO SEARCHABLE TEXT
# --------------------------------------------------

def excel_to_chunks(extracted_data, filename, document_id):
    chunks = []

    if not isinstance(extracted_data, dict):
        print("Invalid Excel extraction structure:", type(extracted_data))
        return chunks

    for sheet_name, sheet_data in extracted_data.items():
        if not isinstance(sheet_data, dict):
            print(f"Skipping invalid sheet data: {sheet_name}")
            continue

        if sheet_data.get("status") != "processed":
            print(
                f"Skipping sheet: {sheet_name}, "
                f"status: {sheet_data.get('status')}"
            )
            continue

        holdings = sheet_data.get("holdings", [])

        print(
            f"Sheet: {sheet_name}, "
            f"Holdings detected: {len(holdings)}"
        )

        for record_number, holding in enumerate(holdings, start=1):
            text_parts = [
                f"Investment name: {holding.get('name', 'Unknown')}",
                f"Sheet name: {sheet_name}",
                f"Excel row number: {holding.get('row_number', 'Unknown')}",
            ]

            field_labels = {
                "symbol": "Symbol",
                "isin": "ISIN",
                "asset_class": "Asset class",
                "sub_category": "Sub category",
                "quantity": "Quantity",
                "invested_value": "Invested value",
                "current_value": "Current value",
                "profit_loss": "Profit or loss",
                "profit_loss_percentage": "Profit or loss percentage",
                "folio_number": "Folio number",
                "source": "Investment source",
                "average_nav": "Average NAV",
                "current_nav": "Current NAV",
            }

            for field, label in field_labels.items():
                value = holding.get(field)
                if value is not None and value != "":
                    text_parts.append(f"{label}: {value}")

            chunks.append({
                "document_id": str(document_id),
                "text": "\n".join(text_parts),
                "source": filename,
                "page": None,
                "sheet": sheet_name,
                "record": record_number,
                "row_number": holding.get("row_number"),
                "document_type": "excel",
            })

    return chunks


def extract_all_excel_holdings(
    extracted_data,
    document_id,
    filename,
    report_date=None,
):
    """Flatten every successfully processed sheet into one holdings list."""
    all_holdings = []
    sheets = extracted_data.get("sheets", {})

    if not isinstance(sheets, dict):
        return all_holdings

    for sheet_name, sheet_data in sheets.items():
        if not isinstance(sheet_data, dict):
            continue

        if sheet_data.get("status") != "processed":
            continue

        for holding in sheet_data.get("holdings", []):
            if not isinstance(holding, dict):
                continue

            record = dict(holding)
            record["sheet"] = sheet_name
            record["document_id"] = document_id
            record["source_file"] = filename
            record["report_date"] = report_date
            all_holdings.append(record)

    return all_holdings


# --------------------------------------------------
# REQUEST MODELS
# --------------------------------------------------

class ChatRequest(BaseModel):
    question: str
    client_id: str


class HoldingRequest(BaseModel):
    name: str
    asset_class: str = "Other"
    sub_category: str | None = None
    sector: str | None = None
    isin: str | None = None
    folio_number: str | None = None
    quantity: float | None = None
    invested_value: float | None = None
    current_value: float | None = None
    profit_loss: float | None = None
    profit_loss_percentage: float | None = None
    source: str | None = None
    average_nav: float | None = None
    current_nav: float | None = None
    report_date: str | None = None
    page: int | None = None


class PortfolioRequest(BaseModel):
    client_id: str
    currency: str = "INR"
    # Optional: when the client has a saved report, it is used instead.
    holdings: list[HoldingRequest] = []
    report_date: str | None = None
    # Example: {"risk_tolerance": "conservative", "goal": "retirement"}
    profile: dict | None = None


class PerformanceSnapshotRequest(BaseModel):
    report_date: str
    total_value: float


class PerformanceRequest(BaseModel):
    client_id: str
    snapshots: list[PerformanceSnapshotRequest]


# --------------------------------------------------
# BASIC ROUTES
# --------------------------------------------------

@app.get("/")
def home():
    return {"message": "WealthWise AI Engine is Running!"}


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "python-ai-engine",
        "client_isolation": "enabled",
    }


# --------------------------------------------------
# DOCUMENT UPLOAD
# --------------------------------------------------

@app.post(
    "/upload",
    dependencies=[Depends(verify_service_secret)],
)
async def upload_document(
    file: UploadFile = File(...),
    client_id: str = Form(...),
    document_id: str = Form(...),
):
    validate_client_id(client_id)
    validate_document_id(document_id)

    original_filename = file.filename or "uploaded_document"
    extension = Path(original_filename).suffix.lower()

    # If this prints a shortened name, the cut happens before Python.
    print("UPLOAD FILENAME:", original_filename)

    if extension not in (".pdf", ".xlsx"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF and XLSX files are accepted.",
        )

    safe_filename = f"{uuid.uuid4().hex}{extension}"

    client_upload_dir = UPLOAD_DIR / client_id
    client_upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = client_upload_dir / safe_filename

    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        file_size = file_path.stat().st_size

        if file_size == 0:
            raise HTTPException(
                status_code=400,
                detail="Uploaded file is empty.",
            )

        if file_size > 10 * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail="File must be smaller than 10 MB.",
            )

        vector_store = get_client_vector_store(client_id)

        # ------------------------------------------
        # PDF PROCESSING
        # ------------------------------------------
        if extension == ".pdf":
            portfolio_data = extract_portfolio_from_pdf(str(file_path))

            chunks = process_pdf(
                str(file_path),
                document_id,
                original_filename,
            )

            if not chunks:
                raise HTTPException(
                    status_code=422,
                    detail="No extractable text found in PDF.",
                )

            pdf_holdings = (
                portfolio_data.get("holdings", [])
                if isinstance(portfolio_data, dict)
                else []
            )

            if not isinstance(pdf_holdings, list) or not pdf_holdings:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "No structured investment holdings could be "
                        "extracted from this PDF. The document text may "
                        "still be readable, but portfolio-wide answers "
                        "require structured holdings."
                    ),
                )

            for chunk in chunks:
                chunk["source"] = original_filename
                chunk["document_type"] = "pdf"

            # Persist PDF holdings in the same per-document format used
            # by Excel. Chat, analytics and risk can then use one
            # consolidated structured-data pipeline for both formats.
            save_portfolio_data(
                client_id,
                document_id,
                {
                    "document_id": document_id,
                    "filename": original_filename,
                    "document_type": "pdf",
                    "report_date": portfolio_data.get("report_date"),
                    "account_holder": portfolio_data.get("account_holder"),
                    "currency": portfolio_data.get("currency"),
                    "total_value": portfolio_data.get("total_value"),
                    "holdings": pdf_holdings,
                },
            )

            client_vector_dir = VECTOR_DIR / client_id

            try:
                vector_store.build_index(chunks)
                vector_store.save(str(client_vector_dir))
            except Exception:
                # Keep structured data and the vector index consistent.
                get_portfolio_file(client_id, document_id).unlink(
                    missing_ok=True
                )
                raise

            return {
                "message": "PDF document processed successfully.",
                "filename": original_filename,
                "stored_filename": safe_filename,
                "total_chunks": len(chunks),
                "total_structured_holdings": len(pdf_holdings),
                "client_id": client_id,
                "status": "ready",
                "document_type": "pdf",
                "portfolio": portfolio_data,
                "structured_holdings_saved": True,
            }

        # ------------------------------------------
        # EXCEL PROCESSING
        # ------------------------------------------
        extracted_data = extract_excel(str(file_path))

        if not extracted_data:
            raise HTTPException(
                status_code=422,
                detail="No readable data found in Excel file.",
            )

        excel_chunks = excel_to_chunks(
            extracted_data.get("sheets", {}),
            original_filename,
            document_id,
        )

        if not excel_chunks:
            raise HTTPException(
                status_code=422,
                detail="No searchable investment records found in Excel.",
            )

        report_date = extracted_data.get("report_date")
        print("EXTRACTED REPORT DATE:", report_date)

        # Flatten all successfully extracted sheets.
        all_holdings = extract_all_excel_holdings(
            extracted_data,
            document_id,
            original_filename,
            report_date,
        )

        if not all_holdings:
            raise HTTPException(
                status_code=422,
                detail="No structured investment holdings were extracted.",
            )

        print(f"EXTRACTED STRUCTURED HOLDINGS: {len(all_holdings)}")

        # Save the complete structured holdings first, then index. If
        # indexing fails, the structured file is removed again so the
        # two stores never disagree.
        save_portfolio_data(
            client_id,
            document_id,
            {
                "document_id": document_id,
                "filename": original_filename,
                "document_type": "excel",
                "report_date": report_date,
                "account_holder": extracted_data.get("account_holder"),
                "currency": "INR",
                "holdings": all_holdings,
            },
        )

        client_vector_dir = VECTOR_DIR / client_id

        try:
            vector_store.build_index(excel_chunks)
            vector_store.save(str(client_vector_dir))
        except Exception:
            get_portfolio_file(client_id, document_id).unlink(
                missing_ok=True
            )
            raise

        return {
            "message": "Excel document processed and indexed successfully.",
            "filename": original_filename,
            "stored_filename": safe_filename,
            "total_chunks": len(excel_chunks),
            "total_structured_holdings": len(all_holdings),
            "client_id": client_id,
            "status": "ready",
            "document_type": "excel",
            "report_date": report_date,
            "account_holder": extracted_data.get("account_holder"),
            "folio_metadata": extracted_data.get("folio_metadata", []),
            "sheets": extracted_data.get("sheets", {}),
        }

    except HTTPException:
        # Remove a partially uploaded file on a failed request.
        if file_path.exists():
            try:
                file_path.unlink()
            except OSError:
                pass
        raise

    except Exception as error:
        traceback.print_exc()

        if file_path.exists():
            try:
                file_path.unlink()
            except OSError:
                pass

        raise HTTPException(
            status_code=500,
            detail=f"Document processing failed: {str(error)}",
        )

    finally:
        await file.close()


# --------------------------------------------------
# DOCUMENT DELETION
# --------------------------------------------------

@app.delete(
    "/documents/{document_id}",
    dependencies=[Depends(verify_service_secret)],
)
def delete_document(
    document_id: str,
    client_id: str = Query(...),
    stored_filename: str = Query(...),
):
    validate_client_id(client_id)
    validate_document_id(document_id)

    # Only accept a generated UUID filename with a supported extension.
    is_new_filename = bool(
        re.fullmatch(
            r"[a-fA-F0-9]{32}\.(pdf|xlsx)",
            stored_filename or "",
        )
    )

    file_path = None
    if is_new_filename:
        file_path = UPLOAD_DIR / client_id / stored_filename

    try:
        # Remove only this document's FAISS chunks.
        vector_store = get_client_vector_store(client_id)
        removed_chunks = vector_store.remove_document(document_id)

        # Save the updated client index.
        client_vector_dir = VECTOR_DIR / client_id

        if vector_store.index is not None:
            vector_store.save(str(client_vector_dir))
        else:
            (client_vector_dir / "index.faiss").unlink(missing_ok=True)
            (client_vector_dir / "documents.json").unlink(missing_ok=True)

        # Remove the uploaded source file.
        if file_path and file_path.exists():
            file_path.unlink()

        # Remove this document's structured portfolio data.
        portfolio_file = get_portfolio_file(client_id, document_id)
        portfolio_file.unlink(missing_ok=True)

        return {
            "message": "Document data deleted successfully.",
            "document_id": document_id,
            "removed_chunks": removed_chunks,
            "structured_data_deleted": True,
        }

    except HTTPException:
        raise

    except Exception:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail="Document deletion failed.",
        )


# --------------------------------------------------
# AI CHAT
# --------------------------------------------------

@app.post(
    "/chat",
    dependencies=[Depends(verify_service_secret)],
)
def chat(request: ChatRequest):
    if not request.question.strip():
        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty.",
        )

    validate_client_id(request.client_id)

    try:
        vector_store = get_client_vector_store(request.client_id)

        if vector_store.index is None:
            raise HTTPException(
                status_code=400,
                detail="Upload a document before asking questions.",
            )

        # If the user explicitly asks about a PDF, scope structured
        # holdings to the newest PDF report instead of mixing Excel data.
        asks_about_pdf = bool(re.search(r"\bpdf\b", request.question, re.IGNORECASE))
        requested_document_type = "pdf" if asks_about_pdf else None

        holdings, documents, consolidation = load_latest_portfolio(
            request.client_id,
            document_type=requested_document_type,
        )

        calculation_data = None

        if holdings:
            # Currency is assumed INR because the Excel extractor does
            # not return per-holding currency.
            portfolio = {
                "client_id": request.client_id,
                "currency": "INR",
                "report_date": consolidation.get("report_date"),
                "holdings": holdings,
            }

            # Portfolio metrics require a valid numeric current value
            # for every holding. A missing value must not crash simple
            # document lookups such as listing investment names.
            current_values_complete = all(
                isinstance(h.get("current_value"), (int, float))
                and not isinstance(h.get("current_value"), bool)
                and math.isfinite(h.get("current_value"))
                and h.get("current_value") >= 0
                for h in holdings
            )

            if current_values_complete:
                calculation_data = calculate_portfolio_metrics(portfolio)
                calculation_data["documents"] = documents
                calculation_data["consolidation"] = consolidation
            elif is_listing_question(request.question):
                # A name listing needs no valuation. Do not calculate or
                # expose portfolio totals from incomplete holding data.
                calculation_data = {
                    "holdings": holdings,
                    "holding_count": len(holdings),
                    "documents": documents,
                    "consolidation": consolidation,
                    "data_incomplete": True,
                }
            else:
                print(
                    "CHAT METRICS UNAVAILABLE: missing or invalid "
                    "current_value in one or more holdings.",
                    flush=True,
                )

        print("CHAT STRUCTURED HOLDINGS:", len(holdings))

        if calculation_data is not None:
            print(
                "CHAT CALCULATED HOLDING COUNT:",
                calculation_data.get("holding_count"),
            )
            print(
                "CHAT TOTAL INVESTED:",
                calculation_data.get("total_invested"),
            )

        result = generate_answer(
            request.question,
            vector_store,
            top_k=8,
            calculation_data=calculation_data,
            document_type_filter=requested_document_type,
        )

        return {
            "question": request.question,
            "answer": result["answer"],
            "sources": result["sources"],
            "calculation_used": result["calculation_used"],
            "retrieved_chunks": result.get("retrieved_chunks", 0),
            "total_structured_records": len(holdings),
            "structured_documents": documents,
            "consolidation": consolidation,
        }

    except HTTPException:
        raise

    except Exception as error:
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=f"Question processing failed: {str(error)}",
        )


# --------------------------------------------------
# PORTFOLIO ANALYTICS
# --------------------------------------------------

@app.post(
    "/analytics",
    dependencies=[Depends(verify_service_secret)],
)
def analytics(request: PortfolioRequest):
    try:
        portfolio = build_portfolio_for_analysis(request)
        return calculate_portfolio_metrics(portfolio)

    except HTTPException:
        raise

    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))

    except Exception as error:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(error))


# --------------------------------------------------
# CONSOLIDATED PORTFOLIO (single source of truth for the dashboard)
# --------------------------------------------------

@app.post(
    "/portfolio/consolidated",
    dependencies=[Depends(verify_service_secret)],
)
def consolidated_portfolio(request: PortfolioRequest):
    try:
        portfolio = build_portfolio_for_analysis(request)
        metrics = calculate_portfolio_metrics(portfolio)

        return {
            "metrics": metrics,
            "consolidation": portfolio.get("consolidation", {}),
        }

    except HTTPException:
        raise

    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))

    except Exception as error:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(error))


# --------------------------------------------------
# RISK ANALYSIS
# --------------------------------------------------

@app.post(
    "/risk",
    dependencies=[Depends(verify_service_secret)],
)
def risk_analysis(request: PortfolioRequest):
    try:
        portfolio = build_portfolio_for_analysis(request)

        return analyze_portfolio_risk(
            portfolio,
            history_records=build_history_records(request.client_id),
            profile=portfolio.get("profile"),
        )

    except HTTPException:
        raise

    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))

    except Exception as error:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(error))


@app.post(
    "/risk/goal",
    dependencies=[Depends(verify_service_secret)],
)
def goal_risk_analysis(request: PortfolioRequest):
    try:
        validate_client_id(request.client_id)

        # Unlike /risk, use the holdings supplied by Node.js.
        # Do not replace them with the client's complete saved portfolio.
        portfolio = request.model_dump()

        if not portfolio.get("holdings"):
            raise HTTPException(
                status_code=400,
                detail="No allocated goal holdings supplied.",
            )

        return analyze_portfolio_risk(
            portfolio,
            history_records=build_history_records(request.client_id),
            profile=request.profile,
        )

    except HTTPException:
        raise

    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))

    except Exception as error:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(error))

# --------------------------------------------------
# AI RISK EXPLANATION
# --------------------------------------------------

@app.post(
    "/risk/explanation",
    dependencies=[Depends(verify_service_secret)],
)
def risk_explanation(request: PortfolioRequest):
    try:
        portfolio = build_portfolio_for_analysis(request)

        risk_data = analyze_portfolio_risk(
            portfolio,
            history_records=build_history_records(request.client_id),
            profile=portfolio.get("profile"),
        )

        explanation = generate_risk_explanation(risk_data)

        return {
            "explanation": explanation,
            "metrics": risk_data,
        }

    except HTTPException:
        raise

    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))

    except Exception as error:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(error))


# --------------------------------------------------
# HISTORICAL PERFORMANCE
# --------------------------------------------------

@app.post(
    "/performance",
    dependencies=[Depends(verify_service_secret)],
)
def portfolio_performance(request: PerformanceRequest):
    try:
        validate_client_id(request.client_id)

        snapshots = [
            snapshot.model_dump()
            for snapshot in request.snapshots
        ]

        result = calculate_portfolio_performance(snapshots)

        return {
            "client_id": request.client_id,
            "performance": result,
        }

    except HTTPException:
        raise

    except Exception:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail="Performance calculation failed.",
        )