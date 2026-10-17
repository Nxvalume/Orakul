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


@pytest.mark.asyncio
async def test_gc_is_skipped_below_memory_threshold(monkeypatch):
    monkeypatch.setattr(engine_module, 'memory_pressure', lambda: False)
    browser = BrowserEngine()
    result = await browser.reclaim_chromium_memory()
    assert result == {'attempted': False}


@pytest.mark.asyncio
async def test_gc_runs_without_closing_user_session(monkeypatch):
    monkeypatch.setattr(engine_module, 'memory_pressure', lambda: True)
    cdp = SimpleNamespace(send=AsyncMock(), detach=AsyncMock())
    context = SimpleNamespace(new_cdp_session=AsyncMock(return_value=cdp))
    page = SimpleNamespace(is_closed=lambda: False)
    browser = BrowserEngine()
    browser._sessions['owned'] = Session(context=context, page=page)
    result = await browser.reclaim_chromium_memory()
    assert result == {'attempted': True, 'pages': 1}
    cdp.send.assert_awaited_once_with('HeapProfiler.collectGarbage')
    cdp.detach.assert_awaited_once()
    assert 'owned' in browser._sessions


@pytest.mark.asyncio
async def test_compact_android_frame_uses_jpeg_at_css_scale(monkeypatch):
    monkeypatch.setattr(engine_module, 'memory_pressure', lambda threshold=0.80: False)
    page = SimpleNamespace(is_closed=lambda:False,
                           screenshot=AsyncMock(return_value=b'jpeg-fixture'))
    browser=BrowserEngine()
    browser._sessions['frame']=Session(context=SimpleNamespace(),page=page)
    result=await browser.screenshot_jpeg('frame')
    assert result == b'jpeg-fixture'
    page.screenshot.assert_awaited_once_with(
        type='jpeg', quality=42, scale='css', full_page=False,
        timeout=engine_module.TIMEOUT_MS)


@pytest.mark.asyncio
async def test_compact_android_frame_refuses_only_critical_memory(monkeypatch):
    monkeypatch.setattr(engine_module, 'memory_pressure',
                        lambda threshold=0.80: threshold <= 0.80)
    page=SimpleNamespace(is_closed=lambda:False,
                         screenshot=AsyncMock(return_value=b'jpeg'))
    browser=BrowserEngine()
    browser._sessions['frame']=Session(context=SimpleNamespace(),page=page)
    assert await browser.screenshot_jpeg('frame') == b'jpeg'
    page.screenshot.assert_awaited_once()
