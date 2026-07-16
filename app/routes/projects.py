from datetime import datetime

from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from app.models import get_db, Project, ProjectMember, User, Document
from app.auth import (
    require_login,
    require_manager_or_admin,
    NotAuthorizedException,
    NotFoundException,
    log_action,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_project_access(user, project, db: Session) -> None:
    """Raise NotAuthorizedException if user cannot view this project."""
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
# List projects
# ---------------------------------------------------------------------------


@router.get("/projects")
def list_projects(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    message = request.query_params.get("message", "")
    message_type = request.query_params.get("type", "info")

    if user.role in ("admin", "manager"):
        projects = (
            db.query(Project)
            .options(joinedload(Project.creator))
            .order_by(Project.created_at.desc())
            .all()
        )
    else:
        # Members only see projects they belong to
        member_project_ids = (
            db.query(ProjectMember.project_id)
            .filter(ProjectMember.user_id == user.id)
            .subquery()
        )
        projects = (
            db.query(Project)
            .options(joinedload(Project.creator))
            .filter(Project.id.in_(member_project_ids))
            .order_by(Project.created_at.desc())
            .all()
        )

    return templates.TemplateResponse(
        "projects/list.html",
        {
            "request": request,
            "user": user,
            "projects": projects,
            "message": message,
            "message_type": message_type,
        },
    )


# ---------------------------------------------------------------------------
# Create project
# ---------------------------------------------------------------------------


@router.get("/projects/new")
def new_project_form(request: Request, db: Session = Depends(get_db)):
    user = require_manager_or_admin(request, db)
    all_users = db.query(User).order_by(User.name).all()
    return templates.TemplateResponse(
        "projects/form.html",
        {
            "request": request,
            "user": user,
            "project": None,
            "all_users": all_users,
        },
    )


@router.post("/projects")
async def create_project(request: Request, db: Session = Depends(get_db)):
    user = require_manager_or_admin(request, db)
    form = await request.form()

    name = form.get("name", "").strip()
    description = form.get("description", "").strip()
    status = form.get("status", "active").strip()

    if not name:
        all_users = db.query(User).order_by(User.name).all()
        return templates.TemplateResponse(
            "projects/form.html",
            {
                "request": request,
                "user": user,
                "project": None,
                "all_users": all_users,
                "message": "Project name is required.",
                "message_type": "error",
            },
        )

    project = Project(
        name=name,
        description=description,
        status=status,
        created_by=user.id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    log_action(
        db,
        user.id,
        user.email,
        "create_project",
        resource_type="project",
        resource_id=project.id,
        details=f"Created project '{name}'",
    )

    return RedirectResponse(
        url=f"/projects/{project.id}?message=Project+created&type=success",
        status_code=303,
    )


# ---------------------------------------------------------------------------
# View project detail
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}")
def project_detail(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = require_login(request, db)
    project = (
        db.query(Project)
        .options(
            joinedload(Project.creator),
            joinedload(Project.members),
            joinedload(Project.documents).joinedload(Document.uploader),
        )
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        raise NotFoundException()

    _check_project_access(user, project, db)

    all_users = db.query(User).order_by(User.name).all()
    message = request.query_params.get("message", "")
    message_type = request.query_params.get("type", "info")

    return templates.TemplateResponse(
        "projects/detail.html",
        {
            "request": request,
            "user": user,
            "project": project,
            "members": project.members,
            "documents": project.documents,
            "all_users": all_users,
            "message": message,
            "message_type": message_type,
        },
    )


# ---------------------------------------------------------------------------
# Edit project
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}/edit")
def edit_project_form(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = require_manager_or_admin(request, db)
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise NotFoundException()

    all_users = db.query(User).order_by(User.name).all()
    project_member_ids = [
        row.user_id
        for row in db.query(ProjectMember.user_id)
        .filter(ProjectMember.project_id == project_id)
        .all()
    ]

    return templates.TemplateResponse(
        "projects/form.html",
        {
            "request": request,
            "user": user,
            "project": project,
            "all_users": all_users,
            "project_member_ids": project_member_ids,
        },
    )


@router.post("/projects/{project_id}/edit")
async def update_project(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = require_manager_or_admin(request, db)
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise NotFoundException()

    form = await request.form()
    project.name = form.get("name", project.name).strip()
    project.description = form.get("description", project.description).strip()
    project.status = form.get("status", project.status).strip()
    project.updated_at = datetime.utcnow()
    db.commit()

    log_action(
        db,
        user.id,
        user.email,
        "update_project",
        resource_type="project",
        resource_id=project.id,
        details=f"Updated project '{project.name}'",
    )

    return RedirectResponse(
        url=f"/projects/{project_id}?message=Project+updated&type=success",
        status_code=303,
    )


# ---------------------------------------------------------------------------
# Delete project
# ---------------------------------------------------------------------------


@router.post("/projects/{project_id}/delete")
def delete_project(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = require_manager_or_admin(request, db)
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise NotFoundException()

    project_name = project.name
    db.delete(project)
    db.commit()

    log_action(
        db,
        user.id,
        user.email,
        "delete_project",
        resource_type="project",
        resource_id=project_id,
        details=f"Deleted project '{project_name}'",
    )

    return RedirectResponse(
        url="/projects?message=Project+deleted&type=success",
        status_code=303,
    )


# ---------------------------------------------------------------------------
# Manage project members
# ---------------------------------------------------------------------------


@router.post("/projects/{project_id}/members")
async def update_members(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = require_manager_or_admin(request, db)
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise NotFoundException()

    form = await request.form()

    # Handle both single value and multi-value form fields
    raw_member_ids = form.getlist("member_ids")
    if not raw_member_ids:
        # Fallback: single value
        single = form.get("member_ids")
        if single:
            raw_member_ids = [single]

    member_ids: list[int] = []
    for mid in raw_member_ids:
        try:
            member_ids.append(int(mid))
        except (ValueError, TypeError):
            continue

    # Clear existing members
    db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id
    ).delete(synchronize_session="fetch")

    # Insert new members
    for mid in member_ids:
        db.add(ProjectMember(project_id=project_id, user_id=mid))
    db.commit()

    log_action(
        db,
        user.id,
        user.email,
        "update_members",
        resource_type="project",
        resource_id=project_id,
        details=f"Updated members for project '{project.name}': {member_ids}",
    )

    return RedirectResponse(
        url=f"/projects/{project_id}?message=Members+updated&type=success",
        status_code=303,
    )
