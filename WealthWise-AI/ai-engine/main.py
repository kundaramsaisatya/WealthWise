
import os
import shutil
import uuid
import secrets
import re
from pathlib import Path
from portfolio_analytics import calculate_portfolio_metrics

from portfolio_extractor import extract_portfolio_from_pdf
from risk_engine import analyze_portfolio_risk
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from risk_explainer import generate_risk_explanation
from document_processor import process_pdf
from vector_store import VectorStore
from rag import generate_answer


app = FastAPI(
    title="WealthWise AI",
    description="AI-powered Wealth Management Assistant",
    version="1.0.0"
)
AI_SERVICE_SECRET = os.getenv("AI_SERVICE_SECRET")

if not AI_SERVICE_SECRET:
    raise RuntimeError("AI_SERVICE_SECRET is missing from environment.")

from fastapi import Header, Depends


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

# Project directories
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
VECTOR_DIR = BASE_DIR / "data" / "vector_data"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# Shared vector store for this initial demo
# Separate vector stores for each client
vector_stores = {}


def validate_client_id(client_id: str):
    if not re.fullmatch(r"CLIENT-[a-fA-F0-9-]{36}", client_id):
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


class ChatRequest(BaseModel):
    question: str
    client_id: str

class PortfolioRequest(BaseModel):
    client_id: str
    currency: str
    holdings: list[dict]


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


@app.post("/upload", dependencies=[Depends(verify_service_secret)])
async def upload_document(
    file: UploadFile = File(...),
    client_id: str = Form(...)
):
    validate_client_id(client_id)

    if not file.filename or Path(file.filename).suffix.lower() != ".pdf":
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are accepted."
        )

    safe_filename = f"{uuid.uuid4().hex}.pdf"
    client_upload_dir = UPLOAD_DIR / client_id
    client_upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = client_upload_dir / safe_filename

    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        file_size = file_path.stat().st_size

        if file_size == 0:
            raise HTTPException(400, "Uploaded PDF is empty.")

        if file_size > 10 * 1024 * 1024:
            raise HTTPException(413, "PDF must be smaller than 10 MB.")

        chunks = process_pdf(str(file_path))

        if not chunks:
            raise HTTPException(
                status_code=422,
                detail="No extractable text found in PDF."
            )

        for chunk in chunks:
            chunk["source"] = file.filename

        vector_store = get_client_vector_store(client_id)

        vector_store.build_index(chunks)

        client_vector_dir = VECTOR_DIR / client_id
        vector_store.save(str(client_vector_dir))
        # Extract structured portfolio information
        portfolio_data = extract_portfolio_from_pdf(str(file_path))

        return {
            "message": "Document processed successfully.",
            "filename": file.filename,
            "total_chunks": len(chunks),
            "client_id": client_id,
            "status": "ready",
            "portfolio": portfolio_data

        }

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Document processing failed: {str(error)}"
        )

    finally:
        await file.close()



@app.post("/chat", dependencies=[Depends(verify_service_secret)])
def chat(request: ChatRequest):

    if not request.question.strip():
        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty."
        )

    try:
        vector_store = get_client_vector_store(request.client_id)

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
        raise HTTPException(
            status_code=500,
            detail=f"Question processing failed: {str(error)}"
        )
    
@app.post("/analytics", dependencies=[Depends(verify_service_secret)])
def analytics(request: PortfolioRequest):

    try:
        validate_client_id(request.client_id)

        portfolio = request.model_dump()

        return calculate_portfolio_metrics(portfolio)

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=str(error)
        )

@app.post("/risk", dependencies=[Depends(verify_service_secret)])
def risk_analysis(request: PortfolioRequest):

    try:
        validate_client_id(request.client_id)

        portfolio = request.model_dump()

        return analyze_portfolio_risk(portfolio)

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=str(error)
        )

@app.post(
    "/risk/explanation",
    dependencies=[Depends(verify_service_secret)]
)
def risk_explanation(request: PortfolioRequest):

    try:
        validate_client_id(request.client_id)

        portfolio = request.model_dump()

        risk_data = analyze_portfolio_risk(portfolio)

        explanation = generate_risk_explanation(risk_data)

        return {
            "explanation": explanation,
            "metrics": risk_data
        }

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=str(error)
        )