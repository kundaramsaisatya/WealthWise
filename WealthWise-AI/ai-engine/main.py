
import os
import shutil
import uuid
import secrets
import re
import traceback

from pathlib import Path
from dotenv import load_dotenv

from fastapi import (
    FastAPI,
    UploadFile,
    File,
    Form,
    HTTPException,
    Header,
    Depends
)

from pydantic import BaseModel

from portfolio_analytics import calculate_portfolio_metrics
from excel_extractor import extract_excel
from portfolio_extractor import extract_portfolio_from_pdf
from risk_engine import analyze_portfolio_risk
from risk_explainer import generate_risk_explanation
from document_processor import process_pdf
from vector_store import VectorStore
from rag import generate_answer


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

AI_SERVICE_SECRET = os.getenv("AI_SERVICE_SECRET")

if not AI_SERVICE_SECRET:
    raise RuntimeError(
        "AI_SERVICE_SECRET is missing from environment."
    )

UPLOAD_DIR = BASE_DIR / "data" / "uploads"
VECTOR_DIR = BASE_DIR / "data" / "vector_data"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
VECTOR_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="WealthWise AI",
    description="AI-powered Wealth Management Assistant",
    version="1.1.0"
)


# --------------------------------------------------
# AUTHENTICATION
# --------------------------------------------------

def verify_service_secret(
    x_service_secret: str = Header(...)
):

    if not secrets.compare_digest(
        x_service_secret,
        AI_SERVICE_SECRET
    ):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized service request."
        )


# --------------------------------------------------
# CLIENT VECTOR STORES
# --------------------------------------------------

vector_stores = {}


def validate_client_id(client_id: str):

    if not re.fullmatch(
        r"CLIENT-[a-fA-F0-9-]{36}",
        client_id
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid client ID."
        )


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


# --------------------------------------------------
# EXCEL TO SEARCHABLE TEXT
# --------------------------------------------------

def excel_to_chunks(extracted_data, filename):

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
                f"Excel row number: {holding.get('row_number', 'Unknown')}"
            ]

            field_labels = {
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
                "current_nav": "Current NAV"
            }

            for field, label in field_labels.items():

                value = holding.get(field)

                if value is not None and value != "":
                    text_parts.append(f"{label}: {value}")

            chunks.append({
                "text": "\n".join(text_parts),
                "source": filename,
                "page": None,
                "sheet": sheet_name,
                "record": record_number,
                "row_number": holding.get("row_number"),
                "document_type": "excel"
            })

    return chunks
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

    page: int | None = None


class PortfolioRequest(BaseModel):

    client_id: str

    currency: str = "INR"

    holdings: list[HoldingRequest]


# --------------------------------------------------
# BASIC ROUTES
# --------------------------------------------------

@app.get("/")
def home():

    return {
        "message": "WealthWise AI Engine is Running!"
    }


@app.get("/health")
def health():

    return {
        "status": "healthy",
        "service": "python-ai-engine",
        "client_isolation": "enabled"
    }


# --------------------------------------------------
# DOCUMENT UPLOAD
# --------------------------------------------------

@app.post(
    "/upload",
    dependencies=[Depends(verify_service_secret)]
)
async def upload_document(
    file: UploadFile = File(...),
    client_id: str = Form(...)
):

    validate_client_id(client_id)

    original_filename = (
        file.filename or "uploaded_document"
    )

    extension = Path(original_filename).suffix.lower()

    if extension not in [".pdf", ".xlsx"]:
        raise HTTPException(
            status_code=400,
            detail="Only PDF and XLSX files are accepted."
        )

    safe_filename = f"{uuid.uuid4().hex}{extension}"

    client_upload_dir = UPLOAD_DIR / client_id
    client_upload_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    file_path = client_upload_dir / safe_filename

    try:

        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        file_size = file_path.stat().st_size

        if file_size == 0:
            raise HTTPException(
                status_code=400,
                detail="Uploaded file is empty."
            )

        if file_size > 10 * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail="File must be smaller than 10 MB."
            )

        vector_store = get_client_vector_store(client_id)

        # ------------------------------------------
        # PDF PROCESSING
        # ------------------------------------------

        if extension == ".pdf":

            chunks = process_pdf(str(file_path))

            if not chunks:
                raise HTTPException(
                    status_code=422,
                    detail="No extractable text found in PDF."
                )

            for chunk in chunks:

                chunk["source"] = original_filename
                chunk["document_type"] = "pdf"

            portfolio_data = extract_portfolio_from_pdf(
                str(file_path)
            )

            vector_store.build_index(chunks)

            client_vector_dir = VECTOR_DIR / client_id

            vector_store.save(str(client_vector_dir))

            return {
                "message": "PDF document processed and indexed successfully.",
                "filename": original_filename,
                "total_chunks": len(chunks),
                "client_id": client_id,
                "status": "ready",
                "document_type": "pdf",
                "portfolio": portfolio_data
            }

        # ------------------------------------------
        # EXCEL PROCESSING
        # ------------------------------------------

        elif extension == ".xlsx":

            extracted_data = extract_excel(
                str(file_path)
            )

            if not extracted_data:
                raise HTTPException(
                    status_code=422,
                    detail="No readable data found in Excel file."
                )

            excel_chunks = excel_to_chunks(
                extracted_data.get("sheets", {}),
                original_filename
            )

            report_date = extracted_data.get("report_date")

            if not excel_chunks:
                raise HTTPException(
                    status_code=422,
                    detail="No searchable investment records found in Excel."
                )

            vector_store.build_index(excel_chunks)

            client_vector_dir = VECTOR_DIR / client_id

            vector_store.save(str(client_vector_dir))

            return {
                "message": "Excel document processed and indexed successfully.",
                "filename": original_filename,
                "total_chunks": len(excel_chunks),
                "client_id": client_id,
                "status": "ready",
                "document_type": "excel",
                "report_date": report_date,
                "sheets": extracted_data.get("sheets", {})
            }
    except HTTPException:
        raise

    except Exception as error:

        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=f"Document processing failed: {str(error)}"
        )

    finally:
        await file.close()


# --------------------------------------------------
# AI CHAT
# --------------------------------------------------

@app.post(
    "/chat",
    dependencies=[Depends(verify_service_secret)]
)
def chat(request: ChatRequest):

    if not request.question.strip():
        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty."
        )

    validate_client_id(request.client_id)

    try:

        vector_store = get_client_vector_store(
            request.client_id
        )

        if vector_store.index is None:
            raise HTTPException(
                status_code=400,
                detail="Upload a document before asking questions."
            )

        result = generate_answer(
            request.question,
            vector_store,
            top_k=3
        )

        return {
            "question": request.question,
            "answer": result["answer"],
            "sources": result["sources"]
        }

    except HTTPException:
        raise

    except Exception as error:

        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=f"Question processing failed: {str(error)}"
        )


# --------------------------------------------------
# PORTFOLIO ANALYTICS
# --------------------------------------------------

@app.post(
    "/analytics",
    dependencies=[Depends(verify_service_secret)]
)
def analytics(request: PortfolioRequest):

    try:

        validate_client_id(request.client_id)

        portfolio = request.model_dump()

        return calculate_portfolio_metrics(portfolio)

    except HTTPException:
        raise

    except Exception as error:

        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )


# --------------------------------------------------
# RISK ANALYSIS
# --------------------------------------------------

@app.post(
    "/risk",
    dependencies=[Depends(verify_service_secret)]
)
def risk_analysis(request: PortfolioRequest):

    try:

        validate_client_id(request.client_id)

        portfolio = request.model_dump()

        return analyze_portfolio_risk(portfolio)

    except HTTPException:
        raise

    except Exception as error:

        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )


# --------------------------------------------------
# AI RISK EXPLANATION
# --------------------------------------------------

@app.post(
    "/risk/explanation",
    dependencies=[Depends(verify_service_secret)]
)
def risk_explanation(request: PortfolioRequest):

    try:

        validate_client_id(request.client_id)

        portfolio = request.model_dump()

        risk_data = analyze_portfolio_risk(
            portfolio
        )

        explanation = generate_risk_explanation(
            risk_data
        )

        return {
            "explanation": explanation,
            "metrics": risk_data
        }

    except HTTPException:
        raise

    except Exception as error:

        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )
