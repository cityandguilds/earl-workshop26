"""Browser recovery from expired and revoked sessions without replaying actions."""

import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner
from sqlalchemy import select
from test_auth import add_user, csrf_from, login, settings_for

from earl_workshop.db import CourseProgress, User, UserRole
from earl_workshop.main import create_app

COOKIE = "earl_workshop_session"
NOTICE = "Please sign in again to continue."


class ExpiredSigner(TimestampSigner):
    def get_timestamp(self) -> int:
        return int(time.time()) - 8 * 60 * 60 - 60


def expire_cookie(client: TestClient, secret: str) -> None:
    payload = TimestampSigner(secret).unsign(client.cookies.get(COOKIE))
    client.cookies.clear()
    client.cookies.set(COOKIE, ExpiredSigner(secret).sign(payload).decode())


def assert_login_redirect(response, destination: str) -> str:
    assert response.status_code == 303
    location = response.headers["location"]
    parsed = urlsplit(location)
    assert parsed.path == "/login"
    assert parse_qs(parsed.query) == {"next": [destination], "reauth": ["1"]}
    return location


@pytest.mark.parametrize("state", ["expired", "missing", "revoked", "inactive"])
def test_protected_pages_recover_all_unauthenticated_sessions(tmp_path: Path, state: str) -> None:
    settings = settings_for(tmp_path)
    app = create_app(settings)
    user = add_user(app, username="attendee", password="password", role=UserRole.ATTENDEE)
    client = TestClient(app, follow_redirects=False)
    login(client, "attendee", "password")
    if state == "expired":
        expire_cookie(client, settings.session_secret)
    elif state == "missing":
        client.cookies.clear()
    else:
        with app.state.session_factory() as db:
            account = db.get(User, user.id)
            if state == "revoked":
                account.session_version += 1
            else:
                account.is_active = False
            db.commit()

    invalid_cookie = client.cookies.get(COOKIE)
    for destination in (
        "/course",
        "/course/orientation?example=one%20two",
        "/portal",
        "/attendee?show_credentials=true",
        "/admin",
        "/admin/protected",
        "/admin/attendees",
        "/admin/vms",
    ):
        # Test each route against the original stale cookie, before login refreshes it.
        client.cookies.clear()
        if invalid_cookie is not None:
            client.cookies.set(COOKIE, invalid_cookie)
        location = assert_login_redirect(client.get(destination), destination)
        page = client.get(location)
        assert page.status_code == 200
        assert NOTICE in page.text
    client.cookies.clear()
    if invalid_cookie is not None:
        client.cookies.set(COOKIE, invalid_cookie)
    password = client.get("/attendee/credentials/password")
    assert password.status_code == 401
    assert "location" not in password.headers


def test_expired_completion_keeps_saved_progress_and_never_replays(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    app = create_app(settings)
    user = add_user(app, username="attendee", password="password", role=UserRole.ATTENDEE)
    client = TestClient(app, follow_redirects=False)
    login(client, "attendee", "password")
    token = csrf_from(client.get("/course/orientation"))
    assert (
        client.post(
            "/course/orientation/completion", data={"csrf_token": token, "completed": "true"}
        ).status_code
        == 303
    )
    expire_cookie(client, settings.session_secret)
    location = assert_login_redirect(
        client.post(
            "/course/orientation/completion", data={"csrf_token": token, "completed": "false"}
        ),
        "/course/orientation",
    )
    form = client.get(location)
    submitted = {
        "username": "attendee",
        "password": "wrong",
        "csrf_token": csrf_from(form),
        "next_path": "/course/orientation",
        "reauth": "1",
    }
    failure = client.post("/login", data=submitted)
    assert failure.status_code == 401
    assert NOTICE in failure.text
    assert 'name="reauth" value="1"' in failure.text
    assert 'name="next_path" value="/course/orientation"' in failure.text
    submitted.update(password="password", csrf_token=csrf_from(failure))
    success = client.post("/login", data=submitted)
    assert success.status_code == 303
    assert success.headers["location"] == "/course/orientation"
    assert client.get(success.headers["location"]).status_code == 200
    with app.state.session_factory() as db:
        progress = db.scalar(select(CourseProgress).where(CourseProgress.attendee_id == user.id))
        assert progress.page_id == "orientation"
        assert progress.completed


def test_expired_admin_submissions_do_not_change_data(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    app = create_app(settings)
    admin = add_user(app, username="admin", password="password", role=UserRole.ADMIN)
    attendee = add_user(app, username="attendee", password="password", role=UserRole.ATTENDEE)
    client = TestClient(app, follow_redirects=False)
    login(client, "admin", "password")
    token = csrf_from(client.get("/admin"))
    expire_cookie(client, settings.session_secret)
    for path, data in (
        ("/admin/attendees/create", {"username": "new-user", "password": "password"}),
        (f"/admin/attendees/{attendee.id}/password", {"password": "replacement"}),
        (f"/admin/attendees/{attendee.id}/profile", {"display_name": "Changed"}),
        (f"/admin/attendees/{attendee.id}/status", {"active": "false"}),
        ("/admin/vms/create", {"host": "vm.test", "ssh_username": "student", "ssh_password": "pw"}),
        ("/admin/vms/123/edit", {"host": "changed.test"}),
        ("/admin/vms/123/assignment", {"attendee_id": str(attendee.id)}),
    ):
        assert_login_redirect(client.post(path, data={"csrf_token": token, **data}), "/admin")
    login(client, "admin", "password")
    with app.state.session_factory() as db:
        accounts = db.scalars(select(User)).all()
        assert {account.id for account in accounts} == {admin.id, attendee.id}
        account = db.get(User, attendee.id)
        assert account.password_hash == attendee.password_hash
        assert account.session_version == attendee.session_version
        assert account.is_active
        assert account.display_name is None
    assert "vm.test" not in client.get("/admin").text


@pytest.mark.parametrize(
    "destination", ["/course/orientation?example=one", "https://evil.test/", "//evil.test/"]
)
def test_expired_login_form_requires_resubmission_with_safe_destination(
    tmp_path: Path, destination: str
) -> None:
    settings = settings_for(tmp_path)
    app = create_app(settings)
    user = add_user(app, username="attendee", password="password", role=UserRole.ATTENDEE)
    client = TestClient(app, follow_redirects=False)
    token = csrf_from(client.get("/login"))
    expire_cookie(client, settings.session_secret)
    safe_destination = destination if destination.startswith("/course/") else "/"
    location = assert_login_redirect(
        client.post(
            "/login",
            data={
                "username": "attendee",
                "password": "password",
                "csrf_token": token,
                "next_path": destination,
            },
        ),
        safe_destination,
    )
    with app.state.session_factory() as db:
        assert db.get(User, user.id).session_version == user.session_version
    form = client.get(location)
    assert NOTICE in form.text
    assert csrf_from(form) != token
    response = client.post(
        "/login",
        data={
            "username": "attendee",
            "password": "password",
            "csrf_token": csrf_from(form),
            "next_path": safe_destination,
            "reauth": "1",
        },
    )
    assert response.status_code == 303
    assert response.headers["location"] == (
        "/course" if safe_destination == "/" else safe_destination
    )


@pytest.mark.parametrize("state", ["expired", "revoked"])
def test_stale_logout_recovers_without_revoking_new_session(tmp_path: Path, state: str) -> None:
    settings = settings_for(tmp_path)
    app = create_app(settings)
    user = add_user(app, username="attendee", password="password", role=UserRole.ATTENDEE)
    client = TestClient(app, follow_redirects=False)
    login(client, "attendee", "password")
    token = csrf_from(client.get("/course"))
    if state == "expired":
        expire_cookie(client, settings.session_secret)
    else:
        other_client = TestClient(app, follow_redirects=False)
        login(other_client, "attendee", "password")
    with app.state.session_factory() as db:
        version = db.get(User, user.id).session_version
    location = assert_login_redirect(client.post("/logout", data={"csrf_token": token}), "/")
    assert NOTICE in client.get(location).text
    with app.state.session_factory() as db:
        assert db.get(User, user.id).session_version == version
    if state == "revoked":
        assert other_client.get("/course").status_code == 200


def test_login_csrf_errors_in_live_sessions_remain_rejected(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    client = TestClient(app, follow_redirects=False)
    client.get("/login")
    for token in ("", "invalid"):
        assert client.post("/login", data={"csrf_token": token}).status_code == 400
