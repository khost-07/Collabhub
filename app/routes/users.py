from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config import ACCESS_TOKEN_EXPIRE_MINUTES
from app.models import get_db, User, Project, ProjectRole, Document, AuditLog
from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    require_login,
    require_admin,
    log_action,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


@router.get("/login")
def login_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user:
        return RedirectResponse(url="/dashboard", status_code=303)
    message = request.query_params.get("message", "")
    message_type = request.query_params.get("type", "info")
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "message": message,
            "message_type": message_type,
        },
    )


@router.post("/login")
async def login_post(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    email = form.get("email", "").strip().lower()
    password = form.get("password", "")

    if not email or not password:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "message": "Email and password are required.",
                "message_type": "error",
            },
        )

    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "message": "Invalid email or password.",
                "message_type": "error",
            },
        )

    token = create_access_token({"sub": str(user.id), "role": user.role})
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    log_action(db, user.id, user.email, "login", resource_type="user", resource_id=user.id)

    return response


# ---------------------------------------------------------------------------
# Signup
# ---------------------------------------------------------------------------


@router.get("/signup")
def signup_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user:
        return RedirectResponse(url="/dashboard", status_code=303)
    message = request.query_params.get("message", "")
    message_type = request.query_params.get("type", "info")
    return templates.TemplateResponse(
        "signup.html",
        {
            "request": request,
            "message": message,
            "message_type": message_type,
        },
    )


@router.post("/signup")
async def signup_post(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    name = form.get("name", "").strip()
    email = form.get("email", "").strip().lower()
    password = form.get("password", "")
    confirm_password = form.get("confirm_password", "")

    # Validation
    if not name or not email or not password or not confirm_password:
        return templates.TemplateResponse(
            "signup.html",
            {
                "request": request,
                "message": "All fields are required.",
                "message_type": "error",
            },
        )

    if password != confirm_password:
        return templates.TemplateResponse(
            "signup.html",
            {
                "request": request,
                "message": "Passwords do not match.",
                "message_type": "error",
            },
        )

    if len(password) < 6:
        return templates.TemplateResponse(
            "signup.html",
            {
                "request": request,
                "message": "Password must be at least 6 characters.",
                "message_type": "error",
            },
        )

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return templates.TemplateResponse(
            "signup.html",
            {
                "request": request,
                "message": "An account with this email already exists.",
                "message_type": "error",
            },
        )

    # CRITICAL: always set role to 'member' — ignore any client input
    new_user = User(
        name=name,
        email=email,
        hashed_password=hash_password(password),
        role="guest",
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    log_action(
        db,
        new_user.id,
        new_user.email,
        "signup",
        resource_type="user",
        resource_id=new_user.id,
    )

    return RedirectResponse(
        url="/login?message=Account+created+successfully&type=success",
        status_code=303,
    )


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


@router.get("/logout")
def logout(request: Request):
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="access_token")
    return response


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)

    stats: dict = {}
    if user.role == "admin":
        stats["projects"] = db.query(func.count(Project.id)).scalar() or 0
        stats["documents"] = db.query(func.count(Document.id)).scalar() or 0
        stats["users"] = db.query(func.count(User.id)).scalar() or 0
        stats["my_projects"] = stats["projects"]
        recent_logs = (
            db.query(AuditLog)
            .order_by(AuditLog.timestamp.desc())
            .limit(10)
            .all()
        )
    elif user.role == "manager":
        manager_projects = (
            db.query(Project).filter(Project.created_by == user.id).all()
        )
        manager_project_ids = [p.id for p in manager_projects]
        stats["projects"] = db.query(func.count(Project.id)).scalar() or 0
        stats["my_projects"] = len(manager_projects)
        stats["documents"] = (
            db.query(func.count(Document.id))
            .filter(Document.project_id.in_(manager_project_ids))
            .scalar()
            or 0
        ) if manager_project_ids else 0
        recent_logs = (
            db.query(AuditLog)
            .filter(AuditLog.user_id == user.id)
            .order_by(AuditLog.timestamp.desc())
            .limit(10)
            .all()
        )
    else:
        # member, developer, or guest
        member_project_ids = [
            row.project_id
            for row in db.query(ProjectRole.project_id)
            .filter(ProjectRole.role == user.role)
            .all()
        ]
        stats["projects"] = db.query(func.count(Project.id)).scalar() or 0
        stats["my_projects"] = len(member_project_ids)
        stats["documents"] = (
            db.query(func.count(Document.id))
            .filter(Document.project_id.in_(member_project_ids))
            .scalar()
            or 0
        ) if member_project_ids else 0
        recent_logs = (
            db.query(AuditLog)
            .filter(AuditLog.user_id == user.id)
            .order_by(AuditLog.timestamp.desc())
            .limit(10)
            .all()
        )

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "stats": stats,
            "recent_logs": recent_logs,
        },
    )


# ---------------------------------------------------------------------------
# User management (admin only)
# ---------------------------------------------------------------------------


@router.get("/users")
def list_users(request: Request, db: Session = Depends(get_db)):
    user = require_admin(request, db)
    users = db.query(User).order_by(User.created_at.desc()).all()
    message = request.query_params.get("message", "")
    message_type = request.query_params.get("type", "info")
    return templates.TemplateResponse(
        "users/list.html",
        {
            "request": request,
            "user": user,
            "users": users,
            "message": message,
            "message_type": message_type,
        },
    )


@router.post("/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    admin_user = require_admin(request, db)
    form = await request.form()
    new_role = form.get("role", "").strip()

    if new_role not in ("admin", "manager", "senior_developer", "junior_developer", "member", "guest"):
        return RedirectResponse(
            url="/users?message=Invalid+role&type=error",
            status_code=303,
        )

    if user_id == admin_user.id:
        return RedirectResponse(
            url="/users?message=Cannot+change+your+own+role&type=error",
            status_code=303,
        )

    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        return RedirectResponse(
            url="/users?message=User+not+found&type=error",
            status_code=303,
        )

    old_role = target_user.role
    target_user.role = new_role
    db.commit()

    log_action(
        db,
        admin_user.id,
        admin_user.email,
        "role_change",
        resource_type="user",
        resource_id=target_user.id,
        details=f"Changed role from '{old_role}' to '{new_role}' for {target_user.email}",
    )

    return RedirectResponse(
        url="/users?message=Role+updated&type=success",
        status_code=303,
    )


# ---------------------------------------------------------------------------
# Audit log (admin only)
# ---------------------------------------------------------------------------


@router.get("/audit")
def list_audit_logs(request: Request, db: Session = Depends(get_db)):
    user = require_admin(request, db)
    logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).all()
    return templates.TemplateResponse(
        "audit/log.html",
        {
            "request": request,
            "user": user,
            "logs": logs,
        },
    )

