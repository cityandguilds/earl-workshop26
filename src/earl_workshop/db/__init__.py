"""Application-managed SQLAlchemy persistence for the workshop portal."""

from .database import create_engine, create_session_factory, initialize_database
from .models import Base, User, UserRole, VMAssignment, VMCredential

__all__ = [
    "Base",
    "User",
    "UserRole",
    "VMAssignment",
    "VMCredential",
    "create_engine",
    "create_session_factory",
    "initialize_database",
]
