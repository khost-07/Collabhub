from datetime import datetime, timedelta
from typing import Optional

from fastapi import Request
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from app.models import User, AuditLog


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Return a bcrypt hash of the given plain-text password."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against its bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------


def create_access_token(data: dict) -> str:
    """Create a signed JWT containing *sub* (user id), *role*, and *exp*."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(request: Request, db: Session) -> Optional[User]:
    """
    Read the ``access_token`` cookie, decode the JWT, and return the
    corresponding :class:`User`, or ``None`` when the token is missing /
    invalid / the user no longer exists.
    """
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: Optional[str] = payload.get("sub")
        if user_id is None:
            return None
        user = db.query(User).filter(User.id == int(user_id)).first()
        return user
    except (JWTError, ValueError, Exception):
        return None


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class RequiresLoginException(Exception):
    """Raised when an unauthenticated user accesses a protected resource."""
    pass


class NotAuthorizedException(Exception):
    """Raised when an authenticated user lacks the required role."""

    def __init__(self, detail: str = "You do not have permission to access this resource."):
        self.detail = detail
        super().__init__(self.detail)


class NotFoundException(Exception):
    """Raised when a requested resource does not exist."""
    pass


# ---------------------------------------------------------------------------
# Route-level auth helpers
# ---------------------------------------------------------------------------


def require_login(request: Request, db: Session) -> User:
    """Return the current user or raise :class:`RequiresLoginException`."""
    user = get_current_user(request, db)
    if user is None:
        raise RequiresLoginException()
    return user


def require_admin(request: Request, db: Session) -> User:
    """Return the current user if they are an admin, otherwise raise."""
    user = require_login(request, db)
    if user.role != "admin":
        raise NotAuthorizedException("Only administrators can perform this action.")
    return user


def require_manager_or_admin(request: Request, db: Session) -> User:
    """Return the current user if they are an admin or manager, otherwise raise."""
    user = require_login(request, db)
    if user.role not in ("admin", "manager"):
        raise NotAuthorizedException(
            "Only managers and administrators can perform this action."
        )
    return user


# ---------------------------------------------------------------------------
# Audit logging helper
# ---------------------------------------------------------------------------


def log_action(
    db: Session,
    user_id: Optional[int],
    user_email: str,
    action: str,
    resource_type: str = "",
    resource_id: Optional[int] = None,
    details: str = "",
) -> None:
    """Persist an audit-log entry."""
    org_id = None
    if user_id:
        from app.models import User
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            org_id = user.organization_id

    entry = AuditLog(
        user_id=user_id,
        user_email=user_email,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        organization_id=org_id,
    )
    db.add(entry)
    db.commit()
