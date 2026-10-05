"""Exercise credential copying and session recovery in a real browser.

Run with: uv run --frozen --with playwright python tests/browser/check_session_expiry.py
Install Chromium first with: uv run --frozen --with playwright playwright install chromium
"""

import socket
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import uvicorn
from cryptography.fernet import Fernet
from playwright.sync_api import expect, sync_playwright

from earl_workshop.auth import create_user
from earl_workshop.config import Settings
from earl_workshop.credentials import assign_vm_credential, create_vm_credential
from earl_workshop.main import create_app

ROOT = Path(__file__).resolve().parents[2]
NOTICE = "Please sign in again to continue."


def check_browser(base_url: str) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            context = browser.new_context()
            copied = []
            context.expose_binding("recordCopy", lambda _source, value: copied.append(value))
            context.add_init_script("""Object.defineProperty(navigator, 'clipboard', {
                value: {writeText: value => window.recordCopy(value)}
            });""")
            page = context.new_page()
            page.goto(f"{base_url}/login")
            page.get_by_label("Sign-in username").fill("attendee")
            page.get_by_label("Password", exact=True).fill("password")
            page.get_by_role("button", name="Sign in", exact=True).click()
            page.wait_for_url(f"{base_url}/course")

            destination = "/attendee?show_credentials=true#connection-title"
            page.goto(f"{base_url}{destination}")
            copy_button = page.get_by_role("button", name="Copy password", exact=True)
            copy_button.click()
            expect(page.locator("[data-copy-status]")).to_have_text("SSH password copied.")
            assert copied == ["vm-password"]

            page.route("**/attendee/credentials/password", lambda route: route.fulfill(status=503))
            copy_button.click()
            expect(page.locator("[data-copy-status]")).to_have_text(
                "SSH password is temporarily unavailable."
            )
            assert copied == ["vm-password"]
            assert page.url == f"{base_url}{destination}"
            page.unroute("**/attendee/credentials/password")

            # The stale dashboard stays open while its browser session disappears.
            context.clear_cookies()
            copy_button.click()
            page.wait_for_url("**/login?**")
            assert parse_qs(urlsplit(page.url).query) == {"next": [destination], "reauth": ["1"]}
            expect(page.get_by_role("status")).to_have_text(NOTICE)
            assert copied == ["vm-password"]

            page.get_by_label("Sign-in username").fill("attendee")
            page.get_by_label("Password", exact=True).fill("wrong")
            page.get_by_role("button", name="Sign in", exact=True).click()
            expect(page.get_by_role("alert")).to_have_text("Invalid username or password")
            expect(page.get_by_role("status")).to_have_text(NOTICE)
            page.get_by_label("Sign-in username").fill("attendee")
            page.get_by_label("Password", exact=True).fill("password")
            page.get_by_role("button", name="Sign in", exact=True).click()
            page.wait_for_url(f"{base_url}{destination}")
            assert copied == ["vm-password"]
            page.get_by_role("button", name="Copy password", exact=True).click()
            expect(page.locator("[data-copy-status]")).to_have_text("SSH password copied.")
            assert copied == ["vm-password", "vm-password"]
            print(
                "Passed: credential copying, 503 handling, 401 login navigation, "
                "and return after login"
            )
        finally:
            browser.close()


def main() -> None:
    with TemporaryDirectory(prefix="earl-session-browser-") as data_dir:
        key = Fernet.generate_key().decode()
        app = create_app(
            Settings(
                root_dir=ROOT,
                content_dir=ROOT / "content",
                resources_dir=ROOT / "resources",
                asset_dir=ROOT / "assets",
                data_dir=Path(data_dir),
                session_secret="browser-test-secret-which-is-long-enough",
                vm_encryption_key=key,
            )
        )
        with app.state.session_factory() as db:
            attendee = create_user(db, username="attendee", password="password")
            vm = create_vm_credential(
                db,
                host="vm.test",
                ssh_username="student",
                ssh_password="vm-password",
                encryption_key=key,
            )
            assign_vm_credential(db, attendee_id=attendee.id, vm_credential_id=vm.id)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
            server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
            thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
            thread.start()
            try:
                deadline = time.monotonic() + 10
                while not server.started:
                    if not thread.is_alive() or time.monotonic() > deadline:
                        raise RuntimeError("Browser test server failed to start")
                    time.sleep(0.05)
                check_browser(f"http://127.0.0.1:{port}")
            finally:
                server.should_exit = True
                thread.join(timeout=10)
                app.state.engine.dispose()


if __name__ == "__main__":
    main()
