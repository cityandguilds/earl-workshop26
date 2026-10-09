from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE settings without overwriting existing variables."""
    if not path.is_file():
        raise RuntimeError(f"Database configuration file not found: {path}")

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    pg_host: str
    pg_port: int
    pg_database: str
    pg_user: str
    pg_password: str


def get_settings() -> Settings:
    configured_path = os.getenv("DSI_DATABASE_ENV")
    env_path = (
        Path(configured_path).expanduser()
        if configured_path
        else Path.home() / ".config" / "dsi" / "database.env"
    )
    load_env_file(env_path)

    required = ["PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(
            "Missing database settings: " + ", ".join(missing)
        )

    return Settings(
        pg_host=os.environ["PGHOST"],
        pg_port=int(os.environ["PGPORT"]),
        pg_database=os.environ["PGDATABASE"],
        pg_user=os.environ["PGUSER"],
        pg_password=os.environ["PGPASSWORD"],
    )
