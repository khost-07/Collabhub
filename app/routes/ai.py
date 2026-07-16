import io
import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.models import get_db, Document, Project, ProjectRole, User, Conversation, Message, ConversationMember
from app.auth import require_login, NotAuthorizedException, NotFoundException, log_action

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def get_gemini_api_key(db: Session) -> Optional[str]:
    """Retrieve custom Google Gemini API Key from the CEO/Admin user, or fallback to environment variable."""
    admin_user = db.query(User).filter(User.role == "admin", User.gemini_api_key.is_not(None), User.gemini_api_key != "").first()
    if admin_user:
        return admin_user.gemini_api_key
    from app.config import GEMINI_API_KEY
    return GEMINI_API_KEY or None


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


def summarize_document(text: str, api_key: Optional[str]) -> str:
    """Use Google Gemini to generate a 2-3 sentence summary of *text*."""
    if not api_key:
        return "AI summary unavailable (API key not configured)."
    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-3.5-flash",
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


def search_documents(query: str, documents: list, api_key: Optional[str]) -> list[dict]:
    """
    Ask Gemini to rank *documents* by relevance to *query*.

    Returns a list of ``{"document_id": int, "reason": str}`` dicts.
    """
    if not api_key:
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

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-3.5-flash",
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

    # Determine which documents the user may access (isolated by organization_id)
    if user.role == "admin":
        documents = db.query(Document).join(Project).filter(Project.organization_id == user.organization_id).all()
    elif user.role == "manager":
        allowed_project_ids = (
            db.query(ProjectRole.project_id)
            .join(Project)
            .filter(ProjectRole.role == "manager", Project.organization_id == user.organization_id)
            .subquery()
        )
        documents = (
            db.query(Document)
            .join(Project)
            .filter(Project.organization_id == user.organization_id)
            .filter((Project.created_by == user.id) | Document.project_id.in_(allowed_project_ids))
            .all()
        )
    else:
        allowed_project_ids = (
            db.query(ProjectRole.project_id)
            .join(Project)
            .filter(ProjectRole.role == user.role, Project.organization_id == user.organization_id)
            .subquery()
        )
        documents = (
            db.query(Document)
            .join(Project)
            .filter(Project.organization_id == user.organization_id)
            .filter(Document.project_id.in_(allowed_project_ids))
            .all()
        )

    api_key = get_gemini_api_key(db)
    ai_results = search_documents(query, documents, api_key)

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


# ---------------------------------------------------------------------------
# Project Files Cohesive Summary
# ---------------------------------------------------------------------------


@router.post("/projects/{project_id}/summarize-files")
def summarize_project_files(project_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    
    project = db.query(Project).filter(Project.id == project_id, Project.organization_id == user.organization_id).first()
    if not project:
        raise NotFoundException()

    # Reuse project role access check logic
    from app.routes.documents import _check_project_access
    _check_project_access(user, project, db)

    docs = project.documents
    if not docs:
        return RedirectResponse(
            url=f"/projects/{project_id}?message=No+documents+in+project+to+summarize&type=error",
            status_code=303
        )

    # Gather content for summarization
    content_parts = []
    for doc in docs:
        text = extract_text(doc.file_content, doc.file_type)
        content_parts.append(
            f"File: {doc.original_filename}\n"
            f"Summary: {doc.summary or 'No summary available'}\n"
            f"Text snippet: {text[:2000]}\n"
        )
    combined_text = "\n\n---\n\n".join(content_parts)

    api_key = get_gemini_api_key(db)
    if not api_key:
        return RedirectResponse(
            url=f"/projects/{project_id}?message=AI+summary+failed%3A+Gemini+API+Key+not+configured&type=error",
            status_code=303
        )

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=(
                "You are an expert project assistant. Provide a cohesive, unified executive summary "
                "of the following project documents. Highlight the main goals, statuses, findings, "
                "and any key action items or deadlines mentioned. Keep it to 2-3 concise paragraphs:\n\n"
                + combined_text[:12000]
            ),
        )
        
        project.files_summary = response.text.strip()
        db.commit()

        log_action(
            db,
            user.id,
            user.email,
            "summarize_project_files",
            resource_type="project",
            resource_id=project.id,
            details=f"Generated unified files summary for project '{project.name}'",
        )

        return RedirectResponse(
            url=f"/projects/{project_id}?message=Project+files+summarized+successfully&type=success",
            status_code=303
        )
    except Exception as exc:
        logger.error("Project file summarization failed: %s", exc)
        return RedirectResponse(
            url=f"/projects/{project_id}?message=AI+summary+failed%3A+{exc}&type=error",
            status_code=303
        )


# ---------------------------------------------------------------------------
# Chat Catch-Up Smart Summary
# ---------------------------------------------------------------------------


@router.get("/chat/conversations/{conversation_id}/catch-up")
def chat_catch_up(conversation_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)

    conv = db.query(Conversation).filter_by(id=conversation_id, organization_id=user.organization_id).first()
    if not conv:
        raise NotFoundException()

    if conv.type != "community":
        is_member = db.query(ConversationMember).filter_by(
            conversation_id=conversation_id, user_id=user.id
        ).first()
        if not is_member:
            raise NotAuthorizedException("You do not have access to this conversation.")

    # Fetch last 30 messages in this room
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.timestamp.desc())
        .limit(30)
        .all()
    )
    # Reverse to keep it in chronological order
    messages.reverse()

    if not messages:
        return JSONResponse(content={"summary": "No messages in this chat to summarize yet."})

    # Build conversation transcript
    transcript = []
    for msg in messages:
        transcript.append(f"{msg.sender.name}: {msg.content}")
    transcript_text = "\n".join(transcript)

    api_key = get_gemini_api_key(db)
    if not api_key:
        return JSONResponse(
            content={"error": "Gemini API key is not configured. Please add your key in Onboarding."}
        )

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=(
                "You are an AI chat assistant. Catch the user up by summarizing the following recent chat messages "
                "in 3-4 bullet points. Focus on key decisions, questions, outcomes, or action items discussed:\n\n"
                + transcript_text
            ),
        )

        return JSONResponse(content={"summary": response.text.strip()})
    except Exception as exc:
        logger.error("Chat catch up failed: %s", exc)
        return JSONResponse(
            content={"error": f"AI Catch-Up failed: {exc}"}
        )
