"""Encrypted VM credential persistence and authorized presentation helpers."""

from __future__ import annotations

import binascii
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from .db.models import User, UserRole, VMAssignment, VMCredential

VM_ENCRYPTION_KEY_ENV = "EARL_WORKSHOP_VM_ENCRYPTION_KEY"


class VMEncryptionError(ValueError):
    """Raised when the required VM encryption configuration or ciphertext is invalid."""


def validate_vm_encryption_key(key: str | None) -> str:
    """Validate and return a dedicated URL-safe Fernet key without exposing its value."""

    if not isinstance(key, str) or not key.strip():
        raise VMEncryptionError(
            f"{VM_ENCRYPTION_KEY_ENV} must be configured with a valid Fernet key"
        )
    try:
        Fernet(key.encode("ascii"))
    except (binascii.Error, TypeError, UnicodeError, ValueError) as exc:
        raise VMEncryptionError(
            f"{VM_ENCRYPTION_KEY_ENV} must be configured with a valid Fernet key"
        ) from exc
    return key


def _fernet(key: str | None) -> Fernet:
    return Fernet(validate_vm_encryption_key(key).encode("ascii"))


def encrypt_vm_password(password: str, key: str | None) -> str:
    """Encrypt an SSH password for persistence using the dedicated VM key."""

    if not isinstance(password, str) or not password:
        raise ValueError("VM password cannot be empty")
    return _fernet(key).encrypt(password.encode("utf-8")).decode("ascii")


def decrypt_vm_password(ciphertext: str, key: str | None) -> str:
    """Decrypt an SSH password, converting all key/ciphertext failures to a safe error."""

    try:
        plaintext = _fernet(key).decrypt(ciphertext.encode("ascii"))
        return plaintext.decode("utf-8")
    except (binascii.Error, InvalidToken, UnicodeError, TypeError, ValueError) as exc:
        raise VMEncryptionError("Unable to decrypt VM credential") from exc


@dataclass(frozen=True, slots=True)
class AttendeeVMConnection:
    """The short-lived, authorized presentation value for an attendee dashboard."""

    host: str
    ssh_username: str
    ssh_password: str


def create_vm_credential(
    session: Session,
    *,
    host: str,
    ssh_username: str,
    ssh_password: str,
    encryption_key: str | None,
) -> VMCredential:
    """Persist VM connection details with the password encrypted before flush."""

    if not host.strip():
        raise ValueError("VM host cannot be empty")
    if len(host.strip()) > 255:
        raise ValueError("VM host cannot be longer than 255 characters")
    if not ssh_username.strip():
        raise ValueError("SSH username cannot be empty")
    if len(ssh_username.strip()) > 150:
        raise ValueError("SSH username cannot be longer than 150 characters")
    credential = VMCredential(
        host=host.strip(),
        ssh_username=ssh_username.strip(),
        encrypted_password=encrypt_vm_password(ssh_password, encryption_key),
    )
    session.add(credential)
    session.commit()
    session.refresh(credential)
    return credential


def update_vm_credential(
    session: Session,
    *,
    vm_credential_id: int,
    host: str,
    ssh_username: str,
    ssh_password: str | None,
    encryption_key: str | None,
) -> VMCredential:
    """Update VM connection fields, encrypting a replacement password when supplied."""

    if not host.strip():
        raise ValueError("VM host cannot be empty")
    if len(host.strip()) > 255:
        raise ValueError("VM host cannot be longer than 255 characters")
    if not ssh_username.strip():
        raise ValueError("SSH username cannot be empty")
    if len(ssh_username.strip()) > 150:
        raise ValueError("SSH username cannot be longer than 150 characters")
    credential = session.get(VMCredential, vm_credential_id)
    if credential is None:
        raise ValueError("VM credential does not exist")
    credential.host = host.strip()
    credential.ssh_username = ssh_username.strip()
    if ssh_password:
        credential.encrypted_password = encrypt_vm_password(ssh_password, encryption_key)
    session.commit()
    session.refresh(credential)
    return credential


def assign_vm_credential(
    session: Session, *, attendee_id: int, vm_credential_id: int
) -> VMAssignment:
    """Create one active assignment for an attendee and one VM.

    Partial unique indexes enforce the same invariant for direct persistence setup and
    concurrent callers. This low-level helper rejects existing assignments; the admin
    workflow uses :func:`reassign_vm_credential` when replacement is intentional.
    """

    attendee = session.get(User, attendee_id)
    if attendee is None or attendee.role != UserRole.ATTENDEE.value:
        raise ValueError("VM assignments require an attendee account")
    if session.get(VMCredential, vm_credential_id) is None:
        raise ValueError("VM credential does not exist")
    existing = session.scalar(
        select(VMAssignment).where(
            VMAssignment.attendee_id == attendee_id,
            VMAssignment.active.is_(True),
        )
    )
    if existing is not None:
        raise ValueError("Attendee already has an active VM assignment")
    existing_vm_owner = session.scalar(
        select(VMAssignment).where(
            VMAssignment.vm_credential_id == vm_credential_id,
            VMAssignment.active.is_(True),
        )
    )
    if existing_vm_owner is not None:
        raise ValueError("VM credential already has an active attendee assignment")
    assignment = VMAssignment(attendee_id=attendee_id, vm_credential_id=vm_credential_id)
    session.add(assignment)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ValueError("VM credential is already assigned") from exc
    session.refresh(assignment)
    return assignment


def reassign_vm_credential(
    session: Session, *, vm_credential_id: int, attendee_id: int | None
) -> VMAssignment | None:
    """Assign a VM to one attendee, clearing any previous owner and target assignment.

    Clearing the target's previous VM in the same transaction makes the resulting state
    unambiguous: a VM has at most one active owner and an attendee has at most one active VM.
    Passing ``None`` unassigns the VM.
    """

    credential = session.get(VMCredential, vm_credential_id)
    if credential is None:
        raise ValueError("VM credential does not exist")

    if attendee_id is not None:
        attendee = session.get(User, attendee_id)
        if attendee is None or attendee.role != UserRole.ATTENDEE.value:
            raise ValueError("VM assignments require an attendee account")
        if not attendee.is_active:
            raise ValueError("VM assignments require an active attendee account")

    current_for_vm = session.scalar(
        select(VMAssignment).where(
            VMAssignment.vm_credential_id == vm_credential_id,
            VMAssignment.active.is_(True),
        )
    )
    current_for_target = None
    if attendee_id is not None:
        current_for_target = session.scalar(
            select(VMAssignment).where(
                VMAssignment.attendee_id == attendee_id,
                VMAssignment.active.is_(True),
            )
        )

    if (
        attendee_id is not None
        and current_for_vm is not None
        and current_for_vm.attendee_id == attendee_id
        and current_for_target is not None
        and current_for_target.id == current_for_vm.id
    ):
        return current_for_vm

    assignments_to_clear = []
    if current_for_vm is not None:
        assignments_to_clear.append(current_for_vm)
    if current_for_target is not None and (
        current_for_vm is None or current_for_target.id != current_for_vm.id
    ):
        assignments_to_clear.append(current_for_target)
    for assignment in assignments_to_clear:
        assignment.active = False
    try:
        session.flush()
        if attendee_id is None:
            session.commit()
            return None

        assignment = VMAssignment(attendee_id=attendee_id, vm_credential_id=vm_credential_id)
        session.add(assignment)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ValueError("VM assignment conflicts with another active assignment") from exc
    session.refresh(assignment)
    return assignment


def unassign_vm_credential(
    session: Session, *, vm_credential_id: int
) -> None:
    """Mark the VM's active assignment inactive, if it has one."""

    reassign_vm_credential(session, vm_credential_id=vm_credential_id, attendee_id=None)


def get_active_assignment(session: Session, *, attendee_id: int) -> VMAssignment | None:
    """Look up only the active assignment belonging to the authenticated attendee ID."""

    return session.scalar(
        select(VMAssignment)
        .options(joinedload(VMAssignment.vm_credential))
        .where(
            VMAssignment.attendee_id == attendee_id,
            VMAssignment.active.is_(True),
        )
    )


def attendee_connection(
    session: Session, *, attendee_id: int, encryption_key: str | None
) -> AttendeeVMConnection | None:
    """Decrypt the authenticated attendee's own assignment at the presentation boundary."""

    assignment = get_active_assignment(session, attendee_id=attendee_id)
    if assignment is None:
        return None
    credential = assignment.vm_credential
    return AttendeeVMConnection(
        host=credential.host,
        ssh_username=credential.ssh_username,
        ssh_password=decrypt_vm_password(credential.encrypted_password, encryption_key),
    )
