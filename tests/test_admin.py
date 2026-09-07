import re
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select

from earl_workshop.auth import authenticate_user, create_user
from earl_workshop.config import Settings
from earl_workshop.credentials import decrypt_vm_password
from earl_workshop.db import CourseProgress, User, UserRole, VMAssignment, VMCredential
from earl_workshop.main import create_app

CSRF_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')
TEST_VM_ENCRYPTION_KEY = Fernet.generate_key().decode()


def settings_for(
    tmp_path: Path,
    *,
    content_dir: Path = Path("content"),
) -> Settings:
    return Settings(
        root_dir=Path("."),
        content_dir=content_dir,
        resources_dir=Path("resources"),
        asset_dir=Path("assets"),
        data_dir=tmp_path / "runtime-data",
        session_secret="test-session-secret-which-is-long-enough",
        vm_encryption_key=TEST_VM_ENCRYPTION_KEY,
    )


def csrf_from(response) -> str:
    token = CSRF_PATTERN.search(response.text)
    assert token is not None
    return token.group(1)


def add_user(
    app,
    *,
    username: str,
    password: str,
    role: UserRole,
    is_active: bool = True,
) -> User:
    with app.state.session_factory() as session:
        return create_user(
            session,
            username=username,
            password=password,
            role=role,
            is_active=is_active,
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


def test_admin_account_lifecycle_and_csrf_are_browser_protected(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    add_user(app, username="admin", password="admin-password", role=UserRole.ADMIN)
    admin_client = TestClient(app, follow_redirects=False)
    login(admin_client, "admin", "admin-password")

    page = admin_client.get("/admin/attendees")
    assert page.status_code == 200
    assert "Create attendee" in page.text
    token = csrf_from(page)
    assert (
        admin_client.post(
            "/admin/attendees/create",
            data={"username": "new-user", "password": "new-password", "csrf_token": token},
            follow_redirects=False,
        ).status_code
        == 303
    )

    with app.state.session_factory() as session:
        attendee = session.scalar(select(User).where(User.username == "new-user"))
        assert attendee is not None
        attendee_id = attendee.id
        assert attendee.display_name is None
        assert attendee.password_hash != "new-password"
        assert authenticate_user(session, username="new-user", password="new-password") is attendee

    duplicate = admin_client.post(
        "/admin/attendees/create",
        data={
            "username": "NEW-USER",
            "password": "another-password",
            "csrf_token": csrf_from(admin_client.get("/admin")),
        },
        follow_redirects=False,
    )
    assert duplicate.status_code == 400
    assert "already in use" in duplicate.text

    missing_csrf = admin_client.post(
        "/admin/attendees/create",
        data={"username": "not-created", "password": "password"},
        follow_redirects=False,
    )
    assert missing_csrf.status_code == 400
    with app.state.session_factory() as session:
        assert session.scalar(select(User).where(User.username == "not-created")) is None

    reset = admin_client.post(
        f"/admin/attendees/{attendee_id}/password",
        data={
            "password": "replacement-password",
            "csrf_token": csrf_from(admin_client.get("/admin")),
        },
        follow_redirects=False,
    )
    assert reset.status_code == 303
    with app.state.session_factory() as session:
        assert authenticate_user(session, username="new-user", password="new-password") is None
        assert (
            authenticate_user(session, username="new-user", password="replacement-password")
            is not None
        )

    update_name = admin_client.post(
        f"/admin/attendees/{attendee_id}/profile",
        data={
            "display_name": "New User",
            "csrf_token": csrf_from(admin_client.get("/admin")),
        },
        follow_redirects=False,
    )
    assert update_name.status_code == 303
    assert "New User" in admin_client.get("/admin").text

    deactivate = admin_client.post(
        f"/admin/attendees/{attendee_id}/status",
        data={"active": "false", "csrf_token": csrf_from(admin_client.get("/admin"))},
        follow_redirects=False,
    )
    assert deactivate.status_code == 303
    with app.state.session_factory() as session:
        attendee = session.get(User, attendee_id)
        assert attendee is not None and not attendee.is_active

    attendee_client = TestClient(app, follow_redirects=False)
    assert attendee_client.get("/admin").status_code == 401
    login_page = attendee_client.get("/login")
    login_response = attendee_client.post(
        "/login",
        data={
            "username": "new-user",
            "password": "replacement-password",
            "csrf_token": csrf_from(login_page),
        },
        follow_redirects=False,
    )
    assert login_response.status_code == 401

    activate = admin_client.post(
        f"/admin/attendees/{attendee_id}/status",
        data={"active": "true", "csrf_token": csrf_from(admin_client.get("/admin"))},
        follow_redirects=False,
    )
    assert activate.status_code == 303


def test_attendee_cannot_read_or_mutate_admin_routes(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    add_user(app, username="attendee", password="attendee-password", role=UserRole.ATTENDEE)
    client = TestClient(app, follow_redirects=False)
    login(client, "attendee", "attendee-password")

    for path in ("/admin", "/admin/attendees", "/admin/vms"):
        assert client.get(path).status_code == 403
    response = client.post(
        "/admin/attendees/create",
        data={
            "username": "bad",
            "password": "bad",
            "csrf_token": csrf_from(client.get("/attendee")),
        },
        follow_redirects=False,
    )
    assert response.status_code == 403
    with app.state.session_factory() as session:
        assert session.scalar(select(User).where(User.username == "bad")) is None


def test_admin_can_create_replace_assign_reassign_and_unassign_encrypted_vm(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    add_user(app, username="admin", password="admin-password", role=UserRole.ADMIN)
    admin_client = TestClient(app, follow_redirects=False)
    login(admin_client, "admin", "admin-password")

    for username in ("alice", "bob"):
        response = admin_client.post(
            "/admin/attendees/create",
            data={
                "username": username,
                "password": f"{username}-password",
                "display_name": username.title(),
                "csrf_token": csrf_from(admin_client.get("/admin")),
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

    create_vm = admin_client.post(
        "/admin/vms/create",
        data={
            "host": "198.51.100.40",
            "ssh_username": "student",
            "ssh_password": "initial-vm-password",
            "csrf_token": csrf_from(admin_client.get("/admin")),
        },
        follow_redirects=False,
    )
    assert create_vm.status_code == 303
    second_vm = admin_client.post(
        "/admin/vms/create",
        data={
            "host": "198.51.100.41",
            "ssh_username": "student-2",
            "ssh_password": "second-vm-password",
            "csrf_token": csrf_from(admin_client.get("/admin")),
        },
        follow_redirects=False,
    )
    assert second_vm.status_code == 303
    with app.state.session_factory() as session:
        vm_credentials = session.scalars(select(VMCredential).order_by(VMCredential.id)).all()
        alice = session.scalar(select(User).where(User.username == "alice"))
        bob = session.scalar(select(User).where(User.username == "bob"))
        assert len(vm_credentials) == 2 and alice is not None and bob is not None
        vm, other_vm = vm_credentials
        vm_id, alice_id, bob_id = vm.id, alice.id, bob.id
        other_vm_id = other_vm.id
        ciphertext = vm.encrypted_password
        assert "initial-vm-password" not in ciphertext
        assert decrypt_vm_password(ciphertext, TEST_VM_ENCRYPTION_KEY) == "initial-vm-password"

    listing = admin_client.get("/admin")
    assert listing.status_code == 200
    assert "initial-vm-password" not in listing.text
    assert ciphertext not in listing.text

    assign = admin_client.post(
        f"/admin/vms/{vm_id}/assignment",
        data={"attendee_id": str(alice_id), "csrf_token": csrf_from(listing)},
        follow_redirects=False,
    )
    assert assign.status_code == 303
    assign_other = admin_client.post(
        f"/admin/vms/{other_vm_id}/assignment",
        data={"attendee_id": str(bob_id), "csrf_token": csrf_from(admin_client.get("/admin"))},
        follow_redirects=False,
    )
    assert assign_other.status_code == 303

    alice_client = TestClient(app, follow_redirects=False)
    login(alice_client, "alice", "alice-password")
    dashboard = alice_client.get("/attendee")
    assert "View VM credentials" in dashboard.text
    assert "198.51.100.40" not in dashboard.text
    assert "initial-vm-password" not in dashboard.text

    update_vm = admin_client.post(
        f"/admin/vms/{vm_id}/edit",
        data={
            "host": "vm.example.test",
            "ssh_username": "workshop",
            "ssh_password": "replacement-vm-password",
            "csrf_token": csrf_from(admin_client.get("/admin")),
        },
        follow_redirects=False,
    )
    assert update_vm.status_code == 303
    with app.state.session_factory() as session:
        vm = session.get(VMCredential, vm_id)
        assert vm is not None
        assert vm.host == "vm.example.test"
        assert vm.ssh_username == "workshop"
        assert (
            decrypt_vm_password(vm.encrypted_password, TEST_VM_ENCRYPTION_KEY)
            == "replacement-vm-password"
        )
        assert vm.encrypted_password != ciphertext

    reassign = admin_client.post(
        f"/admin/vms/{vm_id}/assignment",
        data={"attendee_id": str(bob_id), "csrf_token": csrf_from(admin_client.get("/admin"))},
        follow_redirects=False,
    )
    assert reassign.status_code == 303
    with app.state.session_factory() as session:
        active = session.scalars(select(VMAssignment).where(VMAssignment.active.is_(True))).all()
        assert len(active) == 1
        assert active[0].attendee_id == bob_id

    assert "No VM assigned" in alice_client.get("/attendee").text
    bob_client = TestClient(app, follow_redirects=False)
    login(bob_client, "bob", "bob-password")
    bob_dashboard = bob_client.get("/attendee")
    assert "View VM credentials" in bob_dashboard.text
    assert "vm.example.test" not in bob_dashboard.text
    assert "replacement-vm-password" not in bob_dashboard.text

    unassign = admin_client.post(
        f"/admin/vms/{vm_id}/assignment",
        data={"attendee_id": "", "csrf_token": csrf_from(admin_client.get("/admin"))},
        follow_redirects=False,
    )
    assert unassign.status_code == 303
    assert "No VM assigned" in bob_client.get("/attendee").text
    assert "Unassigned" in admin_client.get("/admin").text


def test_admin_progress_uses_current_markdown_page_count(tmp_path: Path) -> None:
    content_dir = tmp_path / "content"
    pages_dir = content_dir / "pages"
    pages_dir.mkdir(parents=True)
    (content_dir / "workshop.yml").write_text("title: Test\nsubtitle: Test\n", encoding="utf-8")
    (pages_dir / "one.md").write_text(
        "---\nid: one\ntitle: One\norder: 1\n---\nOne\n", encoding="utf-8"
    )
    (pages_dir / "two.md").write_text(
        "---\nid: two\ntitle: Two\norder: 2\n---\nTwo\n", encoding="utf-8"
    )
    app = create_app(settings_for(tmp_path, content_dir=content_dir))
    add_user(app, username="admin", password="admin-password", role=UserRole.ADMIN)
    attendee = add_user(
        app, username="attendee", password="attendee-password", role=UserRole.ATTENDEE
    )
    with app.state.session_factory() as session:
        session.add(CourseProgress(attendee_id=attendee.id, page_id="one", completed=True))
        session.commit()

    client = TestClient(app, follow_redirects=False)
    login(client, "admin", "admin-password")
    response = client.get("/admin")
    assert response.status_code == 200
    assert "1 / 2" in response.text
    assert "One" not in response.text
    assert "Last progress" in response.text
    assert "Not started" not in response.text


def test_admin_overview_has_no_fixed_attendee_limit(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    add_user(app, username="admin", password="admin-password", role=UserRole.ADMIN)
    for number in range(1, 26):
        add_user(
            app,
            username=f"attendee-{number:02d}",
            password="attendee-password",
            role=UserRole.ATTENDEE,
        )

    client = TestClient(app, follow_redirects=False)
    login(client, "admin", "admin-password")
    response = client.get("/admin")
    assert response.status_code == 200
    assert "25 accounts" in response.text
    assert "attendee-25" in response.text
