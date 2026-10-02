from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from earl_workshop.auth import create_user
from earl_workshop.config import Settings
from earl_workshop.db import UserRole
from earl_workshop.main import create_app

TEST_VM_ENCRYPTION_KEY = Fernet.generate_key().decode()


def test_settings_read_runtime_values_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("EARL_WORKSHOP_HOST", "0.0.0.0")
    monkeypatch.setenv("EARL_WORKSHOP_PORT", "8123")
    monkeypatch.setenv("EARL_WORKSHOP_PUBLIC_BASE_URL", "https://workshop.example/portal/")
    monkeypatch.setenv("EARL_WORKSHOP_SECURE_COOKIES", "true")
    monkeypatch.setenv("EARL_WORKSHOP_VM_ENCRYPTION_KEY", TEST_VM_ENCRYPTION_KEY)

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
        vm_encryption_key=TEST_VM_ENCRYPTION_KEY,
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
    assert 'href="/learn-more"' in landing.text
    logo_url = "/assets/cg-lion-news-cover-lion-jpg.jpg"
    favicon_url = "/assets/favicon.png"
    assert f'<link rel="icon" href="{favicon_url}" type="image/png">' in landing.text
    assert landing.text.count(f'src="{logo_url}"') == 2

    logo = client.get(logo_url)
    favicon = client.get(favicon_url)
    assert logo.status_code == 200
    assert favicon.status_code == 200
    assert logo.headers["content-type"].startswith("image/jpeg")
    assert favicon.headers["content-type"].startswith("image/png")
    assert logo.content.startswith(b"\xff\xd8\xff")
    assert favicon.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_learn_more_page_links_to_official_course_sites(tmp_path: Path) -> None:
    settings = Settings(
        root_dir=Path("."),
        content_dir=Path("content"),
        resources_dir=Path("resources"),
        asset_dir=Path("assets"),
        data_dir=tmp_path / "runtime-data",
        session_secret="test-session-secret-which-is-long-enough",
        vm_encryption_key=TEST_VM_ENCRYPTION_KEY,
    )
    client = TestClient(create_app(settings))

    page = client.get("/learn-more")
    assert page.status_code == 200
    assert "PeopleCert" in page.text
    assert "City &amp; Guilds" in page.text
    assert "https://www.peoplecert.org/organizations/browse-certifications" in page.text
    assert "https://www.cityandguilds.com/Home/qualifications-and-apprenticeships" in page.text
    for image_url in (
        "/static/images/peoplecert-placeholder.png",
        "/static/images/city-guilds-placeholder.png",
    ):
        assert image_url in page.text
        image = client.get(image_url)
        assert image.status_code == 200
        assert image.headers["content-type"].startswith("image/png")


def test_course_page_is_rendered_from_loaded_content(tmp_path: Path) -> None:
    settings = Settings(
        root_dir=Path("."),
        content_dir=Path("content"),
        resources_dir=Path("resources"),
        asset_dir=Path("assets"),
        data_dir=tmp_path / "runtime-data",
        session_secret="test-session-secret-which-is-long-enough",
        vm_encryption_key=TEST_VM_ENCRYPTION_KEY,
    )
    client = TestClient(create_app(settings))

    assert client.get("/course/install-software").status_code == 401
    with client.app.state.session_factory() as session:
        create_user(
            session,
            username="attendee",
            password="attendee password",
            role=UserRole.ATTENDEE,
        )
    login_page = client.get("/login")
    csrf_token = login_page.text.split('name="csrf_token" value="', 1)[1].split('"', 1)[0]
    login = client.post(
        "/login",
        data={
            "username": "attendee",
            "password": "attendee password",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert login.status_code == 303

    response = client.get("/course/install-software")

    assert response.status_code == 200
    assert "Install software on a virtual machine" in response.text
    assert "<h2>What you will learn</h2>" in response.text
    assert "sudo apt update" in response.text
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
        vm_encryption_key=TEST_VM_ENCRYPTION_KEY,
    )

    response = TestClient(create_app(settings)).get("/")

    assert response.status_code == 200
    assert "External" in response.text
    assert "/course/external" in response.text
