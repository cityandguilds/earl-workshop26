from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select

from earl_workshop.auth import create_user
from earl_workshop.config import Settings
from earl_workshop.credentials import (
    VMEncryptionError,
    assign_vm_credential,
    create_vm_credential,
    decrypt_vm_password,
)
from earl_workshop.db import User, UserRole, VMAssignment, VMCredential
from earl_workshop.main import create_app

TEST_VM_ENCRYPTION_KEY = Fernet.generate_key().decode()


def settings_for(
    tmp_path: Path, *, vm_encryption_key: str | None = TEST_VM_ENCRYPTION_KEY
) -> Settings:
    return Settings(
        root_dir=Path("."),
        content_dir=Path("content"),
        resources_dir=Path("resources"),
        asset_dir=Path("assets"),
        data_dir=tmp_path / "runtime-data",
        session_secret="test-session-secret-which-is-long-enough",
        vm_encryption_key=vm_encryption_key,
    )


def add_attendee(app, username: str, password: str) -> User:
    with app.state.session_factory() as session:
        return create_user(session, username=username, password=password, role=UserRole.ATTENDEE)


def csrf_from(response) -> str:
    marker = 'name="csrf_token" value="'
    start = response.text.index(marker) + len(marker)
    return response.text[start : response.text.index('"', start)]


def login(client: TestClient, username: str, password: str) -> None:
    login_page = client.get("/login")
    response = client.post(
        "/login",
        data={
            "username": username,
            "password": password,
            "csrf_token": csrf_from(login_page),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_vm_password_is_encrypted_at_rest_and_recoverable(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    password = "vm-password-not-for-sqlite"

    with app.state.session_factory() as session:
        credential = create_vm_credential(
            session,
            host="203.0.113.12",
            ssh_username="workshop",
            ssh_password=password,
            encryption_key=TEST_VM_ENCRYPTION_KEY,
        )
        persisted = session.scalar(select(VMCredential).where(VMCredential.id == credential.id))

    assert persisted is not None
    assert password not in persisted.encrypted_password
    assert persisted.encrypted_password != password
    assert decrypt_vm_password(persisted.encrypted_password, TEST_VM_ENCRYPTION_KEY) == password


def test_two_attendees_only_see_their_own_active_vm_credentials(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    attendee_a = add_attendee(app, "attendee-a", "password-a")
    attendee_b = add_attendee(app, "attendee-b", "password-b")

    with app.state.session_factory() as session:
        credential_a = create_vm_credential(
            session,
            host="198.51.100.10",
            ssh_username="alice",
            ssh_password="password-a-vm",
            encryption_key=TEST_VM_ENCRYPTION_KEY,
        )
        credential_b = create_vm_credential(
            session,
            host="198.51.100.11",
            ssh_username="bob",
            ssh_password="password-b-vm",
            encryption_key=TEST_VM_ENCRYPTION_KEY,
        )
        assign_vm_credential(session, attendee_id=attendee_a.id, vm_credential_id=credential_a.id)
        assign_vm_credential(session, attendee_id=attendee_b.id, vm_credential_id=credential_b.id)

    client_a = TestClient(app)
    login(client_a, "attendee-a", "password-a")
    response_a = client_a.get("/attendee?vm_credential_id=2")
    assert response_a.status_code == 200
    assert "View VM credentials" in response_a.text
    assert "198.51.100.10" not in response_a.text
    assert "alice" not in response_a.text
    assert "password-a-vm" not in response_a.text
    assert "198.51.100.11" not in response_a.text
    assert "password-b-vm" not in response_a.text
    assert client_a.get("/attendee/credentials/password").text == "password-a-vm"

    shown_a = client_a.get("/attendee?show_credentials=true")
    assert "198.51.100.10" in shown_a.text
    assert "alice" in shown_a.text
    assert "password-a-vm" not in shown_a.text
    assert "••••••••" in shown_a.text

    client_b = TestClient(app)
    login(client_b, "attendee-b", "password-b")
    response_b = client_b.get("/attendee")
    assert response_b.status_code == 200
    assert "View VM credentials" in response_b.text
    assert "198.51.100.11" not in response_b.text
    assert "bob" not in response_b.text
    assert "password-b-vm" not in response_b.text
    assert "198.51.100.10" not in response_b.text
    assert "password-a-vm" not in response_b.text
    password_b = client_b.get("/attendee/credentials/password")
    assert password_b.text == "password-b-vm"
    assert password_b.headers["cache-control"] == "no-store"


def test_anonymous_and_unassigned_attendees_are_safe(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    add_attendee(app, "waiting", "waiting-password")

    anonymous = TestClient(app)
    assert anonymous.get("/attendee", follow_redirects=False).status_code == 303
    assert anonymous.get("/attendee/credentials/password").status_code == 401

    client = TestClient(app)
    login(client, "waiting", "waiting-password")
    response = client.get("/attendee?show_credentials=true")
    assert response.status_code == 200
    assert "No VM assigned" in response.text
    assert "Please check again later." in response.text
    assert "Copy password" not in response.text
    assert client.get("/attendee/credentials/password").status_code == 404


def test_active_assignment_is_one_per_attendee_and_one_per_vm(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    attendee_a = add_attendee(app, "attendee-a", "password-a")
    attendee_b = add_attendee(app, "attendee-b", "password-b")

    with app.state.session_factory() as session:
        credential_a = create_vm_credential(
            session,
            host="203.0.113.20",
            ssh_username="a",
            ssh_password="vm-a",
            encryption_key=TEST_VM_ENCRYPTION_KEY,
        )
        credential_b = create_vm_credential(
            session,
            host="203.0.113.21",
            ssh_username="b",
            ssh_password="vm-b",
            encryption_key=TEST_VM_ENCRYPTION_KEY,
        )
        assign_vm_credential(session, attendee_id=attendee_a.id, vm_credential_id=credential_a.id)
        with pytest.raises(ValueError, match="already has an active"):
            assign_vm_credential(
                session, attendee_id=attendee_a.id, vm_credential_id=credential_b.id
            )
        assign_vm_credential(session, attendee_id=attendee_b.id, vm_credential_id=credential_b.id)
        assert session.scalar(select(VMAssignment).where(VMAssignment.active.is_(True))) is not None


@pytest.mark.parametrize("bad_key", [None, "not-a-fernet-key", "short"])
def test_missing_or_malformed_vm_key_fails_without_plaintext_fallback(
    tmp_path: Path, bad_key: str | None
) -> None:
    with pytest.raises(VMEncryptionError):
        create_app(settings_for(tmp_path, vm_encryption_key=bad_key))


def test_environment_requires_a_valid_vm_key(monkeypatch) -> None:
    monkeypatch.delenv("EARL_WORKSHOP_VM_ENCRYPTION_KEY", raising=False)
    with pytest.raises(VMEncryptionError):
        Settings.from_env()

    monkeypatch.setenv("EARL_WORKSHOP_VM_ENCRYPTION_KEY", "not-a-fernet-key")
    with pytest.raises(VMEncryptionError):
        Settings.from_env()


def test_vm_key_is_not_in_settings_repr(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    assert TEST_VM_ENCRYPTION_KEY not in repr(settings)


def test_wrong_vm_key_returns_safe_unavailable_response(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    app = create_app(settings)
    attendee = add_attendee(app, "attendee", "account-password")
    with app.state.session_factory() as session:
        credential = create_vm_credential(
            session,
            host="203.0.113.30",
            ssh_username="workshop",
            ssh_password="secret-vm-password",
            encryption_key=TEST_VM_ENCRYPTION_KEY,
        )
        assign_vm_credential(session, attendee_id=attendee.id, vm_credential_id=credential.id)

    wrong_key_app = create_app(
        settings_for(tmp_path, vm_encryption_key=Fernet.generate_key().decode())
    )
    client = TestClient(wrong_key_app)
    login(client, "attendee", "account-password")
    response = client.get("/attendee?show_credentials=true")
    assert response.status_code == 503
    assert "Connection details unavailable" in response.text
    assert "secret-vm-password" not in response.text
    assert credential.encrypted_password not in response.text


def test_attendee_dashboard_hides_credentials_and_copies_the_password_on_demand(
    tmp_path: Path,
) -> None:
    app = create_app(settings_for(tmp_path))
    attendee = add_attendee(app, "attendee", "account-password")
    with app.state.session_factory() as session:
        credential = create_vm_credential(
            session,
            host="vm.example.test",
            ssh_username="student",
            ssh_password="selectable-vm-password",
            encryption_key=TEST_VM_ENCRYPTION_KEY,
        )
        assign_vm_credential(session, attendee_id=attendee.id, vm_credential_id=credential.id)

    client = TestClient(app)
    login(client, "attendee", "account-password")
    course = client.get("/course")
    assert 'href="/attendee">Get credentials</a>' in course.text
    assert "selectable-vm-password" not in course.text
    response = client.get("/attendee")
    assert response.status_code == 200
    assert "View VM credentials" in response.text
    assert "vm.example.test" not in response.text
    assert "student" not in response.text
    assert "selectable-vm-password" not in response.text

    response = client.get("/attendee?show_credentials=true")
    assert (
        '<code id="vm-host" class="credential-value" tabindex="0">vm.example.test</code>'
        in response.text
    )
    assert (
        '<code id="vm-username" class="credential-value" tabindex="0">student</code>'
        in response.text
    )
    assert (
        '<code id="vm-password" class="credential-value" aria-label="SSH password hidden">'
        "••••••••</code>" in response.text
    )
    assert "selectable-vm-password" not in response.text
    assert 'data-copy-target="vm-host"' in response.text
    assert 'data-copy-target="vm-username"' in response.text
    assert 'data-copy-url="/attendee/credentials/password"' in response.text
    password = client.get("/attendee/credentials/password")
    assert password.text == "selectable-vm-password"
    assert password.headers["cache-control"] == "no-store"
    assert '<script src="/static/attendee.js" defer></script>' in response.text
    script = client.get("/static/attendee.js")
    assert script.status_code == 200
    assert "navigator.clipboard" in script.text
    assert "fetch(button.dataset.copyUrl" in script.text
