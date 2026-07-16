import logging

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response as StarletteResponse

from app.models import init_db
from app.auth import RequiresLoginException, NotAuthorizedException, NotFoundException
from app.routes import users, projects, documents, ai

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(title="CollabHub", docs_url=None, redoc_url=None)

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="app/templates")

# Include routers
app.include_router(users.router)
app.include_router(projects.router)
app.include_router(documents.router)
app.include_router(ai.router)


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------


@app.on_event("startup")
def on_startup():
    """Create database tables on application start."""
    init_db()
    logger.info("CollabHub database initialized.")


# ---------------------------------------------------------------------------
# Root redirect
# ---------------------------------------------------------------------------


@app.get("/")
def root():
    return RedirectResponse(url="/dashboard", status_code=303)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(RequiresLoginException)
async def requires_login_handler(request: Request, exc: RequiresLoginException):
    return RedirectResponse(
        url="/login?message=Please+log+in+to+continue&type=error",
        status_code=303,
    )


@app.exception_handler(NotAuthorizedException)
async def not_authorized_handler(request: Request, exc: NotAuthorizedException):
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "user": None,
            "error": "Access Denied",
            "message": exc.detail,
        },
        status_code=403,
    )


@app.exception_handler(NotFoundException)
async def not_found_handler(request: Request, exc: NotFoundException):
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "user": None,
            "error": "Not Found",
            "message": "The requested resource was not found.",
        },
        status_code=404,
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled server error")
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "user": None,
            "error": "Server Error",
            "message": "An unexpected error occurred.",
        },
        status_code=500,
    )


# ---------------------------------------------------------------------------
# Security headers middleware
# ---------------------------------------------------------------------------


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject security-related HTTP headers into every response."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> StarletteResponse:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        return response


app.add_middleware(SecurityHeadersMiddleware)
