import io
import json
import logging
from typing import List

from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import GEMINI_API_KEY
from app.models import get_db, Document, Project, ProjectRole
from app.auth import require_login

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


def extract_text(file_content: bytes, file_type: str) -> str:
    """
    Extract plain text from raw file bytes.

    Supports ``pdf`` (via PyPDF2) and ``txt`` (UTF-8 decode).
    """
    if file_type == "pdf":
        try:
            import PyPDF2

            reader = PyPDF2.PdfReader(io.BytesIO(file_content))
            pages_text: list[str] = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    pages_text.append(page_text)
            return "\n".join(pages_text)
        except Exception as exc:
            logger.warning("Failed to extract text from PDF: %s", exc)
            return ""
    elif file_type == "txt":
        return file_content.decode("utf-8", errors="ignore")
    return ""


# ---------------------------------------------------------------------------
# AI helpers (Gemini)
# ---------------------------------------------------------------------------


def summarize_document(text: str) -> str:
    """Use Google Gemini to generate a 2-3 sentence summary of *text*."""
    if not GEMINI_API_KEY:
        return "AI summary unavailable (API key not configured)."
    try:
        from google import genai

        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=(
                "Summarize the following document in 2-3 concise sentences. "
                "Be specific about key topics and findings:\n\n"
                + text[:8000]
            ),
        )
        return response.text
    except Exception as exc:
        logger.error("Gemini summarization failed: %s", exc)
        return f"AI summary generation failed: {exc}"


def search_documents(query: str, documents: list) -> list[dict]:
    """
    Ask Gemini to rank *documents* by relevance to *query*.

    Returns a list of ``{"document_id": int, "reason": str}`` dicts.
    """
    if not GEMINI_API_KEY:
        return []
    if not documents:
        return []

    doc_summaries = []
    for doc in documents:
        doc_summaries.append(
            f"Document ID: {doc.id}, Filename: {doc.original_filename}, "
            f"Summary: {doc.summary or 'No summary available'}"
        )
    docs_text = "\n".join(doc_summaries)

    prompt = (
        f"Given the following search query: \"{query}\"\n\n"
        f"And the following documents:\n{docs_text}\n\n"
        "Return a JSON array of the most relevant documents, ranked by relevance. "
        "Each element should have 'document_id' (int) and 'reason' (str explaining "
        "why it matches). Only include documents that are relevant. "
        "Return ONLY valid JSON, no markdown formatting, no code fences."
    )

    try:
        from google import genai

        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        response_text = response.text.strip()
        # Strip markdown code fences if present
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            # Remove first and last lines (``` markers)
            lines = [
                line
                for line in lines
                if not line.strip().startswith("```")
            ]
            response_text = "\n".join(lines)
        results = json.loads(response_text)
        if isinstance(results, list):
            return results
        return []
    except Exception as exc:
        logger.error("Gemini search failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/search")
def search_page(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    return templates.TemplateResponse(
        "search_results.html",
        {"request": request, "user": user, "query": "", "results": []},
    )


@router.post("/search")
async def search_post(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    form = await request.form()
    query = form.get("query", "").strip()

    if not query:
        return templates.TemplateResponse(
            "search_results.html",
            {"request": request, "user": user, "query": query, "results": []},
        )

    # Determine which documents the user may access
    if user.role == "admin":
        documents = db.query(Document).all()
    elif user.role == "manager":
        allowed_project_ids = (
            db.query(ProjectRole.project_id)
            .filter(ProjectRole.role == "manager")
            .subquery()
        )
        documents = (
            db.query(Document)
            .join(Project)
            .filter((Project.created_by == user.id) | Document.project_id.in_(allowed_project_ids))
            .all()
        )
    else:
        allowed_project_ids = (
            db.query(ProjectRole.project_id)
            .filter(ProjectRole.role == user.role)
            .subquery()
        )
        documents = (
            db.query(Document)
            .filter(Document.project_id.in_(allowed_project_ids))
            .all()
        )

    ai_results = search_documents(query, documents)

    # Map AI results back to actual Document objects
    doc_map = {doc.id: doc for doc in documents}
    results: list[dict] = []
    for item in ai_results:
        doc_id = item.get("document_id")
        if doc_id and doc_id in doc_map:
            doc = doc_map[doc_id]
            project = db.query(Project).filter(Project.id == doc.project_id).first()
            results.append(
                {
                    "document": doc,
                    "reason": item.get("reason", ""),
                    "project_name": project.name if project else "Unknown",
                }
            )

    return templates.TemplateResponse(
        "search_results.html",
        {"request": request, "user": user, "query": query, "results": results},
    )
