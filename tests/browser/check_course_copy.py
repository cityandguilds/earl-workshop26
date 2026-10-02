"""Exercise real clipboard writes, including an ordinary HTTP origin.

Run with: uv run --with playwright python tests/browser/check_course_copy.py
Install Chromium first with: uv run --with playwright playwright install chromium
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from playwright.sync_api import sync_playwright

from earl_workshop.course import render_markdown

STATIC = Path(__file__).resolve().parents[2] / "src/earl_workshop/static"
LESSON = render_markdown("```sql\nSELECT 'hello <world>' AS message;\n\nSELECT 42;\n```")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/static/course.js":
            body = (STATIC / "course.js").read_bytes()
            content_type = "text/javascript"
        else:
            body = (
                '<!doctype html><meta charset="utf-8">'
                f'<div class="markdown-body">{LESSON}</div>'
                '<script src="/static/course.js" defer></script>'
            ).encode()
            content_type = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        pass


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port
    secure_origin = f"http://127.0.0.1:{port}"
    http_origin = f"http://workshop.test:{port}"
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                args=["--host-resolver-rules=MAP workshop.test 127.0.0.1", "--no-proxy-server"]
            )
            context = browser.new_context()
            context.grant_permissions(["clipboard-read", "clipboard-write"], origin=secure_origin)
            reader = context.new_page()
            reader.goto(secure_origin)
            page = context.new_page()

            for mode in ("modern API", "HTTP", "API denied"):
                page.goto(http_origin if mode == "HTTP" else secure_origin)
                if mode == "HTTP":
                    assert page.evaluate("window.isSecureContext") is False
                    assert page.evaluate("typeof navigator.clipboard") == "undefined"
                if mode == "API denied":
                    page.evaluate("""() => {
                        navigator.clipboard.writeText = async () => {
                            throw new Error('Permission denied');
                        };
                    }""")
                expected = page.locator("pre code").text_content()
                copy = page.get_by_role("button", name="Copy code block 1", exact=True)
                page.bring_to_front()
                copy.click()
                page.get_by_role("status").filter(has_text="Code copied.").wait_for()
                assert copy.text_content() == "Copied!"
                assert copy.evaluate("el => el === document.activeElement")
                assert page.locator("textarea").count() == 0
                reader.bring_to_front()
                assert reader.evaluate("navigator.clipboard.readText()") == expected, mode
                print(f"PASS: {mode} copied the actual code to the clipboard")

            page.goto(http_origin)
            page.evaluate("document.execCommand = () => false")
            page.bring_to_front()
            page.get_by_role("button", name="Copy code block 1", exact=True).click()
            page.get_by_role("status").filter(has_text="Your browser blocked copying.").wait_for()
            assert page.evaluate("window.getSelection().toString()")
            assert page.locator("textarea").count() == 0
            print("PASS: blocked copying is reported without claiming success")
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    main()
