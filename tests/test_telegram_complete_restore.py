"""Synthetic Telegram-origin persistence regression (no real user credentials)."""
import pytest
from playwright.async_api import async_playwright
from engine import BrowserEngine, Session
from chat_ui import CHAT_HTML

_FAKE_LOGIN = """<!doctype html><html><body><script>
  document.addEventListener('DOMContentLoaded', () => {
    document.body.innerHTML = (
      sessionStorage.getItem('test-only-session-key') === 'fixture' &&
      localStorage.getItem('test-only-local-key') === 'fixture'
    ) ? '<div id="column-left">Synthetic authenticated UI</div>' :
        '<div id="auth-pages">Synthetic sign-in UI</div>';
  });
</script></body></html>"""


@pytest.mark.asyncio
async def test_telegram_owner_sessionstorage_restores_with_indexeddb_profile(monkeypatch):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True, args=["--disable-dev-shm-usage"])
        source = None
        dest = None
        try:
            source = await browser.new_context()
            async def fake_page(route):
                await route.fulfill(status=200, content_type='text/html', body=_FAKE_LOGIN)
            await source.route("https://web.telegram.org/**", fake_page)
            page = await source.new_page()
            await page.goto("https://web.telegram.org/k/")
            await page.evaluate("""() => {
              sessionStorage.setItem('test-only-session-key','fixture');
              localStorage.setItem('test-only-local-key','fixture');
              document.body.innerHTML='<div id="column-left">Synthetic authenticated UI</div>';
            }""")
            engine = BrowserEngine()
            sid = "fictional-owner"
            engine._sessions[sid] = Session(
                context=source, page=page, private_mode=False)
            state = await engine.telegram_authenticated_state(sid)
            assert state is not None
            assert state["_minifish_session_storage"] == {
                "https://web.telegram.org": {"test-only-session-key": "fixture"}}
            assert state["origins"]

            dest = BrowserEngine()
            dest._browser = browser
            async def launched():
                pass
            async def mock_route(route):
                await route.fulfill(status=200, content_type='text/html', body=_FAKE_LOGIN)
            dest._launch = launched
            dest._route = mock_route
            monkeypatch.setattr("engine.validate_url", lambda *_args: None)
            opened = await dest.open("https://web.telegram.org/k/",
                                     storage_state=state, profile_name="telegram")
            restored = dest.get(opened["session_id"])
            assert await restored.page.locator("#column-left").is_visible()
            assert await dest.telegram_logged_in(opened["session_id"])
            assert (await restored.page.evaluate(
                "sessionStorage.getItem('test-only-session-key')")) == "fixture"
            assert (await restored.page.evaluate(
                "localStorage.getItem('test-only-local-key')")) == "fixture"
        finally:
            if dest is not None:
                for session in dest._sessions.values():
                    await session.context.close()
            if source is not None:
                await source.close()
            await browser.close()


def test_telegram_service_workers_are_enabled_only_for_telegram():
    import inspect
    from engine import BrowserEngine
    code = inspect.getsource(BrowserEngine.open)
    assert "service_workers='allow' if is_telegram else 'block'" in code
    assert "location.origin !== 'https://web.telegram.org'" in code
