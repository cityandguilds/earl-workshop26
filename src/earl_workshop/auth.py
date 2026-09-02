"""Portal password hashing, session identity, and CSRF helpers."""

from __future__ import annotations

import secrets
from collections.abc import Mapping

from fastapi import HTTPException, Request, status
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db.models import User, UserRole

PASSWORD_HASHER = PasswordHash.recommended()
# Verify against a real Argon2 hash when a username is unknown so that the login path
# does not make account existence obvious through a cheap early return.
DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash(secrets.token_urlsafe(32))
SESSION_USER_ID_KEY = "user_id"
SESSION_VERSION_KEY = "session_version"
SESSION_CSRF_KEY = "csrf_token"


def normalize_username(username: str) -> str:
    """Normalize usernames for case-insensitive, whitespace-safe account lookup."""

    return username.strip().casefold()


def hash_password(password: str) -> str:
    """Hash a portal password with the maintained recommended password scheme."""

    return PASSWORD_HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password, treating malformed stored hashes as a failed login."""

    try:
        return PASSWORD_HASHER.verify(password, password_hash)
    except (TypeError, ValueError, UnknownHashError):
        return False


def create_user(
    session: Session,
    *,
    username: str,
    password: str,
    role: UserRole | str = UserRole.ATTENDEE,
    is_active: bool = True,
    display_name: str | None = None,
) -> User:
    """Persist a user with only a one-way password hash."""

    normalized_username = normalize_username(username)
    if not normalized_username:
        raise ValueError("Username cannot be empty")
    if len(normalized_username) > 150:
        raise ValueError("Username cannot be longer than 150 characters")
    if not password:
        raise ValueError("Password cannot be empty")
    role_value = role.value if isinstance(role, UserRole) else role
    if role_value not in {member.value for member in UserRole}:
        raise ValueError("Role must be admin or attendee")
    normalized_display_name = display_name.strip() if display_name else None
    if normalized_display_name and len(normalized_display_name) > 150:
        raise ValueError("Display name cannot be longer than 150 characters")
    user = User(
        username=normalized_username,
        display_name=normalized_display_name,
        password_hash=hash_password(password),
        role=role_value,
        is_active=is_active,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def authenticate_user(session: Session, *, username: str, password: str) -> User | None:
    """Return an active user for valid credentials, otherwise return ``None``."""

    normalized_username = normalize_username(username)
    user = session.scalar(select(User).where(User.username == normalized_username))
    stored_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    password_matches = verify_password(password, stored_hash)
    if user is None or not user.is_active or not password_matches:
        return None
    return user


def establish_session(request: Request, session: Session, user: User) -> None:
    """Rotate the account session version and establish a signed browser session."""

    user.session_version += 1
    session.commit()
    request.session.clear()
    request.session[SESSION_USER_ID_KEY] = user.id
    request.session[SESSION_VERSION_KEY] = user.session_version
    rotate_csrf_token(request)


def invalidate_session(request: Request, session: Session, user: User | None) -> None:
    """Revoke the current account session before clearing its signed cookie."""

    if user is not None:
        user.session_version += 1
        session.commit()
    request.session.clear()


def csrf_token(request: Request) -> str:
    """Get or create the CSRF token bound to this signed session cookie."""

    token = request.session.get(SESSION_CSRF_KEY)
    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        request.session[SESSION_CSRF_KEY] = token
    return token


def rotate_csrf_token(request: Request) -> str:
    """Rotate the token after authentication to prevent session fixation."""

    token = secrets.token_urlsafe(32)
    request.session[SESSION_CSRF_KEY] = token
    return token


def validate_csrf(request: Request, submitted_token: str | None) -> None:
    """Reject a missing or invalid form token with a generic client error."""

    expected_token = request.session.get(SESSION_CSRF_KEY)
    if not isinstance(expected_token, str) or not submitted_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid CSRF token")
    if not secrets.compare_digest(expected_token, submitted_token):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid CSRF token")


def current_user(session: Session, request: Request) -> User | None:
    """Resolve the session user, clearing stale or inactive sessions."""

    raw_user_id = request.session.get(SESSION_USER_ID_KEY)
    raw_session_version = request.session.get(SESSION_VERSION_KEY)
    if (
        isinstance(raw_user_id, bool)
        or not isinstance(raw_user_id, int)
        or isinstance(raw_session_version, bool)
        or not isinstance(raw_session_version, int)
    ):
        return None
    user = session.get(User, raw_user_id)
    if user is None or not user.is_active or user.session_version != raw_session_version:
        request.session.clear()
        return None
    return user


def require_authenticated_user(session: Session, request: Request) -> User:
    """Require an active authenticated account at the route boundary."""

    user = current_user(session, request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Session"},
        )
    return user


def require_role(session: Session, request: Request, role: UserRole) -> User:
    """Require authentication and a specific server-side role."""

    user = require_authenticated_user(session, request)
    if user.role != role.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    return user


def public_session_context(request: Request) -> Mapping[str, object]:
    """Return the safe session values needed by shared templates."""

    return {"csrf_token": csrf_token(request)}
