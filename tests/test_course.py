from pathlib import Path

import pytest

from earl_workshop.course import CourseContentError, load_workshop, render_markdown


def write_content(tmp_path: Path, *pages: tuple[str, str]) -> Path:
    content_dir = tmp_path / "content"
    pages_dir = content_dir / "pages"
    pages_dir.mkdir(parents=True)
    (content_dir / "workshop.yml").write_text(
        "title: Test workshop\nsubtitle: Test subtitle\n", encoding="utf-8"
    )
    for filename, source in pages:
        (pages_dir / filename).write_text(source, encoding="utf-8")
    return content_dir


def page(*, page_id: str, title: str = "A page", order: int = 10, section_order: int = 10) -> str:
    return f"""---
id: {page_id}
title: {title}
order: {order}
section: Test section
section_order: {section_order}
---

Body for {page_id}.
"""


def test_placeholder_pages_load_in_deterministic_order() -> None:
    workshop = load_workshop(Path("content"))

    assert [course_page.id for course_page in workshop.pages] == [
        "orientation",
        "runtime",
        "next-steps",
    ]
    assert workshop.pages[0].resources[0].file == "examples/hello.txt"
    assert "<h2>A useful first check</h2>" in workshop.pages[0].html


def test_duplicate_stable_ids_fail_with_both_paths(tmp_path: Path) -> None:
    content_dir = write_content(
        tmp_path,
        ("one.md", page(page_id="same")),
        ("two.md", page(page_id="same")),
    )

    with pytest.raises(
        CourseContentError, match=r"Duplicate stable page id 'same'.*one\.md.*two\.md"
    ):
        load_workshop(content_dir)


@pytest.mark.parametrize(
    ("filename", "source", "message"),
    [
        (
            "missing-title.md",
            "---\nid: missing-title\norder: 10\n---\nBody\n",
            "requires a non-empty string 'title'",
        ),
        (
            "missing-order.md",
            "---\nid: missing-order\ntitle: Missing order\n---\nBody\n",
            "requires 'order' to be an required integer",
        ),
        (
            "bad-yaml.md",
            "---\nid: [broken\ntitle: Broken\norder: 10\n---\nBody\n",
            "Invalid YAML front matter",
        ),
        (
            "no-front-matter.md",
            "# Not front matter\n",
            "must begin with YAML front matter",
        ),
    ],
)
def test_invalid_content_has_actionable_error(
    tmp_path: Path, filename: str, source: str, message: str
) -> None:
    content_dir = write_content(tmp_path, (filename, source))

    with pytest.raises(CourseContentError, match=message):
        load_workshop(content_dir)


def test_unsafe_resource_path_is_rejected(tmp_path: Path) -> None:
    content_dir = write_content(
        tmp_path,
        (
            "unsafe.md",
            """---
id: unsafe
title: Unsafe
order: 10
resources:
  - file: ../secret.txt
---
Body
""",
        ),
    )

    with pytest.raises(CourseContentError, match="unsafe file path"):
        load_workshop(content_dir)


def test_raw_html_is_escaped_but_markdown_is_rendered() -> None:
    rendered = render_markdown("A <script>alert('x')</script>\n\n**safe Markdown**")

    assert "<script>" not in rendered
    assert "&lt;script&gt;alert('x')&lt;/script&gt;" in rendered
    assert "<strong>safe Markdown</strong>" in rendered


def test_page_order_changes_without_route_changes(tmp_path: Path) -> None:
    content_dir = write_content(
        tmp_path,
        ("alpha.md", page(page_id="alpha", order=20)),
        ("beta.md", page(page_id="beta", order=10)),
    )
    assert [course_page.id for course_page in load_workshop(content_dir).pages] == ["beta", "alpha"]

    alpha = content_dir / "pages" / "alpha.md"
    alpha.write_text(page(page_id="alpha", order=5), encoding="utf-8")
    assert [course_page.id for course_page in load_workshop(content_dir).pages] == ["alpha", "beta"]
