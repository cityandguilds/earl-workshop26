"""CommonMark lesson rendering with labelled, highlighted code examples."""

from collections.abc import Sequence
from html import escape

from markdown_it import MarkdownIt
from markdown_it.renderer import RendererHTML
from markdown_it.token import Token
from markdown_it.utils import EnvType, OptionsDict
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound


def _code_block(source: str, info: str = "") -> str:
    # Accept both ordinary fences (R, sql) and Quarto chunks ({r}, {r setup}).
    language = (
        info.split(maxsplit=1)[0].strip("{}.").rstrip(",").lower() if info.strip() else "text"
    )
    language = {"sh": "bash", "shell": "bash", "py": "python", "plaintext": "text"}.get(
        language, language
    )
    try:
        lexer = get_lexer_by_name(language, stripnl=False, ensurenl=False, tabsize=0)
    except ClassNotFound:
        language = "text"
        lexer = get_lexer_by_name("text", stripnl=False, ensurenl=False, tabsize=0)

    code = highlight(source, lexer, HtmlFormatter(nowrap=True))
    safe_language = escape(language, quote=True)
    label = "Plain text" if language == "text" else f".{safe_language}"
    return (
        f'<figure class="code-block" data-language="{safe_language}">'
        '<figcaption class="code-toolbar">'
        f'<span class="code-language">{label}</span>'
        '<span class="code-copy-status" role="status"></span>'
        '<button class="code-copy-button" type="button" hidden>'
        '<svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="1.7">'
        '<rect x="8" y="8" width="12" height="12" rx="2"/>'
        '<path d="M16 8V4H4v12h4"/></svg>'
        '<span class="code-copy-label">Copy</span></button></figcaption>'
        f'<pre class="code-content" tabindex="0" aria-label="{safe_language} code">'
        f'<code class="language-{safe_language}">{code}</code></pre></figure>\n'
    )


class LessonRenderer(RendererHTML):
    def fence(self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType) -> str:
        return _code_block(tokens[idx].content, tokens[idx].info)

    def code_block(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        return _code_block(tokens[idx].content)


def render_markdown(markdown_source: str) -> str:
    """Render CommonMark with tables and literal HTML, preserving code whitespace."""

    renderer = MarkdownIt("commonmark", {"html": False}, renderer_cls=LessonRenderer)
    renderer.enable(["table", "strikethrough"])
    return renderer.render(markdown_source)
