"""Render 512-MiB guard must shed optional media before Chromium is killed."""
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
import engine as engine_module
from engine import BrowserEngine, Session


@pytest.mark.asyncio
async def test_memory_pressure_skips_jpeg_and_png_without_destroying_session(monkeypatch):
    monkeypatch.setattr(engine_module, 'memory_pressure', lambda: True)
    page = SimpleNamespace(
        url='https://example.com/', is_closed=lambda: False,
        screenshot=AsyncMock(return_value=b'fake-image'))
    browser = BrowserEngine()
    browser._sessions['safe'] = Session(context=SimpleNamespace(), page=page)
    with pytest.raises(TimeoutError, match='ограничение памяти'):
        await browser.live_jpeg('safe')
    with pytest.raises(TimeoutError, match='ограничение памяти'):
        await browser.screenshot('safe')
    page.screenshot.assert_not_awaited()
    assert 'safe' in browser._sessions
    assert browser._sessions['safe'].touched <= time.monotonic()


@pytest.mark.asyncio
async def test_memory_pressure_aborts_only_optional_assets(monkeypatch):
    monkeypatch.setattr(engine_module, 'memory_pressure', lambda: True)
    monkeypatch.setattr(engine_module, 'validate_url', lambda *_: None)
    browser = BrowserEngine()
    image_route = SimpleNamespace(
        request=SimpleNamespace(url='https://example.com/logo.png',
                                resource_type='image'),
        abort=AsyncMock(), continue_=AsyncMock())
    await browser._route(image_route)
    image_route.abort.assert_awaited_once_with('blockedbyclient')
    image_route.continue_.assert_not_awaited()
    text_route = SimpleNamespace(
        request=SimpleNamespace(url='https://example.com/data.json',
                                resource_type='fetch'),
        abort=AsyncMock(), continue_=AsyncMock())
    await browser._route(text_route)
    text_route.continue_.assert_awaited_once()
    text_route.abort.assert_not_awaited()
