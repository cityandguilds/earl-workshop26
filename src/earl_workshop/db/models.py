"""SQLAlchemy models for persistent portal state."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for the managed application schema."""


class UserRole(StrEnum):
    """Roles which can authenticate to the portal."""

    ADMIN = "admin"
    ATTENDEE = "attendee"


class User(Base):
    """A portal account with a role used by server-side authorization."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'attendee')", name="ck_users_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
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
    vm_assignments: Mapped[list[VMAssignment]] = relationship(
        "VMAssignment", back_populates="attendee"
    )
    course_progress: Mapped[list[CourseProgress]] = relationship(
        "CourseProgress", back_populates="attendee"
    )


class CourseProgress(Base):
    """An attendee's completion state for one stable Markdown page ID."""

    __tablename__ = "course_progress"
    __table_args__ = (
        UniqueConstraint(
            "attendee_id", "page_id", name="uq_course_progress_attendee_page"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attendee_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_id: Mapped[str] = mapped_column(String(150), nullable=False)
    completed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    attendee: Mapped[User] = relationship("User", back_populates="course_progress")


class VMCredential(Base):
    """Connection details for one workshop VM.

    The SSH password is represented only by ``encrypted_password``. Plaintext is
    accepted by the persistence service and decrypted only for an authorized
    attendee dashboard response.
    """

    __tablename__ = "vm_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    ssh_username: Mapped[str] = mapped_column(String(150), nullable=False)
    encrypted_password: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    assignments: Mapped[list[VMAssignment]] = relationship(
        "VMAssignment", back_populates="vm_credential"
    )


class VMAssignment(Base):
    """The active attendee-to-VM relationship used for credential authorization."""

    __tablename__ = "vm_assignments"
    __table_args__ = (
        CheckConstraint("active IN (0, 1)", name="ck_vm_assignments_active"),
        Index(
            "uq_vm_assignments_one_active_per_attendee",
            "attendee_id",
            unique=True,
            sqlite_where=text("active = 1"),
        ),
        Index(
            "uq_vm_assignments_one_active_per_vm",
            "vm_credential_id",
            unique=True,
            sqlite_where=text("active = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attendee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    vm_credential_id: Mapped[int] = mapped_column(
        ForeignKey("vm_credentials.id"), nullable=False, index=True
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    attendee: Mapped[User] = relationship("User", back_populates="vm_assignments")
    vm_credential: Mapped[VMCredential] = relationship(
        "VMCredential", back_populates="assignments"
    )
