"""Telegram locale files must never replace the active Telegram Web screen.

All values are synthetic, no real account or OTP is accessed.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from playwright.async_api import async_playwright

import engine
from engine import BrowserEngine


@pytest.mark.asyncio
async def test_accidental_telegram_locale_document_returns_to_app(monkeypatch):
    monkeypatch.setattr(engine, 'memory_pressure', lambda: False)
    monkeypatch.setattr(engine, 'validate_url', lambda url: url)
    browser_engine = BrowserEngine()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=['--disable-dev-shm-usage'])
        try:
            context = await browser.new_context(service_workers='block')
            async def fixture_route(route):
                # A single catch-all route intercepts *redirected* requests too:
                # no test browser is allowed to contact real Telegram endpoints.
                if route.request.url.split('?', 1)[0] == 'https://web.telegram.org/k/':
                    await route.fulfill(
                        status=200, content_type='text/html',
                        body='<title>Telegram fixture</title><h1>Telegram home</h1>')
                else:
                    await browser_engine._route(route)
            await context.route('**/*', fixture_route)
            page = await context.new_page()
            await page.goto('https://web.telegram.org/js/locales/en-us.json')
            assert page.url == 'https://web.telegram.org/k/'
            assert await page.locator('h1').inner_text() == 'Telegram home'
            await context.close()
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_telegram_locale_json_fetch_keeps_working(monkeypatch):
    monkeypatch.setattr(engine, 'memory_pressure', lambda: False)
    monkeypatch.setattr(engine, 'validate_url', lambda url: url)
    url = 'https://web.telegram.org/js/locales/en-us.json'
    route = SimpleNamespace(
        request=SimpleNamespace(url=url, resource_type='fetch',
                                is_navigation_request=lambda: False),
        continue_=AsyncMock(), fulfill=AsyncMock(), abort=AsyncMock())
    await BrowserEngine()._route(route)
    route.continue_.assert_awaited_once()
    route.fulfill.assert_not_awaited()
    route.abort.assert_not_awaited()


@pytest.mark.asyncio
async def test_json_documents_on_other_websites_are_not_redirected(monkeypatch):
    monkeypatch.setattr(engine, 'memory_pressure', lambda: False)
    monkeypatch.setattr(engine, 'validate_url', lambda url: url)
    route = SimpleNamespace(
        request=SimpleNamespace(url='https://example.com/data.json',
                                resource_type='document',
                                is_navigation_request=lambda: True),
        continue_=AsyncMock(), fulfill=AsyncMock(), abort=AsyncMock())
    await BrowserEngine()._route(route)
    route.continue_.assert_awaited_once()
    route.fulfill.assert_not_awaited()


def test_inline_android_window_has_safe_one_tap_telegram_recovery():
    from chat_ui import CHAT_HTML, CHAT_UI_URI
    assert 'id="telegramHome"' in CHAT_HTML
    assert "$('telegramHome').onclick=()=>act('browser_goto'" in CHAT_HTML
    assert "url:'https://web.telegram.org/k/'" in CHAT_HTML
    assert CHAT_UI_URI == 'ui://minifish/browser-v18.html'
