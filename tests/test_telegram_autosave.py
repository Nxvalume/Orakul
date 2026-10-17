"""Telegram auto-checkpoint must save auth before private browser is released."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import asyncio
import pytest


@pytest.mark.asyncio
async def test_telegram_autosave_persists_private_login_and_releases_owner(monkeypatch):
    import server
    sid = 'test-telegram-owner'
    session = SimpleNamespace(private_mode=True)
    monkeypatch.setattr(server.engine, '_sessions', {sid: session})
    monkeypatch.setattr(server.engine, 'telegram_session_id', lambda: sid)
    state = {'cookies': [{'name': 'synthetic'}], 'origins': []}
    monkeypatch.setattr(server.engine, 'telegram_authenticated_state', AsyncMock(return_value=state))
    save = AsyncMock()
    release = AsyncMock(return_value=True)
    rename = Mock()
    monkeypatch.setattr(server, '_checkpoint_browser_profile', save)
    monkeypatch.setattr(server.engine, 'release_verified_telegram_login', release)
    monkeypatch.setattr(server.engine, 'set_profile_name', rename)
    monkeypatch.setattr(server.store, 'durable', True, raising=False)
    monkeypatch.setattr(server.store, 'degraded', False, raising=False)
    ticks = 0
    async def one_iteration(seconds):
        nonlocal ticks
        ticks += 1
        if ticks > 1:
            raise asyncio.CancelledError()
    monkeypatch.setattr(server.asyncio, 'sleep', one_iteration)
    with pytest.raises(asyncio.CancelledError):
        await server._telegram_profile_watch()
    save.assert_awaited_once_with('telegram', state)
    rename.assert_called_once_with(sid, 'telegram')
    release.assert_awaited_once_with(sid)


@pytest.mark.asyncio
async def test_telegram_autosave_does_not_persist_qr_login_page(monkeypatch):
    import server
    sid = 'test-unauthed'
    monkeypatch.setattr(server.engine, 'telegram_session_id', lambda: sid)
    monkeypatch.setattr(server.engine, '_sessions', {sid: SimpleNamespace(private_mode=True)})
    monkeypatch.setattr(server.engine, 'telegram_authenticated_state', AsyncMock(return_value=None))
    save = AsyncMock()
    monkeypatch.setattr(server, '_checkpoint_browser_profile', save)
    ticks = 0
    async def one_iteration(seconds):
        nonlocal ticks
        ticks += 1
        if ticks > 1:
            raise asyncio.CancelledError()
    monkeypatch.setattr(server.asyncio, 'sleep', one_iteration)
    with pytest.raises(asyncio.CancelledError):
        await server._telegram_profile_watch()
    save.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_does_not_save_visible_chat_until_auth_database_is_durable(monkeypatch):
    from engine import BrowserEngine, Session
    browser = BrowserEngine()
    page = SimpleNamespace(
        url='https://web.telegram.org/k/', is_closed=lambda:False,
        locator=lambda selector:SimpleNamespace(
            is_visible=AsyncMock(return_value=selector == '#column-left')))
    context=SimpleNamespace(pages=[page])
    browser._sessions['telegram']=Session(context=context,page=page)
    durable = {'origins':[{'origin':'https://web.telegram.org'}], 'cookies':[]}
    export = AsyncMock(return_value=durable)
    checks = AsyncMock(side_effect=[False, True])
    monkeypatch.setattr(browser, '_encrypted_profile_state', export)
    monkeypatch.setattr(browser, '_telegram_indexeddb_auth_ready', checks)

    assert await browser.telegram_authenticated_state('telegram') is None
    export.assert_not_awaited()
    assert await browser.telegram_authenticated_state('telegram') == durable
    export.assert_awaited_once()
    assert checks.await_count == 2


@pytest.mark.asyncio
async def test_indexeddb_readiness_uses_record_counts_not_secret_values():
    from engine import BrowserEngine
    page=SimpleNamespace(evaluate=AsyncMock(return_value=False))
    assert await BrowserEngine()._telegram_indexeddb_auth_ready(page) is False
    page.evaluate=AsyncMock(return_value=True)
    assert await BrowserEngine()._telegram_indexeddb_auth_ready(page) is True
    assert 'count.result > 0' in page.evaluate.await_args.args[0]
    assert 'getAll()' not in page.evaluate.await_args.args[0]


@pytest.mark.asyncio
async def test_restored_telegram_can_refresh_legacy_authenticated_storage(monkeypatch):
    from engine import BrowserEngine, Session
    b = BrowserEngine()
    page = SimpleNamespace(
        url='https://web.telegram.org/k/', is_closed=lambda: False,
        locator=lambda selector: SimpleNamespace(
            is_visible=AsyncMock(return_value=selector == '#column-left')))
    state = {'cookies': [], 'origins': [
        {'origin': 'https://web.telegram.org',
         'indexedDB': [{'name': 'legacy-fixture', 'stores': []}]}]}
    b._sessions['restored'] = Session(
        context=SimpleNamespace(pages=[page]), page=page,
        profile_name='telegram')
    monkeypatch.setattr(b, '_telegram_indexeddb_auth_ready',
                        AsyncMock(return_value=False))
    backup = AsyncMock(return_value=state)
    monkeypatch.setattr(b, '_encrypted_profile_state', backup)
    assert await b.telegram_authenticated_state('restored') == state
    backup.assert_awaited_once()


@pytest.mark.asyncio
async def test_restored_telegram_rejects_empty_storage_despite_visible_chat(monkeypatch):
    from engine import BrowserEngine, Session
    b = BrowserEngine()
    page = SimpleNamespace(
        url='https://web.telegram.org/k/', is_closed=lambda: False,
        locator=lambda selector: SimpleNamespace(
            is_visible=AsyncMock(return_value=selector == '#column-left')))
    b._sessions['restored'] = Session(
        context=SimpleNamespace(pages=[page]), page=page,
        profile_name='telegram')
    monkeypatch.setattr(b, '_telegram_indexeddb_auth_ready',
                        AsyncMock(return_value=False))
    monkeypatch.setattr(b, '_encrypted_profile_state',
                        AsyncMock(return_value={'cookies': [], 'origins': []}))
    assert await b.telegram_authenticated_state('restored') is None
