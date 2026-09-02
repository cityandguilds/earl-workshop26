"""SQLite engine setup and explicit managed schema initialization."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, event, inspect
from sqlalchemy import create_engine as sqlalchemy_create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .models import Base

SQLITE_BUSY_TIMEOUT_MS = 5_000


def _configure_sqlite_connection(dbapi_connection: object, _connection_record: object) -> None:
    """Apply safe SQLite defaults to each newly opened connection."""

    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        # WAL is persisted in the database and is not available for an in-memory DB;
        # SQLite returns the existing journal mode in that case without failing.
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()


def create_engine(database_path: Path | str) -> Engine:
    """Create a SQLite engine for a writable runtime path."""

    path = Path(database_path).expanduser()
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    engine_options = {
        "connect_args": {"check_same_thread": False, "timeout": SQLITE_BUSY_TIMEOUT_MS / 1000}
    }
    if str(path) == ":memory:":
        engine_options["poolclass"] = StaticPool
    engine = sqlalchemy_create_engine(f"sqlite:///{path}", **engine_options)
    event.listen(engine, "connect", _configure_sqlite_connection)
    return engine


def initialize_database(engine: Engine) -> None:
    """Create all current tables if absent.

    This is intentionally an application-managed initialization boundary. The slice has
    one small schema, so SQLAlchemy metadata creation is sufficient and is safe to rerun
    on every application start.
    """

    Base.metadata.create_all(engine)
    # ``create_all`` intentionally does not alter an existing table. Keep the small
    # schema changes made during this increment compatible with an earlier database.
    with engine.begin() as connection:
        user_columns = {column["name"] for column in inspect(connection).get_columns("users")}
        if "session_version" not in user_columns:
            connection.exec_driver_sql(
                "ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0"
            )
        if "display_name" not in user_columns:
            connection.exec_driver_sql(
                "ALTER TABLE users ADD COLUMN display_name VARCHAR(150)"
            )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a session factory with explicit commit/close ownership at call sites."""

    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Yield a short-lived session for CLI and other non-request operations."""

    with factory() as session:
        yield session
