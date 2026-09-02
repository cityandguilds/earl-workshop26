"""FastAPI application entry point for the EARL workshop foundation."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import __version__
from .config import Settings
from .course import CoursePage, Workshop, load_workshop


def _asset_url(asset_dir: Path, name: str) -> str:
    requested = asset_dir / name
    if requested.is_file():
        return f"/assets/{name}"
    fallback = asset_dir / "cg-lion-news-cover-lion-jpg.jpg"
    if fallback.is_file():
        return f"/assets/{fallback.name}"
    return ""


def _template_context(
    request: Request, *, settings: Settings, workshop: Workshop
) -> dict[str, object]:
    return {
        "request": request,
        "settings": settings,
        "workshop": workshop,
        "version": __version__,
        "brand_logo_url": _asset_url(settings.asset_dir, "logo.svg"),
        "favicon_url": _asset_url(settings.asset_dir, "favicon.png"),
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
