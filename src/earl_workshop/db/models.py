"""SQLAlchemy models for persistent portal state."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Text, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for the managed application schema."""


class UserRole(StrEnum):
    """Roles which can authenticate to the portal."""

    ADMIN = "admin"
    ATTENDEE = "attendee"


class User(Base):
    """A portal account; VM credentials are deliberately not part of this model."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'attendee')", name="ck_users_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default=UserRole.ATTENDEE.value
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    session_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
