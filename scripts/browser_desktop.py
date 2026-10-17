"""Synthetic browser acceptance for the Mac app's unprivileged web content.

Uses Chromium on the development host, not WKWebView or physical Mac hardware.
The query parameters are UI hints; all authentication and imports use ordinary
backend APIs. No personal files, native process bridge or model calls are used.
"""
from __future__ import annotations

import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path


PASSWORD = "synthetic-desktop-password-123"


def fixture() -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Aurora/decisao.md", "# Decisão Aurora\n\nDecisão: revisar com uma pessoa antes de publicar.")
        archive.writestr("Aurora/pendencia.md", "# Pendência Aurora\n\nPendente: conferir a experiência antes do convite.")
        archive.writestr("Aurora/.obsidian/app.json", '{"plugins": []}')
    return stream.getvalue()


def run_mode(browser, mode: str, width: int, selected_mode: str | None = None) -> dict:
    from playwright.sync_api import expect

    with socket.socket() as bound:
        bound.bind(("127.0.0.1", 0))
        port = bound.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    hint = selected_mode or ("local" if mode == "unknown" else mode)
    address = base + f"/?mia_client=mac&mia_mode={hint}"
    with tempfile.TemporaryDirectory(prefix="mia-desktop-synthetic-") as data:
        env = {**os.environ, "MIA_DATA_DIR": data, "MIA_AI_ENABLED": "false",
               "MIA_AI_BASE_URL": "", "MIA_AI_API_KEY": "", "MIA_AI_MODEL": "",
               "MIA_COOKIE_SECURE": "false", "MIA_INSTALLATION_MODE": mode}
        env.pop("MIA_OPERATIONS_ROOT", None)
        log_path = Path(data) / "server.log"
        with log_path.open("wb") as log:
            server = subprocess.Popen([sys.executable, "-m", "uvicorn", "mia.app:app",
                                       "--host", "127.0.0.1", "--port", str(port)],
                                      env=env, stdout=log, stderr=log)
            context = None
            try:
                for _ in range(100):
                    if server.poll() is not None:
                        raise AssertionError(log_path.read_text()[-4000:])
                    try:
                        urllib.request.urlopen(base + "/health", timeout=1).close()
                        break
                    except OSError:
                        time.sleep(.1)
                else:
                    raise AssertionError("Synthetic desktop backend did not become ready")
                context = browser.new_context(viewport={"width": width, "height": 950})
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(address)
                expect(page.locator("body.desktop-client")).to_be_visible()
                expect(page.locator("#setup-form")).to_be_visible()
                destination = "Destino a confirmar" if mode == "unknown" else "Dados neste computador" if mode == "local" else "Dados no seu servidor"
                expect(page.locator("#desktop-destination")).to_have_text(destination)
                assert page.request.get(base + "/api/experience").status == 401, "Desktop hint must not authenticate"
                assert page.get_by_label("Primeira área", exact=True).count() == 0
                page.get_by_label("Seu nome", exact=True).fill("Pessoa Sintética")
                page.locator("#setup-form input[name=password]").fill(PASSWORD)
                page.get_by_role("button", name="Criar minha Mia", exact=True).click()
                if mode in {"local", "remote"} and hint != mode:
                    expect(page.locator("#confirm-desktop-destination")).to_be_visible()
                    assert page.locator("#migration-form").count() == 0
                    assert page.request.get(base + "/api/experience").json()["location"]["mode"] == mode
                    page.locator("#confirm-desktop-destination").click()
                expect(page.locator("#migration-form")).to_be_visible()
                expect(page.locator(".journey li")).to_have_count(3)
                assert len(page.locator(".journey").evaluate("element => getComputedStyle(element).gridTemplateColumns.split(' ')")) == 3
                if mode == "unknown":
                    # A spoofed desktop/local URL cannot declare or move storage.
                    expect(page.locator("#location-form")).to_be_visible()
                    expect(page.locator("#migration-form button[type=submit]")).to_be_disabled()
                    assert page.request.get(base + "/api/experience").json()["location"]["mode"] == "unknown"
                    page.locator("#location-form select").select_option("local")
                    page.locator("#location-form button[type=submit]").click()
                    expect(page.locator("#desktop-destination")).to_have_text("Dados neste computador")
                else:
                    assert page.locator("#location-form").count() == 0
                expect(page.locator("#migration-form button[type=submit]")).to_be_enabled()
                page.locator("#migration-form input[name=file]").set_input_files(
                    {"name": "synthetic-desktop.zip", "mimeType": "application/zip", "buffer": fixture()})
                page.get_by_role("button", name="Conferir material", exact=True).click()
                expect(page.locator("#confirm-migration")).to_be_visible(timeout=20000)
                assert page.request.get(base + "/api/documents").json() == [], "Review is not authorization"
                page.locator("#confirm-migration").click()
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    jobs = page.request.get(base + "/api/migrations").json()
                    if jobs[0]["state"] in {"completed", "partial"}:
                        break
                    assert jobs[0]["state"] != "failed", jobs[0]
                    time.sleep(.1)
                else:
                    raise AssertionError("Synthetic import did not finish")
                documents = page.request.get(base + "/api/documents").json()
                assert len(documents) == 2, documents
                page.locator("#guide-next").click()
                expect(page.locator("#focus-form")).to_be_visible()
                assert page.locator("#ai-form").count() == 0, "Model setup should follow first value"
                assert page.request.get(base + "/api/onboarding").json()["step"] == 2
                page.locator("#focus-title").fill("Retomar o projeto Aurora")
                page.locator("#focus-form input[name=source_ids]").first.check()
                page.locator("#guide-next").click()
                expect(page.get_by_role("heading", name="2 fontes disponíveis para usar.")).to_be_visible()
                page.locator("#guide-back").click()
                expect(page.locator("#focus-title")).to_have_value("Retomar o projeto Aurora")
                page.locator("#guide-back").click()
                expect(page.locator("#migration-form")).to_be_visible()
                page.locator("#guide-next").click()
                expect(page.locator("#focus-form")).to_be_visible()
                page.locator("#guide-next").click()
                expect(page.get_by_role("heading", name="2 fontes disponíveis para usar.")).to_be_visible()
                page.locator("#guide-next").click()
                expect(page.get_by_role("heading", name="Retomar o projeto Aurora", exact=True)).to_be_visible()
                expect(page.locator(".source-card")).to_have_count(1)
                page.locator(".source-card button[data-document]").click()
                expect(page.locator("#source-dialog")).to_contain_text("Aurora")
                page.get_by_role("button", name="Fechar fonte", exact=True).click()
                assert page.request.get(base + "/api/tasks").json() == []
                assert page.request.get(base + "/api/runs").json() == []
                assert not page.request.get(base + "/api/ai/config").json()["enabled"]
                page.reload()
                expect(page.get_by_role("heading", name="Retomar o projeto Aurora", exact=True)).to_be_visible()
                screenshots = Path(tempfile.gettempdir()) / "mia-desktop-review"
                screenshots.mkdir(exist_ok=True)
                page.screenshot(path=str(screenshots / f"today-{mode}-{hint}-{width}.png"), full_page=True)
                page.locator("#logout").click()
                expect(page.locator("#login-form")).to_be_visible()
                assert page.request.get(base + "/api/documents").status == 401
                page.locator("#login-form input[name=password]").fill(PASSWORD)
                page.get_by_role("button", name="Entrar", exact=True).click()
                expect(page.get_by_role("heading", name="Retomar o projeto Aurora", exact=True)).to_be_visible()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Desktop window overflow"
                page.locator("[data-view=settings]").click()
                expect(page.get_by_text("No menu Mia, abra Minha instalação para conexão, cópia de recuperação e atualização.", exact=True)).to_be_visible()
                assert page.locator("#system-operations").count() == 0
                assert page.locator("#settings-location").count() == 0
                page.locator("#system-ai").click()
                expect(page.locator("#ai-form")).to_be_visible()
                assert page.request.get(base + "/api/runs").json() == []
                page.goto(base + "/?mia_client=mac&mia_mode=invalid")
                expect(page.get_by_role("heading", name="Retomar o projeto Aurora", exact=True)).to_be_visible()
                assert page.locator("body.desktop-client").count() == 0
                assert page.locator("#desktop-destination").count() == 0
                assert not errors, errors
                return {"backend_mode": mode, "selected_mode": hint, "window_width": width, "sources": 2,
                        "model_calls": 0, "first_value": "confirmed focus with original sources"}
            finally:
                if context:
                    context.close()
                if server.poll() is None:
                    server.terminate()
                    try:
                        server.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        server.kill()
                        server.wait(timeout=10)


def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=os.environ.get("MIA_BROWSER_EXECUTABLE"))
        try:
            results = [run_mode(browser, mode, width, selected) for mode, width, selected in
                       [("local", 1180, None), ("remote", 820, None), ("unknown", 390, None),
                        ("remote", 980, "local")]]
            print(json.dumps({"corpus": "synthetic-only", "browser": "Chromium, not native WKWebView",
                              "screenshots": str(Path(tempfile.gettempdir()) / "mia-desktop-review"),
                              "results": results, "checks": ["normal authentication", "unknown destination gate", "destination mismatch acknowledgment", "invalid hint ignored",
                              "review before import", "3-step first value", "back navigation", "persistent focus",
                              "original source", "logout/login", "optional model setup", "responsive window"]}, ensure_ascii=False))
        finally:
            browser.close()


if __name__ == "__main__":
    main()
