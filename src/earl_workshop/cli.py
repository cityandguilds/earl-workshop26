"""Console entry point for local and installed-wheel startup."""

from __future__ import annotations

import argparse
import getpass
from collections.abc import Sequence

import uvicorn
from sqlalchemy.exc import IntegrityError

from . import __version__
from .auth import create_user
from .config import Settings
from .db import UserRole, create_engine, create_session_factory, initialize_database


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the EARL 2026 workshop portal")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command")
    serve = subparsers.add_parser("serve", help="start the development web server")
    serve.add_argument("--host", default=None, help="bind host (default: configured host)")
    serve.add_argument(
        "--port", type=int, default=None, help="bind port (default: configured port)"
    )
    create_admin = subparsers.add_parser(
        "create-admin", help="create an administrator account using safe interactive prompts"
    )
    create_admin.add_argument(
        "--username", default=None, help="administrator username (prompted when omitted)"
    )
    return parser


def create_admin(settings: Settings, *, username: str, password: str) -> None:
    """Initialize the runtime database and create one administrator account."""

    engine = create_engine(settings.resolved_database_path)
    initialize_database(engine)
    session_factory = create_session_factory(engine)
    try:
        with session_factory() as session:
            create_user(session, username=username, password=password, role=UserRole.ADMIN)
    except IntegrityError as exc:
        raise ValueError("That username is already in use") from exc
    finally:
        engine.dispose()


def _create_admin_from_prompts(settings: Settings, username: str | None) -> int:
    prompted_username = username or input("Administrator username: ").strip()
    password = getpass.getpass("Administrator password: ")
    confirmation = getpass.getpass("Confirm administrator password: ")
    if password != confirmation:
        print("Passwords did not match.")
        return 2
    try:
        create_admin(settings, username=prompted_username, password=password)
    except (ValueError, IntegrityError) as exc:
        print(f"Unable to create administrator: {exc}")
        return 2
    print(f"Administrator account created for {prompted_username.strip()!r}.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "create-admin":
        return _create_admin_from_prompts(Settings.from_env(), args.username)
    if args.command != "serve":
        _parser().print_help()
        return 0
    settings = Settings.from_env()
    uvicorn.run(
        "earl_workshop.main:app", host=args.host or settings.host, port=args.port or settings.port
    )
    return 0
