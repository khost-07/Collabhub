import os

from fastapi import APIRouter, Request, Depends, UploadFile, File
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import MAX_FILE_SIZE
from app.models import get_db, Document, Project, ProjectMember
from app.auth import (
    require_login,
    require_manager_or_admin,
    NotAuthorizedException,
    NotFoundException,
    log_action,
)
from app.routes.ai import extract_text, summarize_document

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Allowed file types
ALLOWED_EXTENSIONS = {"pdf", "txt"}
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "text/plain",
}


def _get_file_extension(filename: str) -> str:
    """Return the lowercase extension without the leading dot."""
    _, ext = os.path.splitext(filename)
    return ext.lstrip(".").lower()


def _check_project_access(user, project, db: Session) -> None:
    """Raise NotAuthorizedException if user cannot access this project."""
    if user.role in ("admin", "manager"):
        return
    is_member = (
        db.query(ProjectMember)
        .filter(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == user.id,
        )
        .first()
    )
    if not is_member:
        raise NotAuthorizedException("You do not have access to this project.")


# ---------------------------------------------------------------------------
# Upload document
# ---------------------------------------------------------------------------


@router.post("/projects/{project_id}/documents/upload")
async def upload_document(
    project_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user = require_login(request, db)
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise NotFoundException()

    _check_project_access(user, project, db)

    # --- Validate file extension ---
    extension = _get_file_extension(file.filename or "")
    if extension not in ALLOWED_EXTENSIONS:
        return RedirectResponse(
            url=f"/projects/{project_id}?message=Only+PDF+and+TXT+files+are+allowed&type=error",
            status_code=303,
        )

    # --- Validate content type ---
    if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
        # Some browsers may send different content types; also accept by extension
        pass  # Extension check above is the primary gate

    # --- Read file content ---
    file_content = await file.read()

    # --- Validate file size ---
    if len(file_content) > MAX_FILE_SIZE:
        size_mb = MAX_FILE_SIZE // (1024 * 1024)
        return RedirectResponse(
            url=f"/projects/{project_id}?message=File+size+exceeds+{size_mb}MB+limit&type=error",
            status_code=303,
        )

    if len(file_content) == 0:
        return RedirectResponse(
            url=f"/projects/{project_id}?message=Uploaded+file+is+empty&type=error",
            status_code=303,
        )

    # --- Extract text and summarize ---
    file_type = extension  # 'pdf' or 'txt'
    extracted_text = extract_text(file_content, file_type)
    summary = summarize_document(extracted_text) if extracted_text else ""

    # --- Persist document ---
    document = Document(
        original_filename=file.filename or "unnamed",
        file_type=file_type,
        file_size=len(file_content),
        file_content=file_content,
        project_id=project_id,
        uploaded_by=user.id,
        summary=summary,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    log_action(
        db,
        user.id,
        user.email,
        "upload_document",
        resource_type="document",
        resource_id=document.id,
        details=f"Uploaded '{file.filename}' to project '{project.name}'",
    )

    return RedirectResponse(
        url=f"/projects/{project_id}?message=Document+uploaded&type=success",
        status_code=303,
    )


# ---------------------------------------------------------------------------
# Download document
# ---------------------------------------------------------------------------


@router.get("/documents/{document_id}/download")
def download_document(
    document_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = require_login(request, db)
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise NotFoundException()

    # Access check via the document's project
    project = db.query(Project).filter(Project.id == document.project_id).first()
    if not project:
        raise NotFoundException()
    _check_project_access(user, project, db)

    # Determine media type
    media_type_map = {
        "pdf": "application/pdf",
        "txt": "text/plain",
    }
    media_type = media_type_map.get(document.file_type, "application/octet-stream")

    return Response(
        content=document.file_content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'inline; filename="{document.original_filename}"',
        },
    )


# ---------------------------------------------------------------------------
# Delete document
# ---------------------------------------------------------------------------


@router.post("/documents/{document_id}/delete")
def delete_document(
    document_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = require_manager_or_admin(request, db)
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise NotFoundException()

    project_id = document.project_id
    filename = document.original_filename
    db.delete(document)
    db.commit()

    log_action(
        db,
        user.id,
        user.email,
        "delete_document",
        resource_type="document",
        resource_id=document_id,
        details=f"Deleted document '{filename}' from project {project_id}",
    )

    return RedirectResponse(
        url=f"/projects/{project_id}?message=Document+deleted&type=success",
        status_code=303,
    )
