"""Memory and Telegram login flood regressions for 512 MiB Render Free."""
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from engine import BrowserEngine, Session, TTL_SECONDS


@pytest.mark.asyncio
async def test_expired_context_and_chromium_are_reaped():
    engine=BrowserEngine()
    page=SimpleNamespace(url='https://example.com', is_closed=lambda: False)
    context=SimpleNamespace(close=AsyncMock(), pages=[page])
    session=Session(context=context,page=page)
    session.touched=time.monotonic()-TTL_SECONDS-5
    engine._sessions['expired']=session
    engine._browser=SimpleNamespace(close=AsyncMock())
    engine._pw=SimpleNamespace(stop=AsyncMock())
    browser=engine._browser
    pw=engine._pw
    result=await engine.reap_idle()
    assert result['active_sessions']==0
    context.close.assert_awaited_once()
    browser.close.assert_awaited_once()
    pw.stop.assert_awaited_once()
    assert engine._browser is None


@pytest.mark.asyncio
async def test_second_browser_is_refused_with_memory_hint(monkeypatch):
    monkeypatch.setattr('engine.validate_url', lambda url: url)
    engine=BrowserEngine()
    page=SimpleNamespace(url='https://example.com',is_closed=lambda: False)
    engine._sessions['existing']=Session(context=SimpleNamespace(),page=page)
    with pytest.raises(RuntimeError, match='один браузер'):
        await engine.open('https://different-domain.example/')
    assert len(engine._sessions)==1


@pytest.mark.asyncio
async def test_telegram_flood_blocks_click_and_enter_without_retry():
    engine=BrowserEngine()
    page=SimpleNamespace(url='https://web.telegram.org/k/',
                         is_closed=lambda: False, locator=lambda selector:
                         SimpleNamespace(evaluate=AsyncMock(return_value=True)),
                         keyboard=SimpleNamespace(press=AsyncMock()),
                         mouse=SimpleNamespace(click=AsyncMock(),move=AsyncMock()),
                         viewport_size={'width': 960, 'height':675})
    session=Session(context=SimpleNamespace(pages=[page]),page=page)
    engine._sessions['t']=session
    with pytest.raises(ValueError,match='PHONE_PASSWORD_FLOOD'):
        await engine.owner_control('t','key',key='Enter')
    page.keyboard.press.assert_not_awaited()
    with pytest.raises(ValueError,match='PHONE_PASSWORD_FLOOD'):
        await engine.owner_control('t','click',x=40,y=40)
    page.mouse.click.assert_not_awaited()
