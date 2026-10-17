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
            context = await browser.new_context()
            async def app_home(route):
                await route.fulfill(status=200, content_type='text/html',
                                    body='<title>Telegram fixture</title><h1>Telegram home</h1>')
            await context.route('https://web.telegram.org/k/', app_home)
            await context.route('https://web.telegram.org/js/locales/*.json', browser_engine._route)
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
