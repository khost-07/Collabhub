from datetime import datetime

from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from app.models import get_db, Project, ProjectRole, User, Document
from app.auth import (
    require_login,
    require_manager_or_admin,
    NotAuthorizedException,
    NotFoundException,
    log_action,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

AVAILABLE_ROLES = [
    {"id": "admin", "name": "Admin"},
    {"id": "manager", "name": "Manager"},
    {"id": "senior_developer", "name": "Senior Developer"},
    {"id": "junior_developer", "name": "Junior Developer"},
    {"id": "member", "name": "Member"},
    {"id": "guest", "name": "Guest"},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_project_access(user, project, db: Session) -> None:
    """Raise NotAuthorizedException if user cannot view this project."""
    if project.organization_id != user.organization_id:
        raise NotAuthorizedException("You do not have access to this project.")

    if user.role == "admin":
        return

    # Managers always have access to projects they created
    if user.role == "manager" and project.created_by == user.id:
        return

    # Otherwise, check if their role is in the allowed roles for this project
    is_allowed = (
        db.query(ProjectRole)
        .filter(
            ProjectRole.project_id == project.id,
            ProjectRole.role == user.role,
        )
        .first()
    )
    if not is_allowed:
        raise NotAuthorizedException("Your role does not have access to this project.")


# ---------------------------------------------------------------------------
# List projects
# ---------------------------------------------------------------------------


@router.get("/projects")
def list_projects(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    message = request.query_params.get("message", "")
    message_type = request.query_params.get("type", "info")

    if user.role == "admin":
        projects = (
            db.query(Project)
            .options(joinedload(Project.creator))
            .filter(Project.organization_id == user.organization_id)
            .order_by(Project.created_at.desc())
            .all()
        )
    elif user.role == "manager":
        # Managers see all projects they created, plus any projects explicitly allowing 'manager' role
        allowed_project_ids = (
            db.query(ProjectRole.project_id)
            .filter(ProjectRole.role == "manager")
            .subquery()
        )
        projects = (
            db.query(Project)
            .options(joinedload(Project.creator))
            .filter(Project.organization_id == user.organization_id)
            .filter((Project.created_by == user.id) | Project.id.in_(allowed_project_ids))
            .order_by(Project.created_at.desc())
            .all()
        )
    else:
        # Others see projects explicitly allowing their role
        role_project_ids = (
            db.query(ProjectRole.project_id)
            .filter(ProjectRole.role == user.role)
            .subquery()
        )
        projects = (
            db.query(Project)
            .options(joinedload(Project.creator))
            .filter(Project.organization_id == user.organization_id)
            .filter(Project.id.in_(role_project_ids))
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
    return templates.TemplateResponse(
        "projects/form.html",
        {
            "request": request,
            "user": user,
            "project": None,
            "available_roles": AVAILABLE_ROLES,
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
        return templates.TemplateResponse(
            "projects/form.html",
            {
                "request": request,
                "user": user,
                "project": None,
                "available_roles": AVAILABLE_ROLES,
                "message": "Project name is required.",
                "message_type": "error",
            },
        )

    project = Project(
        name=name,
        description=description,
        status=status,
        created_by=user.id,
        organization_id=user.organization_id,
    )
    db.add(project)
    db.flush()  # populate ID

    # Add default allowed roles on project creation
    db.add(ProjectRole(project_id=project.id, role="admin"))
    db.add(ProjectRole(project_id=project.id, role="manager"))
    if user.role not in ("admin", "manager"):
        db.add(ProjectRole(project_id=project.id, role=user.role))

    db.commit()

    log_action(
        db,
        user.id,
        user.email,
        "create_project",
        resource_type="project",
        resource_id=project.id,
        details=f"Created project '{name}' with default admin/manager role access",
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
            joinedload(Project.allowed_roles),
            joinedload(Project.documents).joinedload(Document.uploader),
        )
        .filter(Project.id == project_id, Project.organization_id == user.organization_id)
        .first()
    )
    if not project:
        raise NotFoundException()

    _check_project_access(user, project, db)

    message = request.query_params.get("message", "")
    message_type = request.query_params.get("type", "info")

    allowed_roles_list = [r.role for r in project.allowed_roles]

    return templates.TemplateResponse(
        "projects/detail.html",
        {
            "request": request,
            "user": user,
            "project": project,
            "allowed_roles": allowed_roles_list,
            "documents": project.documents,
            "available_roles": AVAILABLE_ROLES,
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
    project = db.query(Project).filter(Project.id == project_id, Project.organization_id == user.organization_id).first()
    if not project:
        raise NotFoundException()

    project_allowed_roles = [
        row.role
        for row in db.query(ProjectRole.role)
        .filter(ProjectRole.project_id == project_id)
        .all()
    ]

    return templates.TemplateResponse(
        "projects/form.html",
        {
            "request": request,
            "user": user,
            "project": project,
            "available_roles": AVAILABLE_ROLES,
            "project_allowed_roles": project_allowed_roles,
        },
    )


@router.post("/projects/{project_id}/edit")
async def update_project(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = require_manager_or_admin(request, db)
    project = db.query(Project).filter(Project.id == project_id, Project.organization_id == user.organization_id).first()
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
    project = db.query(Project).filter(Project.id == project_id, Project.organization_id == user.organization_id).first()
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
# Manage project roles
# ---------------------------------------------------------------------------


@router.post("/projects/{project_id}/roles")
async def update_project_roles(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = require_manager_or_admin(request, db)
    project = db.query(Project).filter(Project.id == project_id, Project.organization_id == user.organization_id).first()
    if not project:
        raise NotFoundException()

    form = await request.form()

    # Read selected roles from form checkboxes
    raw_roles = form.getlist("roles")
    if not raw_roles:
        single = form.get("roles")
        if single:
            raw_roles = [single]

    valid_roles_set = {role["id"] for role in AVAILABLE_ROLES}
    selected_roles = [r.strip() for r in raw_roles if r.strip() in valid_roles_set]

    # Always ensure 'admin' and 'manager' are allowed
    if "admin" not in selected_roles:
        selected_roles.append("admin")
    if "manager" not in selected_roles:
        selected_roles.append("manager")

    # Clear existing allowed roles
    db.query(ProjectRole).filter(
        ProjectRole.project_id == project_id
    ).delete(synchronize_session="fetch")

    # Insert new allowed roles
    for role_id in selected_roles:
        db.add(ProjectRole(project_id=project_id, role=role_id))
    db.commit()

    log_action(
        db,
        user.id,
        user.email,
        "update_project_roles",
        resource_type="project",
        resource_id=project_id,
        details=f"Updated allowed roles for project '{project.name}': {selected_roles}",
    )

    return RedirectResponse(
        url=f"/projects/{project_id}?message=Allowed+roles+updated&type=success",
        status_code=303,
    )
