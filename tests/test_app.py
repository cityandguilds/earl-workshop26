from pathlib import Path

from fastapi.testclient import TestClient

from earl_workshop.config import Settings
from earl_workshop.main import create_app


def test_settings_read_runtime_values_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("EARL_WORKSHOP_HOST", "0.0.0.0")
    monkeypatch.setenv("EARL_WORKSHOP_PORT", "8123")
    monkeypatch.setenv("EARL_WORKSHOP_PUBLIC_BASE_URL", "https://workshop.example/portal/")
    monkeypatch.setenv("EARL_WORKSHOP_SECURE_COOKIES", "true")

    settings = Settings.from_env()

    assert settings.host == "0.0.0.0"
    assert settings.port == 8123
    assert settings.public_base_url == "https://workshop.example/portal"
    assert settings.secure_cookies is True


def test_health_and_branded_landing_page(tmp_path: Path) -> None:
    settings = Settings(
        root_dir=Path("."),
        content_dir=Path("content"),
        resources_dir=Path("resources"),
        asset_dir=Path("assets"),
        data_dir=tmp_path / "runtime-data",
        session_secret="test-session-secret-which-is-long-enough",
    )
    client = TestClient(create_app(settings))

    health = client.get("/healthz")
    landing = client.get("/")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert set(health.json()) == {"status"}
    assert landing.status_code == 200
    assert "Development to Deployment" in landing.text
    assert "Infrastructure for Data Teams" in landing.text
    assert "/static/site.css" in landing.text
    logo_url = "/assets/logo.svg"
    favicon_url = "/assets/favicon.png"
    assert f'<link rel="icon" href="{favicon_url}" type="image/png">' in landing.text
    assert landing.text.count(f'src="{logo_url}"') == 2

    logo = client.get(logo_url)
    favicon = client.get(favicon_url)
    assert logo.status_code == 200
    assert favicon.status_code == 200
    assert logo.headers["content-type"].startswith("image/svg+xml")
    assert favicon.headers["content-type"].startswith("image/png")
    assert logo.content.lstrip().startswith(b"<svg")
    assert favicon.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_course_page_is_rendered_from_loaded_content(tmp_path: Path) -> None:
    settings = Settings(
        root_dir=Path("."),
        content_dir=Path("content"),
        resources_dir=Path("resources"),
        asset_dir=Path("assets"),
        data_dir=tmp_path / "runtime-data",
        session_secret="test-session-secret-which-is-long-enough",
    )
    client = TestClient(create_app(settings))

    response = client.get("/course/runtime")

    assert response.status_code == 200
    assert "Describe a runnable environment" in response.text
    assert "echo &quot;hello from the workshop&quot;" in response.text
    assert client.get("/course/not-a-page").status_code == 404


def test_application_can_use_environment_style_external_content(tmp_path: Path) -> None:
    content_dir = tmp_path / "content"
    (content_dir / "pages").mkdir(parents=True)
    (content_dir / "workshop.yml").write_text(
        "title: External\nsubtitle: Content\n", encoding="utf-8"
    )
    (content_dir / "pages" / "page.md").write_text(
        "---\nid: external\ntitle: External page\norder: 1\n---\nHello\n", encoding="utf-8"
    )
    settings = Settings(
        root_dir=tmp_path,
        content_dir=content_dir,
        resources_dir=tmp_path / "resources",
        asset_dir=Path("assets"),
        data_dir=tmp_path / "data",
    )

    response = TestClient(create_app(settings)).get("/")

    assert response.status_code == 200
    assert "External" in response.text
    assert "/course/external" in response.text
