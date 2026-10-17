import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
import engine as runtime
from engine import BrowserEngine, Session

@pytest.mark.asyncio
async def test_idle_telegram_hibernation_after_save(monkeypatch):
    monkeypatch.setattr(runtime, "memory_pressure", lambda threshold=0.8: True)
    b=BrowserEngine()
    page=SimpleNamespace(url="https://web.telegram.org/k/",is_closed=lambda:False)
    ctx=SimpleNamespace(pages=[page],close=AsyncMock())
    ses=Session(context=ctx,page=page)
    ses.touched=time.monotonic()-125
    ses.last_interaction=time.monotonic()-125
    b._sessions["fixture"]=ses
    b._browser=SimpleNamespace(close=AsyncMock())
    b._pw=SimpleNamespace(stop=AsyncMock())
    b.telegram_authenticated_state=AsyncMock(return_value={"cookies":[],"origins":[]})
    b.profile_save_callback=AsyncMock()
    result=await b.hibernate_telegram_if_needed()
    assert result["hibernated"] is True
    b.profile_save_callback.assert_awaited_once()
    ctx.close.assert_awaited_once()
    assert b._sessions=={}

@pytest.mark.asyncio
async def test_failed_save_never_closes_user_browser(monkeypatch):
    monkeypatch.setattr(runtime, "memory_pressure", lambda threshold=0.8: True)
    b=BrowserEngine()
    page=SimpleNamespace(url="https://web.telegram.org/k/",is_closed=lambda:False)
    ctx=SimpleNamespace(pages=[page],close=AsyncMock())
    ses=Session(context=ctx,page=page)
    ses.touched=time.monotonic()-125
    ses.last_interaction=time.monotonic()-125
    b._sessions["fixture"]=ses
    b._browser=SimpleNamespace(close=AsyncMock())
    b.telegram_authenticated_state=AsyncMock(return_value={"cookies":[],"origins":[]})
    b.profile_save_callback=AsyncMock(side_effect=RuntimeError("unavailable"))
    result=await b.hibernate_telegram_if_needed()
    assert result["reason"]=="checkpoint_failed"
    assert "fixture" in b._sessions
    ctx.close.assert_not_awaited()
