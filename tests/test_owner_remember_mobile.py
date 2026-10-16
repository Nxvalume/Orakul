"""Opt-in, time-bounded owner access, private frame latency and horizontal controls."""
from types import SimpleNamespace

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

import chat_secure
from chat_ui import CHAT_HTML
from engine import BrowserEngine, Session


SID_A = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
SID_B = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
ORIGIN = "https://chatgpt.com"


class FakeEngine:
    def __init__(self):
        self.mode = {}
        self.calls = []

    async def owner_set_private(self, sid, enabled):
        self.calls.append((sid, enabled))
        self.mode[sid] = enabled
        return {"private_mode": enabled}

    def get(self, sid, *, owner=False):
        assert owner
        return SimpleNamespace(private_mode=self.mode.get(sid, False))


def client_for_owner(monkeypatch):
    monkeypatch.setenv("MINIFISH_SECRET", "Y" * 64)
    monkeypatch.setattr(chat_secure, "allowed_attempt", lambda ip: True)
    monkeypatch.setattr(chat_secure, "verify_password", lambda password, ip: password == "local-test-only")
    engine = FakeEngine()
    app = Starlette(routes=[Route("/chat/secure/{operation}",
                                   chat_secure.create_owner_routes(engine),
                                   methods=["GET", "POST", "OPTIONS"])])
    return TestClient(app), engine


def test_owner_can_opt_in_remember_for_next_browser_session_but_not_leak_password(monkeypatch):
    client, engine = client_for_owner(monkeypatch)
    with client:
        unlock = client.post("/chat/secure/unlock", headers={"origin": ORIGIN}, json={
            "session_id": SID_A, "owner_password": "local-test-only",
            "remember_device": True})
        assert unlock.status_code == 200
        body = unlock.json()
        remembered = body["remember_token"]
        assert "local-test-only" not in str(body)
        assert body["remember_seconds"] == 24 * 3600
        assert chat_secure._valid_remember(remembered, ORIGIN)
        assert not chat_secure._valid_remember(remembered, "https://chat.openai.com")
        assert not chat_secure._valid_remember(remembered+"invalid", ORIGIN)

        resumed = client.post("/chat/secure/resume", headers={
            "origin": ORIGIN, "x-minifish-device": remembered},
            json={"session_id": SID_B})
        assert resumed.status_code == 200, resumed.text
        assert chat_secure._valid(resumed.json()["token"], SID_B, ORIGIN)
        assert resumed.json()["private_mode"] is True
        assert engine.calls == [(SID_A, True), (SID_B, True)]

        wrong_origin = client.post("/chat/secure/resume", headers={
            "origin": "https://chat.openai.com",
            "x-minifish-device": remembered}, json={"session_id": SID_A})
        assert wrong_origin.status_code == 401
        wrong_token = client.post("/chat/secure/resume",
            headers={"origin": ORIGIN, "x-minifish-device": "invalid"},
            json={"session_id": SID_A})
        assert wrong_token.status_code == 401


def test_remember_token_only_explicit_opt_in_and_fails_after_one_day(monkeypatch):
    client, engine = client_for_owner(monkeypatch)
    with client:
        res = client.post("/chat/secure/unlock", headers={"origin": ORIGIN}, json={
            "session_id": SID_A, "owner_password": "local-test-only"})
        assert res.status_code == 200
        assert "remember_token" not in res.json()
        remembered = chat_secure._seal_remember(ORIGIN)
        now = chat_secure.time.time()
        monkeypatch.setattr(chat_secure.time, "time", lambda: now + 24*3600 + 60)
        assert not chat_secure._valid_remember(remembered, ORIGIN)
        expired = client.post("/chat/secure/resume", headers={
            "origin": ORIGIN, "x-minifish-device": remembered},
            json={"session_id": SID_B})
        assert expired.status_code == 401


def test_mobile_live_view_repeats_without_overlap_and_supports_four_scroll_buttons():
    assert "id=\"left\"" in CHAT_HTML and "id=\"right\"" in CHAT_HTML
    assert "id=\"secureLeft\"" in CHAT_HTML and "id=\"secureRight\"" in CHAT_HTML
    assert "axis:'horizontal'" in CHAT_HTML
    assert "secureFrameBusy=true;" in CHAT_HTML
    assert "finally{secureFrameBusy=false}" in CHAT_HTML
    assert "securePoll=setInterval(()=>{void secureFrame()},1200);" in CHAT_HTML
    assert "void Promise.allSettled([secureFields(),refreshSecureTabs()]);" in CHAT_HTML
    assert "operation==='resume'" in CHAT_HTML
    assert "x-minifish-device" in CHAT_HTML.lower()
    assert "remember_device:$('rememberOwner').checked" in CHAT_HTML


@pytest.mark.asyncio
async def test_horizontal_wheel_moves_page_on_real_chromium_without_navigating():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=['--disable-dev-shm-usage'])
        try:
            ctx = await browser.new_context(viewport={"width": 390, "height": 730})
            page = await ctx.new_page()
            await page.set_content("""<style>body{margin:0}main{width:1800px;height:1200px}
              </style><main></main>""")
            eng = BrowserEngine()
            eng._sessions[SID_A] = Session(context=ctx, page=page)
            pos = await page.evaluate("window.scrollX")
            result = await eng.scroll(SID_A, pixels=420, axis="horizontal")
            await page.wait_for_function("window.scrollX > 0", timeout=3000)
            assert await page.evaluate("window.scrollX") > pos
            assert result["axis"] == "horizontal"
            with pytest.raises(ValueError):
                await eng.scroll(SID_A, pixels=300, axis="diagonal")
        finally:
            await browser.close()
