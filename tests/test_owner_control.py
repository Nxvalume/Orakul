"""Regression tests for owner-only interactive login handoff."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from engine import BrowserEngine, Session


def mock_browser():
    page = SimpleNamespace(
        viewport_size={'width': 1280, 'height': 900},
        url='https://example.com/login',
        mouse=SimpleNamespace(click=AsyncMock()),
        keyboard=SimpleNamespace(insert_text=AsyncMock(), press=AsyncMock()),
        is_closed=lambda: False,
    )
    context = SimpleNamespace(pages=[page])
    engine = BrowserEngine()
    engine._sessions['session'] = Session(context=context, page=page)
    return engine, page


@pytest.mark.asyncio
async def test_owner_click_is_bounded():
    engine, page = mock_browser()
    assert (await engine.owner_control('session', 'click', x=64, y=75))['ok']
    page.mouse.click.assert_awaited_once_with(64.0, 75.0)
    with pytest.raises(ValueError):
        await engine.owner_control('session', 'click', x=-1, y=2)
    with pytest.raises(ValueError):
        await engine.owner_control('session', 'click', x=0, y=901)


@pytest.mark.asyncio
async def test_owner_typing_never_echoes_secrets():
    engine, page = mock_browser()
    secret = 'sample-secret-not-a-real-password'
    result = await engine.owner_control('session', 'type', text=secret)
    assert secret not in str(result)
    assert secret not in engine._sessions['session'].last_action
    page.keyboard.insert_text.assert_awaited_once_with(secret)


@pytest.mark.asyncio
async def test_owner_keys_whitelisted():
    engine, page = mock_browser()
    await engine.owner_control('session', 'key', key='Tab')
    page.keyboard.press.assert_awaited_once_with('Tab')
    with pytest.raises(ValueError):
        await engine.owner_control('session', 'key', key='ControlOrMeta+Shift+I')
    with pytest.raises(ValueError):
        await engine.owner_control('session', 'unknown')


@pytest.mark.asyncio
async def test_owner_control_requires_known_session():
    engine, _ = mock_browser()
    with pytest.raises(ValueError):
        await engine.owner_control('missing', 'click', x=1, y=1)


@pytest.mark.asyncio
async def test_saved_profile_is_checkpointed_when_closed():
    engine, _ = mock_browser()
    session = engine._sessions['session']
    session.profile_name = 'my_profile'
    session.context.storage_state = AsyncMock(return_value={'cookies':[], 'origins':[]})
    session.context.close = AsyncMock()
    callback = AsyncMock()
    engine.profile_save_callback = callback
    result = await engine.close('session')
    assert result == {'closed': True, 'profile_updated': True, 'profile_save_failed': False}
    callback.assert_awaited_once_with('my_profile', {'cookies':[], 'origins':[]})
    session.context.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_storage_error_does_not_leave_browser_open():
    engine, _ = mock_browser()
    session = engine._sessions['session']
    session.profile_name = 'my_profile'
    session.context.storage_state = AsyncMock(return_value={'cookies':[], 'origins':[]})
    session.context.close = AsyncMock()
    engine.profile_save_callback = AsyncMock(side_effect=RuntimeError('secret must not be logged'))
    result = await engine.close('session')
    assert result['closed'] is True
    assert result['profile_updated'] is False
    assert result['profile_save_failed'] is True
    assert 'secret' not in str(result)
    session.context.close.assert_awaited_once()
