import re
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select

from earl_workshop import cli
from earl_workshop.auth import create_user
from earl_workshop.cli import _parser, create_admin
from earl_workshop.config import Settings
from earl_workshop.db import User, UserRole, create_engine, initialize_database
from earl_workshop.main import create_app

CSRF_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')
TEST_VM_ENCRYPTION_KEY = Fernet.generate_key().decode()


def settings_for(tmp_path: Path, *, secure_cookies: bool = False) -> Settings:
    return Settings(
        root_dir=Path("."),
        content_dir=Path("content"),
        resources_dir=Path("resources"),
        asset_dir=Path("assets"),
        data_dir=tmp_path / "runtime-data",
        secure_cookies=secure_cookies,
        session_secret="test-session-secret-which-is-long-enough",
        vm_encryption_key=TEST_VM_ENCRYPTION_KEY,
    )


def csrf_from(response) -> str:
    token = CSRF_PATTERN.search(response.text)
    assert token is not None
    return token.group(1)


def add_user(app, *, username: str, password: str, role: UserRole, is_active: bool = True) -> User:
    with app.state.session_factory() as session:
        return create_user(
            session,
            username=username,
            password=password,
            role=role,
            is_active=is_active,
        )


def login(client: TestClient, username: str, password: str) -> None:
    token = csrf_from(client.get("/login"))
    response = client.post(
        "/login",
        data={"username": username, "password": password, "csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_database_initializes_in_runtime_path_and_user_survives_restart(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    app = create_app(settings)
    add_user(app, username="persisted", password="a secure password", role=UserRole.ATTENDEE)

    database_path = settings.resolved_database_path
    assert database_path == tmp_path / "runtime-data" / "earl_workshop.sqlite3"
    assert database_path.is_file()
    assert "src/earl_workshop" not in str(database_path)
    with app.state.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar() == 5_000

    restarted_app = create_app(settings)
    with restarted_app.state.session_factory() as session:
        user = session.scalar(select(User).where(User.username == "persisted"))
        assert user is not None


def test_managed_initialization_upgrades_a_previously_created_user_table(tmp_path: Path) -> None:
    database_path = tmp_path / "older.sqlite3"
    engine = create_engine(database_path)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE users ("
            "id INTEGER PRIMARY KEY, username VARCHAR(150) NOT NULL UNIQUE, "
            "password_hash TEXT NOT NULL, role VARCHAR(20) NOT NULL, "
            "is_active BOOLEAN NOT NULL)"
        )

    initialize_database(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("users")}
    assert {"session_version", "display_name"} <= columns


def test_passwords_are_argon2_hashes_and_no_plaintext_column_exists(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    user = add_user(app, username="hashed", password="visible nowhere", role=UserRole.ADMIN)

    assert user.password_hash.startswith("$argon2")
    assert "visible nowhere" not in user.password_hash
    assert "password" not in {column.name for column in inspect(User).columns}
    with app.state.session_factory() as session:
        persisted = session.get(User, user.id)
        assert persisted is not None
        assert persisted.password_hash == user.password_hash


def test_login_logout_and_signed_cookie_configuration(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path, secure_cookies=True))
    add_user(app, username="Admin", password="admin password", role=UserRole.ADMIN)
    client = TestClient(app, base_url="https://testserver", follow_redirects=False)

    assert client.get("/admin").status_code == 401
    login_page = client.get("/login")
    assert login_page.status_code == 200
    cookie = login_page.headers["set-cookie"].lower()
    assert "earl_workshop_session=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "secure" in cookie

    invalid = client.post(
        "/login",
        data={"username": "Admin", "password": "wrong", "csrf_token": csrf_from(login_page)},
        follow_redirects=False,
    )
    assert invalid.status_code == 401
    assert "Invalid username or password" in invalid.text

    login(client, "ADMIN", "admin password")
    assert client.get("/admin/protected").status_code == 200
    old_signed_cookie = client.cookies.get("earl_workshop_session")

    logout_token = csrf_from(client.get("/admin/protected"))
    logout = client.post("/logout", data={"csrf_token": logout_token}, follow_redirects=False)
    assert logout.status_code == 303
    assert client.get("/admin").status_code == 401
    client.cookies.set("earl_workshop_session", old_signed_cookie)
    assert client.get("/admin").status_code == 401


def test_login_rejects_external_and_malformed_return_destinations(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    add_user(app, username="admin", password="admin password", role=UserRole.ADMIN)
    for destination in ("https://example.org", "//example.org", "/\\example.org", "course"):
        client = TestClient(app, follow_redirects=False)
        form = client.get("/login", params={"next": destination})
        assert 'name="next_path" value="/"' in form.text
        response = client.post(
            "/login",
            data={
                "username": "admin",
                "password": "admin password",
                "csrf_token": csrf_from(form),
                "next_path": destination,
            },
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/"


def test_inactive_account_and_unknown_account_have_safe_login_failure(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    add_user(
        app,
        username="inactive",
        password="inactive password",
        role=UserRole.ATTENDEE,
        is_active=False,
    )
    client = TestClient(app, follow_redirects=False)

    token = csrf_from(client.get("/login"))
    inactive = client.post(
        "/login",
        data={"username": "inactive", "password": "inactive password", "csrf_token": token},
        follow_redirects=False,
    )
    unknown = client.post(
        "/login",
        data={"username": "does-not-exist", "password": "inactive password", "csrf_token": token},
        follow_redirects=False,
    )

    assert inactive.status_code == unknown.status_code == 401
    assert "Invalid username or password" in inactive.text
    assert "Invalid username or password" in unknown.text
    assert client.get("/portal").status_code == 401


def test_role_guards_are_enforced_server_side(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    add_user(app, username="attendee", password="attendee password", role=UserRole.ATTENDEE)
    add_user(app, username="admin", password="admin password", role=UserRole.ADMIN)
    client = TestClient(app, follow_redirects=False)

    login(client, "attendee", "attendee password")
    assert client.get("/portal").status_code == 200
    assert client.get("/admin").status_code == 403
    assert client.get("/admin/protected").status_code == 403

    client.post("/logout", data={"csrf_token": csrf_from(client.get("/portal"))})
    login(client, "admin", "admin password")
    assert client.get("/admin").status_code == 200
    assert client.get("/admin/protected").status_code == 200


def test_state_changing_forms_require_csrf_without_mutating_session(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    add_user(app, username="admin", password="admin password", role=UserRole.ADMIN)
    client = TestClient(app, follow_redirects=False)

    login(client, "admin", "admin password")
    assert client.post("/logout", data={}, follow_redirects=False).status_code == 400
    assert client.get("/admin").status_code == 200
    assert (
        client.post("/logout", data={"csrf_token": "invalid"}, follow_redirects=False).status_code
        == 400
    )
    assert client.get("/admin").status_code == 200

    login_page = client.get("/login")
    # An already authenticated browser is redirected, so the mutating login form is
    # explicitly checked using a fresh anonymous session.
    anonymous = TestClient(app, follow_redirects=False)
    assert (
        anonymous.post(
            "/login", data={"username": "admin", "password": "admin password"}
        ).status_code
        == 400
    )
    assert login_page.status_code == 303


def test_create_admin_cli_has_no_password_argument_and_persists_admin(tmp_path: Path) -> None:
    parser = _parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["create-admin", "--password", "not-safe"])

    settings = settings_for(tmp_path)
    create_admin(settings, username="first-admin", password="cli password")
    with create_app(settings).state.session_factory() as session:
        admin = session.scalar(select(User).where(User.username == "first-admin"))
        assert admin is not None
        assert admin.role == UserRole.ADMIN


def test_create_admin_cli_prompts_for_password_without_echoing_it(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    settings = settings_for(tmp_path)
    monkeypatch.setattr("builtins.input", lambda _prompt: "prompted-admin")
    passwords = iter(["prompted password", "prompted password"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: next(passwords))

    assert cli._create_admin_from_prompts(settings, None) == 0
    assert "prompted password" not in capsys.readouterr().out
    with create_app(settings).state.session_factory() as session:
        admin = session.scalar(select(User).where(User.username == "prompted-admin"))
        assert admin is not None
        assert admin.role == UserRole.ADMIN
