from __future__ import annotations

from collections.abc import Iterator

import psycopg
from psycopg.rows import dict_row

from .config import get_settings


def get_connection() -> Iterator[psycopg.Connection]:
    """Yield one PostgreSQL connection for a request, then close it."""
    settings = get_settings()

    with psycopg.connect(
        host=settings.pg_host,
        port=settings.pg_port,
        dbname=settings.pg_database,
        user=settings.pg_user,
        password=settings.pg_password,
        row_factory=dict_row,
        connect_timeout=5,
    ) as connection:
        yield connection
