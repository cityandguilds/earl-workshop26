"""FastAPI application entry point for the EARL workshop portal."""

from __future__ import annotations

import secrets
from collections.abc import Generator
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

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
from .db import User, UserRole, create_engine, create_session_factory, initialize_database

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


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or Settings.from_env()
    if not runtime_settings.session_secret:
        if runtime_settings.environment.strip().lower() in {"production", "prod"}:
            raise ValueError(
                "A session secret is required in production; set EARL_WORKSHOP_SESSION_SECRET"
            )
        # Development and tests still get signed sessions, but an unconfigured process does
        # not accidentally reuse a predictable secret across deployments.
        runtime_settings = replace(runtime_settings, session_secret=secrets.token_urlsafe(32))

    workshop = load_workshop(runtime_settings.content_dir)
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

    @app.get("/", response_class=HTMLResponse)
    async def landing_page(request: Request) -> HTMLResponse:
        context = _template_context(request, settings=runtime_settings, workshop=workshop)
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
        return RedirectResponse(
            url=_safe_next_path(next_path), status_code=status.HTTP_303_SEE_OTHER
        )

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
    ) -> HTMLResponse:
        user = require_authenticated_user(db, request)
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
    async def attendee_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
        user = require_role(db, request, UserRole.ATTENDEE)
        context = _template_context(
            request, settings=runtime_settings, workshop=workshop, user=user
        )
        return templates.TemplateResponse(request=request, name="portal.html", context=context)

    @app.get("/course/{page_id}", response_class=HTMLResponse)
    async def course_page(request: Request, page_id: str) -> HTMLResponse:
        page = next((candidate for candidate in workshop.pages if candidate.id == page_id), None)
        if page is None:
            raise HTTPException(status_code=404, detail="Course page not found")
        context = _template_context(request, settings=runtime_settings, workshop=workshop)
        context["page"] = page
        context["previous_page"] = _neighbour(workshop, page, offset=-1)
        context["next_page"] = _neighbour(workshop, page, offset=1)
        return templates.TemplateResponse(request=request, name="course_page.html", context=context)

    return app


def _neighbour(workshop: Workshop, page: CoursePage, *, offset: int) -> CoursePage | None:
    page_index = workshop.pages.index(page) + offset
    if 0 <= page_index < len(workshop.pages):
        return workshop.pages[page_index]
    return None


app = create_app()
