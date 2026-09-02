"""FastAPI application entry point for the EARL workshop portal."""

from __future__ import annotations

import secrets
import shlex
from collections.abc import Generator
from dataclasses import replace
from mimetypes import guess_type
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlsplit

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from . import __version__
from .auth import (
    authenticate_user,
    csrf_token,
    current_user,
    establish_session,
    invalidate_session,
    require_authenticated_user,
    require_role,
    validate_csrf,
)
from .config import Settings
from .course import CoursePage, Workshop, load_workshop
from .credentials import VMEncryptionError, attendee_connection, validate_vm_encryption_key
from .db import (
    User,
    UserRole,
    completed_page_ids,
    create_engine,
    create_session_factory,
    initialize_database,
    set_page_completion,
)

# The canonical brand entry points are committed local assets. The SVG and PNG both use
# the supplied City & Guilds lion artwork; no network or runtime asset generation is needed.
BRAND_LOGO_NAME = "logo.svg"
BRAND_FAVICON_NAME = "favicon.png"


def _brand_asset_url(asset_dir: Path, name: str) -> str:
    if (asset_dir / name).is_file():
        return f"/assets/{name}"
    return ""


def _template_context(
    request: Request,
    *,
    settings: Settings,
    workshop: Workshop,
    user: User | None = None,
) -> dict[str, object]:
    safe_user = (
        {"username": user.username, "role": user.role}
        if user is not None
        else None
    )
    return {
        "request": request,
        "workshop": workshop,
        "version": __version__,
        "current_user": safe_user,
        "course_index": False,
        "completed_page_ids": set(),
        "progress_summary": {"completed": 0, "total": len(workshop.pages), "percentage": 0},
        "csrf_token": csrf_token(request),
        "brand_logo_url": _brand_asset_url(settings.asset_dir, BRAND_LOGO_NAME),
        "favicon_url": _brand_asset_url(settings.asset_dir, BRAND_FAVICON_NAME),
    }


def get_db(request: Request) -> Generator[Session]:
    """Provide one short-lived database session per request."""

    with request.app.state.session_factory() as session:
        yield session


def _safe_next_path(next_path: str | None) -> str:
    """Keep login redirects on this site and avoid an open redirect."""

    if (
        next_path
        and next_path.startswith("/")
        and not next_path.startswith("//")
        and "\\" not in next_path
        and not urlsplit(next_path).scheme
        and not urlsplit(next_path).netloc
    ):
        return next_path
    return "/"


def _safe_resource_path(
    resources_dir: Path, resource_path: str, declared_resources: frozenset[str]
) -> Path | None:
    """Resolve one declared resource without allowing path escape or symlink escape."""

    if (
        not resource_path
        or "\x00" in resource_path
        or "\\" in resource_path
        or resource_path.startswith("/")
        or (len(resource_path) >= 3 and resource_path[1:3] == ":/")
        or resource_path not in declared_resources
    ):
        return None
    parts = resource_path.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        return None

    try:
        root = resources_dir.resolve()
        candidate = (root / PurePosixPath(resource_path)).resolve()
    except (OSError, RuntimeError):
        return None
    try:
        candidate.relative_to(root)
        available = candidate.is_file()
    except (OSError, ValueError):
        return None
    return candidate if available else None


def _resource_url(request: Request, settings: Settings, resource_file: str) -> str:
    """Build a stable browser URL from the configured public base or request origin."""

    base_url = (settings.public_base_url or str(request.base_url)).rstrip("/")
    return f"{base_url}/resources/{quote(resource_file, safe='/')}"


def _progress_context(db: Session, user: User, workshop: Workshop) -> dict[str, object]:
    """Return current-content progress only, ignoring records for removed page IDs."""

    page_ids = tuple(page.id for page in workshop.pages)
    completed_ids = completed_page_ids(db, attendee_id=user.id, page_ids=page_ids)
    total = len(page_ids)
    completed = len(completed_ids)
    percentage = round((completed / total) * 100) if total else 0
    return {
        "completed_page_ids": completed_ids,
        "progress_summary": {
            "completed": completed,
            "total": total,
            "percentage": percentage,
        },
    }


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or Settings.from_env()
    runtime_settings = replace(
        runtime_settings,
        vm_encryption_key=validate_vm_encryption_key(runtime_settings.vm_encryption_key),
    )
    if not runtime_settings.session_secret:
        if runtime_settings.environment.strip().lower() in {"production", "prod"}:
            raise ValueError(
                "A session secret is required in production; set EARL_WORKSHOP_SESSION_SECRET"
            )
        # Development and tests still get signed sessions, but an unconfigured process does
        # not accidentally reuse a predictable secret across deployments.
        runtime_settings = replace(runtime_settings, session_secret=secrets.token_urlsafe(32))

    workshop = load_workshop(runtime_settings.content_dir)
    declared_resource_files = frozenset(
        resource.file for page in workshop.pages for resource in page.resources
    )
    app = FastAPI(title=workshop.title, version=__version__)
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    app.state.settings = runtime_settings
    app.state.workshop = workshop
    app.state.engine = create_engine(runtime_settings.resolved_database_path)
    initialize_database(app.state.engine)
    app.state.session_factory = create_session_factory(app.state.engine)
    app.add_middleware(
        SessionMiddleware,
        secret_key=runtime_settings.session_secret,
        session_cookie="earl_workshop_session",
        max_age=8 * 60 * 60,
        same_site="lax",
        https_only=runtime_settings.secure_cookies,
    )

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get(f"/assets/{BRAND_LOGO_NAME}", include_in_schema=False)
    async def brand_logo() -> FileResponse:
        return FileResponse(
            runtime_settings.asset_dir / BRAND_LOGO_NAME, media_type="image/svg+xml"
        )

    @app.get(f"/assets/{BRAND_FAVICON_NAME}", include_in_schema=False)
    async def brand_favicon() -> FileResponse:
        return FileResponse(runtime_settings.asset_dir / BRAND_FAVICON_NAME, media_type="image/png")

    app.mount("/assets", StaticFiles(directory=runtime_settings.asset_dir), name="assets")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    def _attendee_dashboard_response(request: Request, db: Session, user: User) -> Response:
        context = _template_context(
            request, settings=runtime_settings, workshop=workshop, user=user
        )
        try:
            context["vm_connection"] = attendee_connection(
                db,
                attendee_id=user.id,
                encryption_key=runtime_settings.vm_encryption_key,
            )
        except VMEncryptionError:
            # Never render ciphertext or a partially decrypted credential. The generic
            # message is intentionally safe for both browser output and application logs.
            context["credential_error"] = (
                "Your VM connection details are temporarily unavailable. Please contact the "
                "workshop team."
            )
            return templates.TemplateResponse(
                request=request,
                name="attendee.html",
                context=context,
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return templates.TemplateResponse(request=request, name="attendee.html", context=context)

    @app.get("/", response_class=HTMLResponse)
    async def landing_page(
        request: Request, db: Session = Depends(get_db)
    ) -> HTMLResponse:
        user = current_user(db, request)
        context = _template_context(
            request, settings=runtime_settings, workshop=workshop, user=user
        )
        return templates.TemplateResponse(request=request, name="index.html", context=context)

    @app.get("/course", response_class=HTMLResponse)
    async def course_index(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
        user = require_authenticated_user(db, request)
        context = _template_context(
            request, settings=runtime_settings, workshop=workshop, user=user
        )
        context["course_index"] = True
        context.update(_progress_context(db, user, workshop))
        return templates.TemplateResponse(request=request, name="index.html", context=context)

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(
        request: Request,
        next_path: str | None = Query(default=None, alias="next"),
        db: Session = Depends(get_db),
    ) -> Response:
        user = current_user(db, request)
        if user is not None:
            return RedirectResponse(
                url=_safe_next_path(next_path), status_code=status.HTTP_303_SEE_OTHER
            )
        context = _template_context(request, settings=runtime_settings, workshop=workshop)
        context["next_path"] = _safe_next_path(next_path)
        return templates.TemplateResponse(request=request, name="login.html", context=context)

    @app.post("/login", response_class=HTMLResponse)
    async def login_submit(
        request: Request,
        username: str = Form(default=""),
        password: str = Form(default=""),
        submitted_csrf_token: str = Form(default="", alias="csrf_token"),
        next_path: str = Form(default="/"),
        db: Session = Depends(get_db),
    ) -> Response:
        validate_csrf(request, submitted_csrf_token)
        user = authenticate_user(db, username=username, password=password)
        if user is None:
            context = _template_context(request, settings=runtime_settings, workshop=workshop)
            context["next_path"] = _safe_next_path(next_path)
            context["login_error"] = "Invalid username or password"
            return templates.TemplateResponse(
                request=request, name="login.html", context=context, status_code=401
            )

        establish_session(request, db, user)
        destination = _safe_next_path(next_path)
        if destination == "/" and user.role == UserRole.ATTENDEE.value:
            destination = "/attendee"
        return RedirectResponse(url=destination, status_code=status.HTTP_303_SEE_OTHER)

    @app.post("/logout")
    async def logout(
        request: Request,
        submitted_csrf_token: str = Form(default="", alias="csrf_token"),
        db: Session = Depends(get_db),
    ) -> RedirectResponse:
        # Resolve the account before mutating the session so stale/inactive cookies are
        # invalidated through the same route as an explicit logout.
        user = current_user(db, request)
        validate_csrf(request, submitted_csrf_token)
        invalidate_session(request, db, user)
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    @app.get("/portal", response_class=HTMLResponse)
    async def portal_page(
        request: Request, db: Session = Depends(get_db)
    ) -> Response:
        user = require_authenticated_user(db, request)
        if user.role == UserRole.ATTENDEE.value:
            return _attendee_dashboard_response(request, db, user)
        context = _template_context(
            request, settings=runtime_settings, workshop=workshop, user=user
        )
        return templates.TemplateResponse(request=request, name="portal.html", context=context)

    @app.get("/admin", response_class=HTMLResponse)
    @app.get("/admin/protected", response_class=HTMLResponse)
    async def admin_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
        user = require_role(db, request, UserRole.ADMIN)
        context = _template_context(
            request, settings=runtime_settings, workshop=workshop, user=user
        )
        return templates.TemplateResponse(request=request, name="admin.html", context=context)

    @app.get("/attendee", response_class=HTMLResponse)
    async def attendee_page(request: Request, db: Session = Depends(get_db)) -> Response:
        user = require_role(db, request, UserRole.ATTENDEE)
        return _attendee_dashboard_response(request, db, user)

    @app.get("/resources/{resource_path:path}", name="public_resource")
    async def public_resource(resource_path: str) -> FileResponse:
        """Serve only declared, existing files beneath the configured resource root."""

        candidate = _safe_resource_path(
            runtime_settings.resources_dir, resource_path, declared_resource_files
        )
        if candidate is None:
            raise HTTPException(status_code=404, detail="Resource not found")
        return FileResponse(
            candidate,
            filename=candidate.name,
            media_type=guess_type(candidate.name)[0] or "application/octet-stream",
        )

    @app.get("/course/{page_id}", response_class=HTMLResponse)
    async def course_page(
        request: Request, page_id: str, db: Session = Depends(get_db)
    ) -> HTMLResponse:
        user = require_authenticated_user(db, request)
        page = next((candidate for candidate in workshop.pages if candidate.id == page_id), None)
        if page is None:
            raise HTTPException(status_code=404, detail="Course page not found")
        context = _template_context(
            request, settings=runtime_settings, workshop=workshop, user=user
        )
        context.update(_progress_context(db, user, workshop))
        context["page"] = page
        context["page_index"] = workshop.pages.index(page)
        context["page_complete"] = page.id in context["completed_page_ids"]
        resource_links = []
        for resource in page.resources:
            resource_url = _resource_url(request, runtime_settings, resource.file)
            resource_links.append(
                {
                    "label": resource.label,
                    "file": resource.file,
                    "url": resource_url,
                    "curl_command": f"curl -fL {shlex.quote(resource_url)}",
                    "available": _safe_resource_path(
                        runtime_settings.resources_dir,
                        resource.file,
                        declared_resource_files,
                    )
                    is not None,
                }
            )
        context["resource_links"] = resource_links
        context["previous_page"] = _neighbour(workshop, page, offset=-1)
        context["next_page"] = _neighbour(workshop, page, offset=1)
        return templates.TemplateResponse(request=request, name="course_page.html", context=context)

    @app.post("/course/{page_id}/completion")
    async def update_course_completion(
        request: Request,
        page_id: str,
        completed: str = Form(default="false"),
        submitted_csrf_token: str = Form(default="", alias="csrf_token"),
        db: Session = Depends(get_db),
    ) -> RedirectResponse:
        user = require_authenticated_user(db, request)
        validate_csrf(request, submitted_csrf_token)
        page = next((candidate for candidate in workshop.pages if candidate.id == page_id), None)
        if page is None:
            raise HTTPException(status_code=404, detail="Course page not found")

        normalized_completed = completed.strip().casefold()
        if normalized_completed in {"1", "true", "on", "yes"}:
            is_completed = True
        elif normalized_completed in {"0", "false", "off", "no", ""}:
            is_completed = False
        else:
            raise HTTPException(status_code=400, detail="Invalid completion state")
        set_page_completion(
            db,
            attendee_id=user.id,
            page_id=page.id,
            completed=is_completed,
        )
        return RedirectResponse(
            url=f"/course/{page.id}", status_code=status.HTTP_303_SEE_OTHER
        )

    return app


def _neighbour(workshop: Workshop, page: CoursePage, *, offset: int) -> CoursePage | None:
    page_index = workshop.pages.index(page) + offset
    if 0 <= page_index < len(workshop.pages):
        return workshop.pages[page_index]
    return None


def _configuration_error_app() -> FastAPI:
    """Keep module imports safe while making an unconfigured deployment non-operational."""

    unavailable_app = FastAPI(title="EARL Workshop Portal")

    @unavailable_app.get("/healthz")
    async def unavailable_healthz() -> Response:
        return Response(
            content='{"status":"unavailable"}',
            media_type="application/json",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    @unavailable_app.api_route(
        "/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    )
    async def unavailable_route() -> Response:
        return Response(
            content="Application configuration is unavailable.",
            media_type="text/plain",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return unavailable_app


try:
    app = create_app()
except VMEncryptionError:
    # ``uvicorn earl_workshop.main:app`` remains importable for operators, but no request
    # can reach application functionality until the dedicated key is configured.
    app = _configuration_error_app()
