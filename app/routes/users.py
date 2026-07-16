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
from app.common_templates import templates


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
    onboard = request.query_params.get("onboard", "")
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "message": message,
            "message_type": message_type,
            "onboard": onboard,
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
    onboard = form.get("onboard", "") == "true"
    if onboard and user.role == "admin":
        response = RedirectResponse(url="/onboarding", status_code=303)
    else:
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
    org_name = form.get("org_name", "").strip()
    name = form.get("name", "").strip()
    email = form.get("email", "").strip().lower()
    password = form.get("password", "")
    confirm_password = form.get("confirm_password", "")

    # Validation
    if not org_name or not name or not email or not password or not confirm_password:
        return templates.TemplateResponse(
            "signup.html",
            {
                "request": request,
                "message": "All fields including Organization Name are required.",
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

    from app.models import Organization

    # Create Organization
    org = Organization(name=org_name)
    db.add(org)
    db.flush()  # Populate org.id

    new_user = User(
        name=name,
        email=email,
        hashed_password=hash_password(password),
        role="admin",
        organization_id=org.id,
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
        url="/login?message=Organization+registered.+Log+in+to+onboard+employees&type=success&onboard=true",
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
        stats["projects"] = db.query(func.count(Project.id)).filter(Project.organization_id == user.organization_id).scalar() or 0
        stats["documents"] = (
            db.query(func.count(Document.id))
            .join(Project)
            .filter(Project.organization_id == user.organization_id)
            .scalar() or 0
        )
        stats["users"] = db.query(func.count(User.id)).filter(User.organization_id == user.organization_id).scalar() or 0
        stats["my_projects"] = stats["projects"]
        recent_logs = (
            db.query(AuditLog)
            .filter(AuditLog.organization_id == user.organization_id)
            .order_by(AuditLog.timestamp.desc())
            .limit(10)
            .all()
        )
    elif user.role == "manager":
        manager_projects = (
            db.query(Project).filter(Project.created_by == user.id, Project.organization_id == user.organization_id).all()
        )
        manager_project_ids = [p.id for p in manager_projects]
        stats["projects"] = db.query(func.count(Project.id)).filter(Project.organization_id == user.organization_id).scalar() or 0
        stats["my_projects"] = len(manager_projects)
        stats["documents"] = (
            db.query(func.count(Document.id))
            .filter(Document.project_id.in_(manager_project_ids))
            .scalar()
            or 0
        ) if manager_project_ids else 0
        recent_logs = (
            db.query(AuditLog)
            .filter(AuditLog.user_id == user.id, AuditLog.organization_id == user.organization_id)
            .order_by(AuditLog.timestamp.desc())
            .limit(10)
            .all()
        )
    else:
        # member, developer, or guest
        member_project_ids = [
            row.project_id
            for row in db.query(ProjectRole.project_id)
            .join(Project)
            .filter(ProjectRole.role == user.role, Project.organization_id == user.organization_id)
            .all()
        ]
        stats["projects"] = db.query(func.count(Project.id)).filter(Project.organization_id == user.organization_id).scalar() or 0
        stats["my_projects"] = len(member_project_ids)
        stats["documents"] = (
            db.query(func.count(Document.id))
            .filter(Document.project_id.in_(member_project_ids))
            .scalar()
            or 0
        ) if member_project_ids else 0
        recent_logs = (
            db.query(AuditLog)
            .filter(AuditLog.user_id == user.id, AuditLog.organization_id == user.organization_id)
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
    users = db.query(User).filter(User.organization_id == user.organization_id).order_by(User.created_at.desc()).all()
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

    target_user = db.query(User).filter(User.id == user_id, User.organization_id == admin_user.organization_id).first()
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
    logs = db.query(AuditLog).filter(AuditLog.organization_id == user.organization_id).order_by(AuditLog.timestamp.desc()).all()
    return templates.TemplateResponse(
        "audit/log.html",
        {
            "request": request,
            "user": user,
            "logs": logs,
        },
    )


# ---------------------------------------------------------------------------
# Organization Onboarding (CEO only)
# ---------------------------------------------------------------------------


@router.get("/onboarding")
def onboarding_page(request: Request, db: Session = Depends(get_db)):
    user = require_admin(request, db) # CEO is admin
    message = request.query_params.get("message", "")
    message_type = request.query_params.get("type", "info")

    # Fetch all employees added so far (all users except this CEO in the same org)
    employees = db.query(User).filter(User.organization_id == user.organization_id, User.id != user.id).order_by(User.created_at.desc()).all()

    return templates.TemplateResponse(
        "onboarding.html",
        {
            "request": request,
            "user": user,
            "employees": employees,
            "message": message,
            "message_type": message_type,
        },
    )


@router.post("/onboarding/add-employee")
async def onboarding_add_employee(request: Request, db: Session = Depends(get_db)):
    user = require_admin(request, db)
    form = await request.form()

    name = form.get("name", "").strip()
    email = form.get("email", "").strip().lower()
    role = form.get("role", "").strip()
    password = form.get("password", "")

    if not name or not email or not role or not password:
        return RedirectResponse(
            url="/onboarding?message=All+fields+are+required&type=error",
            status_code=303,
        )

    if len(password) < 6:
        return RedirectResponse(
            url="/onboarding?message=Password+must+be+at+least+6+characters&type=error",
            status_code=303,
        )

    if role not in ("manager", "senior_developer", "junior_developer", "member", "guest"):
        return RedirectResponse(
            url="/onboarding?message=Invalid+role+selected&type=error",
            status_code=303,
        )

    # Check email uniqueness
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return RedirectResponse(
            url="/onboarding?message=An+account+with+this+email+already+exists&type=error",
            status_code=303,
        )

    # Create employee user
    new_employee = User(
        name=name,
        email=email,
        hashed_password=hash_password(password),
        role=role,
        organization_id=user.organization_id,
    )
    db.add(new_employee)
    db.commit()
    db.refresh(new_employee)

    log_action(
        db,
        user.id,
        user.email,
        "onboarding_add_employee",
        resource_type="user",
        resource_id=new_employee.id,
        details=f"CEO created employee {new_employee.name} ({new_employee.role}) during onboarding",
    )

    return RedirectResponse(
        url=f"/onboarding?message=Employee+{new_employee.name}+added+successfully&type=success",
        status_code=303,
    )


@router.post("/onboarding/save-api-key")
async def onboarding_save_api_key(request: Request, db: Session = Depends(get_db)):
    user = require_admin(request, db)
    form = await request.form()
    api_key = form.get("gemini_api_key", "").strip()

    user.gemini_api_key = api_key if api_key else None
    db.commit()

    log_action(
        db,
        user.id,
        user.email,
        "onboarding_save_api_key",
        resource_type="user",
        resource_id=user.id,
        details="CEO updated Gemini API key during onboarding",
    )

    return RedirectResponse(
        url="/onboarding?message=Gemini+API+Key+saved+successfully&type=success",
        status_code=303,
    )

