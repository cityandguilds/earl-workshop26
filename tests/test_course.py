import re
from html import unescape
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


def test_workshop_content_loads_in_deterministic_order() -> None:
    workshop = load_workshop(Path("content"))

    assert [course_page.id for course_page in workshop.pages] == [
        "orientation",
        "cloud-computing",
        "linux",
        "unix",
        "install-software",
        "postgresql-open-data",
        "postgresql-open-data-solutions",
        "shiny-server-introduction",
        "shiny-server-deployment",
        "fastapi-introduction",
        "fastapi-flights",
        "quarto-flights-report",
        "containers-docker-introduction",
        "shinyproxy-introduction",
        "next-steps",
        "postgresql-open-data-instructor",
        "fastapi-flights-instructor",
    ]
    assert list(dict.fromkeys(section.name for section in workshop.sections)) == [
        "Getting started",
        "PostgreSQL",
        "Shiny",
        "FastAPI",
        "Quarto",
        "Docker and ShinyProxy",
        "Next steps",
        "Instructor resources",
    ]
    assert "<h2>Workshop learning outcomes</h2>" in workshop.pages[0].html


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


@pytest.mark.parametrize(
    "language",
    [
        "bash",
        "python",
        "r",
        "R",
        "{r}",
        "sql",
        "yaml",
        "dockerfile",
        "nginx",
        "json",
        "ini",
        "powershell",
    ],
)
def test_code_highlighting_preserves_code_text(language: str) -> None:
    code = 'value < 2 & "example"\n    indented_value\n'
    rendered = render_markdown(f"```{language}\n{code}```")

    code_html = re.search(r"<code[^>]*>(.*?)</code>", rendered, re.DOTALL)
    assert code_html is not None
    assert '<span class="' in code_html.group(1)
    assert unescape(re.sub(r"<[^>]+>", "", code_html.group(1))) == code
    normalised = language.strip("{}").lower()
    assert f'<span class="code-language">.{normalised}</span>' in rendered
    assert f'class="language-{normalised}"' in rendered


@pytest.mark.parametrize("language", ["", "text", "not-a-language"])
def test_plain_code_is_not_guessed_or_rendered_as_html(language: str) -> None:
    rendered = render_markdown(f"```{language}\n<script>alert('x')</script>\n```")

    code_html = re.search(r"<code[^>]*>(.*?)</code>", rendered, re.DOTALL)
    assert code_html is not None
    assert '<span class="' not in code_html.group(1)
    assert '<span class="code-language">Plain text</span>' in rendered
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered


def test_markdown_renders_headings_lists_tables_and_quotes() -> None:
    rendered = render_markdown(
        "## Heading\n\n- **Bold** and `inline code`\n\n> A quote\n\n"
        "| Name | Value |\n| --- | --- |\n| Example | 42 |"
    )
    for markup in [
        "<h2>Heading</h2>",
        "<ul>",
        "<strong>Bold</strong>",
        "<code>inline code</code>",
        "<blockquote>",
        "<table>",
        "<td>42</td>",
    ]:
        assert markup in rendered


def test_quarto_fence_normalisation_does_not_change_nested_example() -> None:
    rendered = render_markdown("````text\n```{r}\nx <- 1\n```\n````")
    assert "```{r}" in rendered


def test_blockquotes_keep_html_escaped() -> None:
    rendered = render_markdown(
        "> **Note:** <script>alert('x')</script>\n\n> > Nested quote\n\n&gt; literal"
    )
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "<strong>Note:</strong>" in rendered
    assert rendered.count("<blockquote>") == 3
    assert "<p>&gt; literal</p>" in rendered


@pytest.mark.parametrize("language", ["sql", "bash", "text", ""])
def test_code_preserves_tabs_blank_lines_and_literal_entities(language: str) -> None:
    source = '\n\tSELECT "<example> &amp;";\n\n'
    rendered = render_markdown(f"```{language}\n{source}```")
    code_html = re.search(r"<code[^>]*>(.*?)</code>", rendered, re.DOTALL)
    assert code_html is not None
    assert unescape(re.sub(r"<[^>]+>", "", code_html.group(1))) == source


def test_code_fences_work_inside_lists_and_blockquotes() -> None:
    rendered = render_markdown(
        "3. Run the query:\n\n   ```sql\n   SELECT 42;\n   ```\n\n"
        "4. Read the result.\n\n> ```bash\n> echo 'done'\n> ```\n"
    )
    assert '<ol start="3">' in rendered
    assert re.search(r'<li>.*?<figure[^>]+data-language="sql".*?</figure>.*?</li>', rendered, re.S)
    assert re.search(r'<blockquote>.*?<figure[^>]+data-language="bash"', rendered, re.S)
    assert rendered.count('class="code-block"') == 2


def test_markdown_handles_autolinks_without_allowing_raw_html_or_script_links() -> None:
    rendered = render_markdown(
        '<https://example.org>\n\n<div onclick="alert(1)">Example</div>\n\n'
        "[unsafe](javascript:alert(1))\n\n```unknown\n<script>alert(1)</script>\n```"
    )
    assert '<a href="https://example.org">' in rendered
    assert '<div onclick="' not in rendered
    assert "<script>" not in rendered
    assert 'href="javascript:' not in rendered


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
