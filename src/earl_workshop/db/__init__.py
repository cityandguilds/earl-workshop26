"""Application-managed SQLAlchemy persistence for the workshop portal."""

from .database import create_engine, create_session_factory, initialize_database
from .models import Base, CourseProgress, User, UserRole, VMAssignment, VMCredential
from .progress import completed_page_ids, set_page_completion

__all__ = [
    "Base",
    "CourseProgress",
    "User",
    "UserRole",
    "VMAssignment",
    "VMCredential",
    "completed_page_ids",
    "create_engine",
    "create_session_factory",
    "initialize_database",
    "set_page_completion",
]
