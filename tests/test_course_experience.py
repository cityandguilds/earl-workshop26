import re
from dataclasses import replace
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select

from earl_workshop.auth import create_user
from earl_workshop.config import Settings
from earl_workshop.course import load_workshop
from earl_workshop.db import CourseProgress, User, UserRole
from earl_workshop.main import create_app

CSRF_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')
TEST_VM_ENCRYPTION_KEY = Fernet.generate_key().decode()


def settings_for(tmp_path: Path, *, public_base_url: str = "") -> Settings:
    return Settings(
        root_dir=Path("."),
        content_dir=Path("content"),
        resources_dir=Path("resources"),
        asset_dir=Path("assets"),
        data_dir=tmp_path / "runtime-data",
        public_base_url=public_base_url,
        session_secret="test-session-secret-which-is-long-enough",
        vm_encryption_key=TEST_VM_ENCRYPTION_KEY,
    )


def csrf_from(response) -> str:
    token = CSRF_PATTERN.search(response.text)
    assert token is not None
    return token.group(1)


def add_attendee(app, username: str, password: str) -> User:
    with app.state.session_factory() as session:
        return create_user(
            session,
            username=username,
            password=password,
            role=UserRole.ATTENDEE,
        )


def login(client: TestClient, username: str, password: str) -> None:
    response = client.post(
        "/login",
        data={
            "username": username,
            "password": password,
            "csrf_token": csrf_from(client.get("/login")),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_authenticated_course_index_groups_pages_and_shows_progress(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    add_attendee(app, "attendee", "attendee password")
    client = TestClient(app, follow_redirects=False)

    assert client.get("/course").status_code == 401
    login(client, "attendee", "attendee password")

    index = client.get("/course")
    workshop = app.state.workshop
    assert index.status_code == 200
    assert '<h2 id="course-heading">Course</h2>' in index.text
    assert f"0 / {len(workshop.pages)}" in index.text
    assert index.text.index("Getting started") < index.text.index("PostgreSQL")
    assert index.text.index("Cloud computing") < index.text.index("Install software")
    for page in workshop.pages:
        assert f'href="/course/{page.id}"' in index.text

    first_page = client.get("/course/orientation")
    assert first_page.status_code == 200
    assert "Workshop learning outcomes" in first_page.text
    assert 'href="/course/cloud-computing"' in first_page.text
    assert 'href="/course"' in first_page.text
    assert 'action="/course/orientation/completion"' in first_page.text


def test_declared_resource_is_public_and_has_browser_and_curl_urls(tmp_path: Path) -> None:
    content_dir = tmp_path / "content"
    (content_dir / "pages").mkdir(parents=True)
    (content_dir / "workshop.yml").write_text("title: Resource test\n", encoding="utf-8")
    (content_dir / "pages" / "orientation.md").write_text(
        "---\nid: orientation\ntitle: Resources\norder: 1\nresources:\n"
        "  - file: examples/hello.txt\n    label: Example file\n---\nResource example.\n",
        encoding="utf-8",
    )
    app = create_app(
        replace(
            settings_for(tmp_path, public_base_url="https://workshop.example/portal"),
            content_dir=content_dir,
        )
    )
    anonymous = TestClient(app)

    resource = anonymous.get("/resources/examples/hello.txt")
    assert resource.status_code == 200
    assert resource.text.startswith("EARL 2026 workshop example resource")
    assert "attachment" in resource.headers["content-disposition"]

    add_attendee(app, "attendee", "attendee password")
    client = TestClient(app)
    login(client, "attendee", "attendee password")
    page = client.get("/course/orientation")
    assert "Page resources (1)" in page.text
    assert "https://workshop.example/portal/resources/examples/hello.txt" in page.text
    assert "curl -fL https://workshop.example/portal/resources/examples/hello.txt" in page.text


def test_resource_route_rejects_traversal_absolute_and_undeclared_paths(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    client = TestClient(app)
    paths = (
        "/resources/../.env",
        "/resources/%2e%2e/%2e%2e/etc/passwd",
        "/resources/%2e%2e%2f.env",
        "/resources/%2Fetc%2Fpasswd",
        "/resources/%2e%2e%5c.env",
        "/resources/C:%2FWindows%2Fwin.ini",
        "/resources/earl_workshop.sqlite3",
        "/resources/not-declared.txt",
    )
    assert all(client.get(path).status_code == 404 for path in paths)


def test_progress_is_isolated_persistent_uncomplete_and_stale_safe(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    app = create_app(settings)
    total = len(app.state.workshop.pages)
    attendee_a = add_attendee(app, "attendee-a", "password-a")
    add_attendee(app, "attendee-b", "password-b")
    with app.state.session_factory() as session:
        session.add(
            CourseProgress(
                attendee_id=attendee_a.id,
                page_id="removed-page",
                completed=True,
            )
        )
        session.commit()

    client_a = TestClient(app, follow_redirects=False)
    login(client_a, "attendee-a", "password-a")
    page = client_a.get("/course/orientation")
    response = client_a.post(
        "/course/orientation/completion",
        data={"csrf_token": csrf_from(page), "completed": "true"},
    )
    assert response.status_code == 303
    assert f"1 of {total} pages complete" in client_a.get("/course/orientation").text

    client_b = TestClient(app, follow_redirects=False)
    login(client_b, "attendee-b", "password-b")
    assert f"0 of {total} pages complete" in client_b.get("/course/orientation").text

    invalid = client_a.post(
        "/course/orientation/completion",
        data={"csrf_token": "invalid", "completed": "false"},
    )
    assert invalid.status_code == 400
    assert f"1 of {total} pages complete" in client_a.get("/course/orientation").text

    uncomplete = client_a.post(
        "/course/orientation/completion",
        data={"csrf_token": csrf_from(client_a.get("/course/orientation")), "completed": "false"},
    )
    assert uncomplete.status_code == 303
    assert f"<strong>0 / {total}</strong> pages complete" in client_a.get("/course").text

    restarted = create_app(settings)
    restarted_client = TestClient(restarted, follow_redirects=False)
    login(restarted_client, "attendee-a", "password-a")
    assert f"<strong>0 / {total}</strong> pages complete" in restarted_client.get("/course").text
    with restarted.state.session_factory() as session:
        records = session.scalars(
            select(CourseProgress).where(CourseProgress.attendee_id == attendee_a.id)
        ).all()
    assert {record.page_id for record in records} == {"removed-page", "orientation"}
    assert load_workshop(Path("content")).pages[0].id == "orientation"
