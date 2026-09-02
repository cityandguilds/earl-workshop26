"""Console entry point for local and installed-wheel startup."""

from __future__ import annotations

import argparse

import uvicorn

from . import __version__
from .config import Settings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the EARL 2026 workshop portal")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command")
    serve = subparsers.add_parser("serve", help="start the development web server")
    serve.add_argument("--host", default=None, help="bind host (default: configured host)")
    serve.add_argument(
        "--port", type=int, default=None, help="bind port (default: configured port)"
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command != "serve":
        _parser().print_help()
        return
    settings = Settings.from_env()
    uvicorn.run(
        "earl_workshop.main:app", host=args.host or settings.host, port=args.port or settings.port
    )
