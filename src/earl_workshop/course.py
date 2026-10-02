"""Filesystem-backed workshop metadata, Markdown loading, and validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from posixpath import normpath
from typing import Any

import markdown
import yaml


class CourseContentError(ValueError):
    """Raised when the workshop content violates the documented authoring contract."""


@dataclass(frozen=True, slots=True)
class ResourceDeclaration:
    file: str
    label: str


@dataclass(frozen=True, slots=True)
class CoursePage:
    id: str
    title: str
    order: int
    section: str
    section_order: int
    resources: tuple[ResourceDeclaration, ...]
    markdown: str
    html: str
    source_path: Path


@dataclass(frozen=True, slots=True)
class CourseSection:
    """A navigation section derived from page front matter."""

    name: str
    order: int
    pages: tuple[CoursePage, ...]


@dataclass(frozen=True, slots=True)
class Workshop:
    title: str
    subtitle: str
    pages: tuple[CoursePage, ...]

    @property
    def sections(self) -> tuple[CourseSection, ...]:
        """Group the already-ordered pages without hard-coding course sections."""

        grouped: dict[tuple[int, str], list[CoursePage]] = {}
        section_names: dict[tuple[int, str], str] = {}
        for page in self.pages:
            key = (page.section_order, page.section.casefold())
            grouped.setdefault(key, []).append(page)
            section_names.setdefault(key, page.section)
        return tuple(
            CourseSection(
                name=section_names[key],
                order=key[0],
                pages=tuple(grouped[key]),
            )
            for key in sorted(grouped)
        )


_FENCE_PATTERN = r"^ {0,3}(`{3,}|~{3,})[^\n]*\n.*?^ {0,3}\1\s*$"
_INLINE_CODE_PATTERN = r"(`+)(.+?)(?<!`)\1(?!`)"
_PROTECTED_RE = re.compile(
    f"(?:{_FENCE_PATTERN})|(?:{_INLINE_CODE_PATTERN})", re.MULTILINE | re.DOTALL
)
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_QUARTO_R_FENCE_RE = re.compile(r"^( {0,3}(?:`{3,}|~{3,}))\{r\}[ \t]*$", re.IGNORECASE)
_HTML_OR_QUOTE_RE = re.compile(r"(?P<quote>^ {0,3}(?:>[ \t]*)+)|[<>]", re.MULTILINE)


def _escape_html_text(text: str) -> str:
    """Escape angle brackets while preserving Markdown blockquote markers."""

    return _HTML_OR_QUOTE_RE.sub(
        lambda match: (
            match.group(0)
            if match.group("quote") is not None
            else {"<": "&lt;", ">": "&gt;"}[match.group(0)]
        ),
        text,
    )


def _escape_raw_html(markdown_source: str) -> str:
    """Escape HTML-looking text while leaving Markdown code spans and fences intact.

    Python-Markdown intentionally supports raw HTML. Workshop authors should be able to
    paste examples without turning them into trusted page markup, so only Markdown's own
    generated HTML is allowed through to the template.
    """

    protected: list[str] = []

    def protect(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"\x00EARL_CODE_{len(protected) - 1}\x00"

    escaped_parts: list[str] = []
    cursor = 0
    for match in _PROTECTED_RE.finditer(markdown_source):
        escaped_parts.append(_escape_html_text(markdown_source[cursor : match.start()]))
        escaped_parts.append(protect(match))
        cursor = match.end()
    escaped_parts.append(_escape_html_text(markdown_source[cursor:]))
    escaped = "".join(escaped_parts)
    for index, original in enumerate(protected):
        escaped = escaped.replace(f"\x00EARL_CODE_{index}\x00", original)
    return escaped


def _normalise_quarto_r_fence(match: re.Match[str]) -> str:
    """Treat a Quarto R chunk as R without changing the code inside its fence."""

    opening, newline, body = match.group(0).partition("\n")
    return _QUARTO_R_FENCE_RE.sub(r"\1r", opening) + newline + body


def render_markdown(markdown_source: str) -> str:
    """Render Markdown with highlighted code, tables, and raw HTML disabled."""

    safe_source = _escape_raw_html(markdown_source)
    safe_source = _PROTECTED_RE.sub(_normalise_quarto_r_fence, safe_source)
    return markdown.markdown(
        safe_source,
        extensions=["fenced_code", "tables", "codehilite"],
        extension_configs={"codehilite": {"guess_lang": False, "pygments_style": "monokai"}},
    )


def _read_yaml(path: Path, *, description: str) -> dict[str, Any]:
    try:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CourseContentError(f"Unable to read {description} {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise CourseContentError(f"Invalid YAML in {description} {path}: {exc}") from exc
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise CourseContentError(f"{description.capitalize()} {path} must contain a YAML mapping")
    return parsed


def _front_matter(path: Path) -> tuple[dict[str, Any], str]:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CourseContentError(f"Unable to read course page {path}: {exc}") from exc

    lines = source.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise CourseContentError(
            f"Course page {path} must begin with YAML front matter; "
            "expected '---' on the first line"
        )
    closing_index = next(
        (index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
        None,
    )
    if closing_index is None:
        raise CourseContentError(f"Course page {path} has front matter without a closing '---'")

    front_matter_text = "".join(lines[1:closing_index])
    try:
        metadata = yaml.safe_load(front_matter_text)
    except yaml.YAMLError as exc:
        raise CourseContentError(f"Invalid YAML front matter in {path}: {exc}") from exc
    if not isinstance(metadata, dict):
        raise CourseContentError(f"Front matter in {path} must contain a YAML mapping")
    return metadata, "".join(lines[closing_index + 1 :]).lstrip()


def _required_text(metadata: dict[str, Any], field: str, path: Path) -> str:
    value = metadata.get(field)
    if not isinstance(value, str) or not value.strip():
        raise CourseContentError(f"Course page {path} requires a non-empty string '{field}' field")
    return value.strip()


def _integer(
    metadata: dict[str, Any], field: str, path: Path, *, default: int | None = None
) -> int:
    value = metadata.get(field, default)
    if isinstance(value, bool) or not isinstance(value, int):
        requirement = "required integer" if default is None else "integer"
        raise CourseContentError(f"Course page {path} requires '{field}' to be an {requirement}")
    return value


def _resource_declarations(metadata: dict[str, Any], path: Path) -> tuple[ResourceDeclaration, ...]:
    raw_resources = metadata.get("resources", [])
    if raw_resources is None:
        raw_resources = []
    if not isinstance(raw_resources, list):
        raise CourseContentError(f"Course page {path} field 'resources' must be a list")

    declarations: list[ResourceDeclaration] = []
    for index, raw_resource in enumerate(raw_resources, start=1):
        if not isinstance(raw_resource, dict):
            raise CourseContentError(f"Course page {path} resource #{index} must be a mapping")
        resource_file = raw_resource.get("file")
        if not isinstance(resource_file, str) or not resource_file.strip():
            raise CourseContentError(
                f"Course page {path} resource #{index} requires a non-empty string 'file' field"
            )
        normalized = resource_file.strip().replace("\\", "/")
        parts = normalized.split("/")
        if (
            not normalized
            or "\x00" in normalized
            or normalized.startswith("/")
            or (len(normalized) >= 3 and normalized[1:3] == ":/")
            or ".." in parts
        ):
            raise CourseContentError(
                f"Course page {path} resource #{index} has unsafe file path {resource_file!r}"
            )
        normalized = normpath(normalized)
        if normalized in {"", ".", ".."} or normalized.startswith("../"):
            raise CourseContentError(
                f"Course page {path} resource #{index} has unsafe file path {resource_file!r}"
            )
        label = raw_resource.get("label", normalized)
        if not isinstance(label, str) or not label.strip():
            raise CourseContentError(
                f"Course page {path} resource #{index} field 'label' must be a non-empty string"
            )
        declarations.append(ResourceDeclaration(file=normalized, label=label.strip()))
    return tuple(declarations)


def _load_page(path: Path) -> CoursePage:
    metadata, body = _front_matter(path)
    page_id = _required_text(metadata, "id", path)
    if not _ID_RE.fullmatch(page_id):
        raise CourseContentError(
            f"Course page {path} has invalid id {page_id!r}; use letters, numbers, '-' or '_'"
        )
    title = _required_text(metadata, "title", path)
    order = _integer(metadata, "order", path)
    section = metadata.get("section", "Workshop")
    if not isinstance(section, str) or not section.strip():
        raise CourseContentError(f"Course page {path} field 'section' must be a non-empty string")
    section_order = _integer(metadata, "section_order", path, default=0)
    return CoursePage(
        id=page_id,
        title=title,
        order=order,
        section=section.strip(),
        section_order=section_order,
        resources=_resource_declarations(metadata, path),
        markdown=body,
        html=render_markdown(body),
        source_path=path,
    )


def load_workshop(content_dir: Path | str) -> Workshop:
    """Load, validate, and deterministically order a workshop content directory."""

    content_path = Path(content_dir).expanduser()
    metadata_path = content_path / "workshop.yml"
    pages_path = content_path / "pages"
    if not metadata_path.is_file():
        raise CourseContentError(f"Workshop metadata file not found: {metadata_path}")
    if not pages_path.is_dir():
        raise CourseContentError(f"Workshop pages directory not found: {pages_path}")

    metadata = _read_yaml(metadata_path, description="workshop metadata")
    title = metadata.get("title")
    if not isinstance(title, str) or not title.strip():
        raise CourseContentError(
            f"Workshop metadata {metadata_path} requires a non-empty string 'title'"
        )
    subtitle = metadata.get("subtitle", "")
    if not isinstance(subtitle, str):
        raise CourseContentError(
            f"Workshop metadata {metadata_path} field 'subtitle' must be a string"
        )

    page_paths = sorted(pages_path.glob("*.md"), key=lambda path: path.name.casefold())
    pages: list[CoursePage] = []
    seen_ids: dict[str, Path] = {}
    for page_path in page_paths:
        page = _load_page(page_path)
        if page.id in seen_ids:
            first_path = seen_ids[page.id]
            raise CourseContentError(
                f"Duplicate stable page id {page.id!r} in {first_path} and {page.source_path}"
            )
        seen_ids[page.id] = page.source_path
        pages.append(page)

    pages.sort(
        key=lambda page: (
            page.section_order,
            page.section.casefold(),
            page.order,
            page.id,
        )
    )
    return Workshop(title=title.strip(), subtitle=subtitle.strip(), pages=tuple(pages))
