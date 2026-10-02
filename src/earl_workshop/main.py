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
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload
from starlette.middleware.sessions import SessionMiddleware

from . import __version__
from .auth import (
    authenticate_user,
    create_user,
    csrf_token,
    current_user,
    establish_session,
    hash_password,
    invalidate_session,
    require_authenticated_user,
    require_role,
    validate_csrf,
)
from .config import Settings
from .course import CoursePage, Workshop, load_workshop
from .credentials import (
    VMEncryptionError,
    attendee_connection,
    create_vm_credential,
    get_active_assignment,
    reassign_vm_credential,
    update_vm_credential,
    validate_vm_encryption_key,
)
from .db import (
    CourseProgress,
    User,
    UserRole,
    VMAssignment,
    VMCredential,
    completed_page_ids,
    create_engine,
    create_session_factory,
    initialize_database,
    set_page_completion,
)

# The supplied JPEG is the self-contained City & Guilds lion artwork.  `logo.svg`
# references that JPEG as a nested resource, which is not reliable when the SVG is itself
# used as an <img>.  Serve the JPEG directly for the visible brand mark.
BRAND_LOGO_NAME = "cg-lion-news-cover-lion-jpg.jpg"
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
        {
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
        }
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


def _login_redirect(request: Request) -> RedirectResponse:
    """Ask a course visitor to sign in, then return to the requested page."""

    next_path = request.url.path
    if request.url.query:
        next_path += f"?{request.url.query}"
    return RedirectResponse(
        url=f"/login?next={quote(next_path, safe='')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


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


def _admin_data(db: Session, workshop: Workshop) -> dict[str, object]:
    """Load the complete current attendee and VM overview for an administrator."""

    attendees = db.scalars(
        select(User).where(User.role == UserRole.ATTENDEE.value).order_by(User.username)
    ).all()
    attendee_ids = tuple(attendee.id for attendee in attendees)
    page_ids = tuple(page.id for page in workshop.pages)

    active_assignments = db.scalars(
        select(VMAssignment)
        .options(joinedload(VMAssignment.vm_credential))
        .where(VMAssignment.active.is_(True))
    ).all()
    assignment_by_attendee = {
        assignment.attendee_id: assignment for assignment in active_assignments
    }
    assignment_by_vm = {
        assignment.vm_credential_id: assignment for assignment in active_assignments
    }

    completed_counts: dict[int, int] = {}
    last_progress: dict[int, object] = {}
    if attendee_ids and page_ids:
        completed_counts = {
            attendee_id: int(count)
            for attendee_id, count in db.execute(
                select(CourseProgress.attendee_id, func.count(CourseProgress.id))
                .where(
                    CourseProgress.attendee_id.in_(attendee_ids),
                    CourseProgress.page_id.in_(page_ids),
                    CourseProgress.completed.is_(True),
                )
                .group_by(CourseProgress.attendee_id)
            ).all()
        }
        last_progress = {
            attendee_id: timestamp
            for attendee_id, timestamp in db.execute(
                select(CourseProgress.attendee_id, func.max(CourseProgress.updated_at))
                .where(
                    CourseProgress.attendee_id.in_(attendee_ids),
                    CourseProgress.page_id.in_(page_ids),
                )
                .group_by(CourseProgress.attendee_id)
            ).all()
            if timestamp is not None
        }

    attendee_rows = [
        {
            "user": attendee,
            "assignment": assignment_by_attendee.get(attendee.id),
            "completed": completed_counts.get(attendee.id, 0),
            "total": len(page_ids),
            "last_progress": last_progress.get(attendee.id),
        }
        for attendee in attendees
    ]
    vm_credentials = db.scalars(select(VMCredential).order_by(VMCredential.id)).all()
    vm_rows = [
        {
            "credential": credential,
            "assignment": assignment_by_vm.get(credential.id),
        }
        for credential in vm_credentials
    ]
    return {
        "attendees": attendees,
        "attendee_rows": attendee_rows,
        "vm_rows": vm_rows,
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
        return FileResponse(runtime_settings.asset_dir / BRAND_LOGO_NAME, media_type="image/jpeg")

    @app.get(f"/assets/{BRAND_FAVICON_NAME}", include_in_schema=False)
    async def brand_favicon() -> FileResponse:
        return FileResponse(runtime_settings.asset_dir / BRAND_FAVICON_NAME, media_type="image/png")

    app.mount("/assets", StaticFiles(directory=runtime_settings.asset_dir), name="assets")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    def _attendee_dashboard_response(
        request: Request, db: Session, user: User, *, show_credentials: bool = False
    ) -> Response:
        context = _template_context(
            request, settings=runtime_settings, workshop=workshop, user=user
        )
        assignment = get_active_assignment(db, attendee_id=user.id)
        context["vm_assigned"] = assignment is not None
        context["show_credentials"] = show_credentials
        if not show_credentials or assignment is None:
            return templates.TemplateResponse(
                request=request, name="attendee.html", context=context
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
    async def landing_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
        user = current_user(db, request)
        context = _template_context(
            request, settings=runtime_settings, workshop=workshop, user=user
        )
        return templates.TemplateResponse(request=request, name="index.html", context=context)

    @app.get("/learn-more", response_class=HTMLResponse)
    async def learn_more_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
        user = current_user(db, request)
        context = _template_context(
            request, settings=runtime_settings, workshop=workshop, user=user
        )
        return templates.TemplateResponse(request=request, name="learn_more.html", context=context)

    @app.get("/course", response_class=HTMLResponse)
    async def course_index(request: Request, db: Session = Depends(get_db)) -> Response:
        user = current_user(db, request)
        if user is None:
            return _login_redirect(request)
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
    async def portal_page(request: Request, db: Session = Depends(get_db)) -> Response:
        user = require_authenticated_user(db, request)
        if user.role == UserRole.ATTENDEE.value:
            return _attendee_dashboard_response(request, db, user)
        context = _template_context(
            request, settings=runtime_settings, workshop=workshop, user=user
        )
        return templates.TemplateResponse(request=request, name="portal.html", context=context)

    def _admin_page_response(
        request: Request,
        db: Session,
        user: User,
        *,
        notice: str | None = None,
        error: str | None = None,
        form_values: dict[str, str] | None = None,
        response_status: int = status.HTTP_200_OK,
    ) -> Response:
        context = _template_context(
            request, settings=runtime_settings, workshop=workshop, user=user
        )
        context.update(_admin_data(db, workshop))
        context["admin_notice"] = notice
        context["admin_error"] = error
        context["admin_form_values"] = form_values or {}
        return templates.TemplateResponse(
            request=request,
            name="admin.html",
            context=context,
            status_code=response_status,
        )

    def _admin_redirect(message: str) -> RedirectResponse:
        return RedirectResponse(
            url=f"/admin?notice={quote(message, safe='')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    def _attendee_or_404(db: Session, attendee_id: int) -> User:
        attendee = db.get(User, attendee_id)
        if attendee is None or attendee.role != UserRole.ATTENDEE.value:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attendee not found")
        return attendee

    @app.get("/admin", response_class=HTMLResponse)
    @app.get("/admin/protected", response_class=HTMLResponse)
    @app.get("/admin/attendees", response_class=HTMLResponse)
    @app.get("/admin/vms", response_class=HTMLResponse)
    async def admin_page(
        request: Request,
        notice: str | None = Query(default=None),
        db: Session = Depends(get_db),
    ) -> Response:
        user = require_role(db, request, UserRole.ADMIN)
        return _admin_page_response(request, db, user, notice=notice)

    @app.post("/admin/attendees/create", response_class=HTMLResponse)
    async def create_attendee(
        request: Request,
        username: str = Form(default=""),
        password: str = Form(default=""),
        password_confirmation: str = Form(default=""),
        display_name: str = Form(default=""),
        submitted_csrf_token: str = Form(default="", alias="csrf_token"),
        db: Session = Depends(get_db),
    ) -> Response:
        admin = require_role(db, request, UserRole.ADMIN)
        validate_csrf(request, submitted_csrf_token)
        form_values = {
            "attendee_username": username,
            "attendee_display_name": display_name,
        }
        if password_confirmation and password_confirmation != password:
            return _admin_page_response(
                request,
                db,
                admin,
                error="Password confirmation does not match",
                form_values=form_values,
                response_status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            create_user(
                db,
                username=username,
                password=password,
                display_name=display_name,
                role=UserRole.ATTENDEE,
            )
        except ValueError as exc:
            db.rollback()
            message = str(exc)
            if "Username" in message or "username" in message:
                message = "Username cannot be empty" if not username.strip() else message
            return _admin_page_response(
                request,
                db,
                admin,
                error=message,
                form_values=form_values,
                response_status=status.HTTP_400_BAD_REQUEST,
            )
        except IntegrityError:
            db.rollback()
            return _admin_page_response(
                request,
                db,
                admin,
                error="That username is already in use",
                form_values=form_values,
                response_status=status.HTTP_400_BAD_REQUEST,
            )
        return _admin_redirect("Attendee account created")

    @app.post("/admin/attendees/{attendee_id}/password", response_class=HTMLResponse)
    async def replace_attendee_password(
        request: Request,
        attendee_id: int,
        password: str = Form(default=""),
        new_password: str = Form(default=""),
        password_confirmation: str = Form(default=""),
        submitted_csrf_token: str = Form(default="", alias="csrf_token"),
        db: Session = Depends(get_db),
    ) -> Response:
        admin = require_role(db, request, UserRole.ADMIN)
        validate_csrf(request, submitted_csrf_token)
        attendee = _attendee_or_404(db, attendee_id)
        replacement = new_password or password
        if password_confirmation and password_confirmation != replacement:
            return _admin_page_response(
                request,
                db,
                admin,
                error=f"Password confirmation does not match for {attendee.username}",
                response_status=status.HTTP_400_BAD_REQUEST,
            )
        if not replacement:
            return _admin_page_response(
                request,
                db,
                admin,
                error=f"Replacement password cannot be empty for {attendee.username}",
                response_status=status.HTTP_400_BAD_REQUEST,
            )
        attendee.password_hash = hash_password(replacement)
        attendee.session_version += 1
        db.commit()
        return _admin_redirect(f"Password replaced for {attendee.username}")

    @app.post("/admin/attendees/{attendee_id}/profile", response_class=HTMLResponse)
    async def update_attendee_profile(
        request: Request,
        attendee_id: int,
        display_name: str = Form(default=""),
        submitted_csrf_token: str = Form(default="", alias="csrf_token"),
        db: Session = Depends(get_db),
    ) -> Response:
        admin = require_role(db, request, UserRole.ADMIN)
        validate_csrf(request, submitted_csrf_token)
        attendee = _attendee_or_404(db, attendee_id)
        normalized_display_name = display_name.strip()
        if len(normalized_display_name) > 150:
            return _admin_page_response(
                request,
                db,
                admin,
                error="Display name cannot be longer than 150 characters",
                response_status=status.HTTP_400_BAD_REQUEST,
            )
        attendee.display_name = normalized_display_name or None
        db.commit()
        return _admin_redirect(f"Details updated for {attendee.username}")

    @app.post("/admin/attendees/{attendee_id}/status", response_class=HTMLResponse)
    async def update_attendee_status(
        request: Request,
        attendee_id: int,
        active: str = Form(default=""),
        is_active: str = Form(default=""),
        action: str = Form(default=""),
        submitted_csrf_token: str = Form(default="", alias="csrf_token"),
        db: Session = Depends(get_db),
    ) -> Response:
        admin = require_role(db, request, UserRole.ADMIN)
        validate_csrf(request, submitted_csrf_token)
        attendee = _attendee_or_404(db, attendee_id)
        requested = active or is_active or action
        normalized = requested.strip().casefold()
        if normalized in {"1", "true", "on", "yes", "activate", "active"}:
            desired_active = True
        elif normalized in {"0", "false", "off", "no", "deactivate", "inactive"}:
            desired_active = False
        else:
            return _admin_page_response(
                request,
                db,
                admin,
                error="Choose whether the attendee should be active",
                response_status=status.HTTP_400_BAD_REQUEST,
            )
        if attendee.is_active != desired_active:
            attendee.is_active = desired_active
            attendee.session_version += 1
            db.commit()
        state = "activated" if desired_active else "deactivated"
        return _admin_redirect(f"{attendee.username} {state}")

    @app.post("/admin/vms/create", response_class=HTMLResponse)
    async def create_vm(
        request: Request,
        host: str = Form(default=""),
        ssh_username: str = Form(default=""),
        ssh_password: str = Form(default=""),
        password_confirmation: str = Form(default=""),
        submitted_csrf_token: str = Form(default="", alias="csrf_token"),
        db: Session = Depends(get_db),
    ) -> Response:
        admin = require_role(db, request, UserRole.ADMIN)
        validate_csrf(request, submitted_csrf_token)
        form_values = {"vm_host": host, "vm_ssh_username": ssh_username}
        if password_confirmation and password_confirmation != ssh_password:
            return _admin_page_response(
                request,
                db,
                admin,
                error="VM password confirmation does not match",
                form_values=form_values,
                response_status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            create_vm_credential(
                db,
                host=host,
                ssh_username=ssh_username,
                ssh_password=ssh_password,
                encryption_key=runtime_settings.vm_encryption_key,
            )
        except ValueError as exc:
            db.rollback()
            return _admin_page_response(
                request,
                db,
                admin,
                error=str(exc),
                form_values=form_values,
                response_status=status.HTTP_400_BAD_REQUEST,
            )
        return _admin_redirect("VM credential created")

    @app.post("/admin/vms/{vm_credential_id}/edit", response_class=HTMLResponse)
    async def edit_vm(
        request: Request,
        vm_credential_id: int,
        host: str = Form(default=""),
        ssh_username: str = Form(default=""),
        ssh_password: str = Form(default=""),
        password: str = Form(default=""),
        password_confirmation: str = Form(default=""),
        submitted_csrf_token: str = Form(default="", alias="csrf_token"),
        db: Session = Depends(get_db),
    ) -> Response:
        admin = require_role(db, request, UserRole.ADMIN)
        validate_csrf(request, submitted_csrf_token)
        credential = db.get(VMCredential, vm_credential_id)
        if credential is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="VM credential not found"
            )
        replacement = ssh_password or password
        form_values = {"vm_host": host, "vm_ssh_username": ssh_username}
        if password_confirmation and password_confirmation != replacement:
            return _admin_page_response(
                request,
                db,
                admin,
                error="VM password confirmation does not match",
                form_values=form_values,
                response_status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            update_vm_credential(
                db,
                vm_credential_id=vm_credential_id,
                host=host,
                ssh_username=ssh_username,
                ssh_password=replacement or None,
                encryption_key=runtime_settings.vm_encryption_key,
            )
        except ValueError as exc:
            db.rollback()
            return _admin_page_response(
                request,
                db,
                admin,
                error=str(exc),
                form_values=form_values,
                response_status=status.HTTP_400_BAD_REQUEST,
            )
        return _admin_redirect("VM credential updated")

    @app.post("/admin/vms/{vm_credential_id}/assignment", response_class=HTMLResponse)
    async def assign_vm(
        request: Request,
        vm_credential_id: int,
        attendee_id: str = Form(default=""),
        assigned_attendee_id: str = Form(default=""),
        submitted_csrf_token: str = Form(default="", alias="csrf_token"),
        db: Session = Depends(get_db),
    ) -> Response:
        admin = require_role(db, request, UserRole.ADMIN)
        validate_csrf(request, submitted_csrf_token)
        selected_attendee_id = attendee_id or assigned_attendee_id
        try:
            target_id = int(selected_attendee_id) if selected_attendee_id.strip() else None
        except ValueError:
            return _admin_page_response(
                request,
                db,
                admin,
                error="Select a valid attendee for the VM assignment",
                response_status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            reassign_vm_credential(db, vm_credential_id=vm_credential_id, attendee_id=target_id)
        except ValueError as exc:
            db.rollback()
            return _admin_page_response(
                request,
                db,
                admin,
                error=str(exc),
                response_status=status.HTTP_400_BAD_REQUEST,
            )
        if target_id is None:
            return _admin_redirect("VM credential unassigned")
        target = db.get(User, target_id)
        target_name = target.username if target is not None else "attendee"
        return _admin_redirect(f"VM credential assigned to {target_name}")

    @app.get("/attendee", response_class=HTMLResponse)
    async def attendee_page(
        request: Request,
        show_credentials: bool = Query(default=False),
        db: Session = Depends(get_db),
    ) -> Response:
        user = require_role(db, request, UserRole.ATTENDEE)
        return _attendee_dashboard_response(request, db, user, show_credentials=show_credentials)

    @app.get("/attendee/credentials/password", response_class=PlainTextResponse)
    async def attendee_vm_password(
        request: Request, db: Session = Depends(get_db)
    ) -> PlainTextResponse:
        """Return an attendee's password only in response to their copy action."""

        user = require_role(db, request, UserRole.ATTENDEE)
        try:
            connection = attendee_connection(
                db,
                attendee_id=user.id,
                encryption_key=runtime_settings.vm_encryption_key,
            )
        except VMEncryptionError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="VM credentials are temporarily unavailable",
            ) from exc
        if connection is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="VM not assigned")
        return PlainTextResponse(
            connection.ssh_password,
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )

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
    ) -> Response:
        user = current_user(db, request)
        if user is None:
            return _login_redirect(request)
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
        return RedirectResponse(url=f"/course/{page.id}", status_code=status.HTTP_303_SEE_OTHER)

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
