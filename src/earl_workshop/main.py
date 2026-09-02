"""FastAPI application entry point for the EARL workshop foundation."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import __version__
from .config import Settings
from .course import CoursePage, Workshop, load_workshop

# The canonical brand entry points are committed local assets. The SVG and PNG both use
# the supplied City & Guilds lion artwork; no network or runtime asset generation is needed.
BRAND_LOGO_NAME = "logo.svg"
BRAND_FAVICON_NAME = "favicon.png"


def _brand_asset_url(asset_dir: Path, name: str) -> str:
    if (asset_dir / name).is_file():
        return f"/assets/{name}"
    return ""


def _template_context(
    request: Request, *, settings: Settings, workshop: Workshop
) -> dict[str, object]:
    return {
        "request": request,
        "settings": settings,
        "workshop": workshop,
        "version": __version__,
        "brand_logo_url": _brand_asset_url(settings.asset_dir, BRAND_LOGO_NAME),
        "favicon_url": _brand_asset_url(settings.asset_dir, BRAND_FAVICON_NAME),
    }


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or Settings.from_env()
    workshop = load_workshop(runtime_settings.content_dir)
    app = FastAPI(title=workshop.title, version=__version__)
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    app.state.settings = runtime_settings
    app.state.workshop = workshop

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
