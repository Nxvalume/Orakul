"""Regression: a failed Telegram checkpoint cannot expose owner login to MCP."""
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from engine import BrowserEngine, Session, TTL_SECONDS


def telegram_engine():
    shown = {
        '#column-left': True,
        '#auth-pages': False,
    }
    def locator(selector):
        return SimpleNamespace(is_visible=AsyncMock(return_value=shown.get(selector, False)))
    page = SimpleNamespace(
        url='https://web.telegram.org/k/',
        is_closed=lambda: False,
        locator=locator,
        screenshot=AsyncMock(return_value=b'test-jpeg'),
    )
    context = SimpleNamespace(
        storage_state=AsyncMock(return_value={'cookies': [], 'origins': []}),
    )
    engine = BrowserEngine()
    engine._sessions['telegram-test'] = Session(context=context, page=page)
    return engine, context


@pytest.mark.asyncio
async def test_owner_stays_private_when_checkpoint_fails():
    engine, context = telegram_engine()
    await engine.owner_set_private('telegram-test', True)
    engine.profile_save_callback = AsyncMock(side_effect=RuntimeError('sensitive-data'))
    result = await engine.owner_set_private('telegram-test', False)
    assert result['private_mode'] is True
    assert result['profile_saved'] is False
    assert result['save_error'] is not None
    assert 'sensitive-data' not in str(result)
    with pytest.raises(PermissionError, match='Личный режим'):
        engine.get('telegram-test')
    assert engine.telegram_session_id() == 'telegram-test'
    context.storage_state.assert_awaited_once_with(indexed_db=True)


@pytest.mark.asyncio
async def test_owner_can_release_after_successful_retry():
    engine, _ = telegram_engine()
    await engine.owner_set_private('telegram-test', True)
    saving = AsyncMock(side_effect=[RuntimeError('temporary store error'), None])
    engine.profile_save_callback = saving
    failed = await engine.owner_set_private('telegram-test', False)
    assert failed['private_mode'] is True
    saved = await engine.owner_set_private('telegram-test', False)
    assert saved == {'private_mode': False, 'profile_saved': True, 'save_error': None}
    assert engine._sessions['telegram-test'].profile_name == 'telegram'
    assert engine.get('telegram-test') is engine._sessions['telegram-test']
    assert saving.await_count == 2


@pytest.mark.asyncio
async def test_telegram_private_video_obeys_longer_login_ttl_without_renewal():
    engine, _ = telegram_engine()
    session = engine._sessions['telegram-test']
    session.private_mode = True
    session.touched = time.monotonic() - TTL_SECONDS - 20
    initial_touch = session.touched
    assert await engine.live_jpeg('telegram-test') == b'test-jpeg'
    assert session.touched == initial_touch
    session.private_mode = False
    with pytest.raises(ValueError, match='Сессия недоступна'):
        await engine.live_jpeg('telegram-test')


def test_live_ui_uses_actual_private_mode_when_checkpoint_fails():
    from live_view import PAGE
    assert 'privateMode=!!data.private_mode;' in PAGE
    assert 'else if(data.save_error)' in PAGE
    assert 'Личный вход остаётся включённым' in PAGE
