"""Environment-driven settings for the read-only application foundation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = PACKAGE_ROOT.parent.parent


def _env_path(name: str, default: Path) -> Path:
    value = os.getenv(name)
    return Path(value).expanduser() if value else default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value (true/false), got {value!r}")


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings, with source-checkout and wheel-friendly defaults.

    Content and resources can be moved outside the installed package by setting their
    corresponding environment variables. Secrets are represented here for the later
    stateful slices but are intentionally not required by this read-only slice.
    """

    root_dir: Path
    content_dir: Path
    resources_dir: Path
    asset_dir: Path
    data_dir: Path
    host: str = "127.0.0.1"
    port: int = 8000
    public_base_url: str = ""
    environment: str = "development"
    secure_cookies: bool = False
    session_secret: str | None = None
    vm_encryption_key: str | None = None

    @classmethod
    def from_env(cls) -> Settings:
        configured_root = os.getenv("EARL_WORKSHOP_ROOT")
        root_dir = Path(configured_root).expanduser() if configured_root else SOURCE_ROOT
        source_layout_available = (root_dir / "content").exists()
        content_default = (
            root_dir / "content" if source_layout_available else PACKAGE_ROOT / "content"
        )
        resources_default = (
            root_dir / "resources" if source_layout_available else PACKAGE_ROOT / "resources"
        )
        assets_default = (
            root_dir / "assets" if source_layout_available else PACKAGE_ROOT / "brand_assets"
        )
        data_default = root_dir / ".data" if source_layout_available else Path.cwd() / ".data"

        port_value = os.getenv("EARL_WORKSHOP_PORT", "8000")
        try:
            port = int(port_value)
        except ValueError as exc:
            raise ValueError(f"EARL_WORKSHOP_PORT must be an integer, got {port_value!r}") from exc
        if not 1 <= port <= 65535:
            raise ValueError(f"EARL_WORKSHOP_PORT must be between 1 and 65535, got {port}")

        public_base_url = os.getenv("EARL_WORKSHOP_PUBLIC_BASE_URL", "").rstrip("/")
        return cls(
            root_dir=root_dir,
            content_dir=_env_path("EARL_WORKSHOP_CONTENT_DIR", content_default),
            resources_dir=_env_path("EARL_WORKSHOP_RESOURCES_DIR", resources_default),
            asset_dir=_env_path("EARL_WORKSHOP_ASSET_DIR", assets_default),
            data_dir=_env_path("EARL_WORKSHOP_DATA_DIR", data_default),
            host=os.getenv("EARL_WORKSHOP_HOST", "127.0.0.1"),
            port=port,
            public_base_url=public_base_url,
            environment=os.getenv("EARL_WORKSHOP_ENVIRONMENT", "development"),
            secure_cookies=_env_bool("EARL_WORKSHOP_SECURE_COOKIES", False),
            session_secret=os.getenv("EARL_WORKSHOP_SESSION_SECRET"),
            vm_encryption_key=os.getenv("EARL_WORKSHOP_VM_ENCRYPTION_KEY"),
        )
