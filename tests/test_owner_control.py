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


@pytest.mark.asyncio
async def test_owner_mobile_fill_field_never_replies_with_secret():
    engine, page = mock_browser()
    field = SimpleNamespace(
        get_attribute=AsyncMock(return_value='tel'),
        fill=AsyncMock())
    fields = SimpleNamespace(count=AsyncMock(return_value=2),
                             nth=lambda idx: field)
    page.locator = lambda selector: fields
    secret = 'not-a-real-phone-number-1234'
    result = await engine.owner_control('session', 'fill_field',
                                        field_index=1, text=secret)
    assert result['ok'] is True
    assert secret not in str(result)
    assert secret not in engine._sessions['session'].last_action
    field.fill.assert_awaited_once_with(secret, timeout=15000)
    with pytest.raises(ValueError):
        await engine.owner_control('session', 'fill_field', field_index=-1,
                                   text=secret)
    with pytest.raises(ValueError):
        await engine.owner_control('session', 'fill_field', field_index=24,
                                   text=secret)


@pytest.mark.asyncio
async def test_owner_mobile_fields_never_reveal_existing_values():
    engine, page = mock_browser()
    locator = SimpleNamespace(evaluate_all=AsyncMock(return_value=[
        {'index':0, 'kind':'tel', 'label':'Phone Number'},
        {'index':1, 'kind':'password', 'label':'Password'}]))
    page.locator = lambda selector: locator
    result = await engine.owner_fields('session')
    assert result['fields'][0]['label'] == 'Phone Number'
    assert 'value' not in str(result)
    assert 'Phone' in str(result)


@pytest.mark.asyncio
async def test_reopening_telegram_reuses_existing_live_session(monkeypatch):
    monkeypatch.setattr('engine.validate_url', lambda url: url)
    engine, page = mock_browser()
    engine._sessions.pop('session')
    page.url = 'https://web.telegram.org/k/'
    page.title = AsyncMock(return_value='Telegram Web')
    for i in range(2):
        engine._sessions['telegram' if i == 0 else 'example'] = Session(
            context=SimpleNamespace(pages=[page]), page=page)
    async def no_cleanup():
        return None
    engine._cleanup_expired = no_cleanup
    result = await engine.open('https://web.telegram.org/k/')
    assert result['reused'] is True
    assert result['session_id'] in ('telegram', 'example')
    assert len(engine._sessions) == 2
