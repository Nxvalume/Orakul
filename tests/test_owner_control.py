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
        mouse=SimpleNamespace(click=AsyncMock(), move=AsyncMock()),
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
        fill=AsyncMock(), evaluate=AsyncMock(return_value=True))
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
    field.evaluate.assert_awaited_once()
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



@pytest.mark.asyncio
async def test_telegram_auth_state_is_saved_only_after_visible_chats():
    engine, page = mock_browser()
    page.url = 'https://web.telegram.org/k/'
    auth_pages = SimpleNamespace(is_visible=AsyncMock(return_value=True))
    chat_column = SimpleNamespace(is_visible=AsyncMock(return_value=False))
    page.locator = lambda css: chat_column if css == '#column-left' else auth_pages
    engine._sessions['session'].context.storage_state = AsyncMock(
        return_value={'cookies': [], 'origins': []})
    assert await engine.telegram_authenticated_state('session') is None
    chat_column.is_visible.return_value = True
    auth_pages.is_visible.return_value = False
    state = await engine.telegram_authenticated_state('session')
    assert state == {'cookies': [], 'origins': []}


@pytest.mark.asyncio
async def test_logging_out_never_overwrites_saved_telegram_profile():
    engine, page = mock_browser()
    page.url = 'https://web.telegram.org/k/'
    session = engine._sessions['session']
    session.profile_name = 'telegram'
    page.locator = lambda css: SimpleNamespace(is_visible=AsyncMock(
        return_value=css == '#auth-pages'))
    session.context.close = AsyncMock()
    session.context.storage_state = AsyncMock(return_value={'cookies': []})
    engine.profile_save_callback = AsyncMock()
    result = await engine.close('session')
    assert result['closed'] is True
    assert result['profile_updated'] is False
    engine.profile_save_callback.assert_not_awaited()
    session.context.storage_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_active_session_selection_is_domain_scoped():
    engine, page = mock_browser()
    page.url = 'https://web.telegram.org/k/'
    assert engine.telegram_session_id() == 'session'
    page.url = 'https://example.com/'
    assert engine.telegram_session_id() is None



@pytest.mark.asyncio
async def test_cursor_moves_in_steps_before_click(monkeypatch):
    engine, page = mock_browser()
    monkeypatch.setattr('engine.asyncio.sleep', AsyncMock())
    response = await engine.owner_control('session', 'click', x=800, y=500)
    assert response['ok']
    assert page.mouse.move.await_count == 14
    first = page.mouse.move.await_args_list[0].args
    final = page.mouse.move.await_args_list[-1].args
    assert first[0] > 640 and first[0] < 800
    assert final == (800.0, 500.0)
    assert engine._sessions['session'].cursor == (800.0,500.0)
    page.mouse.click.assert_awaited_once_with(800.0, 500.0)



@pytest.mark.asyncio
async def test_telegram_auth_is_persisted_in_owner_private_mode():
    engine, page = mock_browser()
    page.url='https://web.telegram.org/k/'
    session=engine._sessions['session']
    session.private_mode=True
    loggedin=SimpleNamespace(is_visible=AsyncMock(return_value=True))
    login=SimpleNamespace(is_visible=AsyncMock(return_value=False))
    page.locator=lambda sel: loggedin if sel=='#column-left' else login
    session.context.storage_state=AsyncMock(return_value={'cookies':[{'name':'test'}], 'origins':[]})
    assert await engine.telegram_authenticated_state('session') == {'cookies':[{'name':'test'}], 'origins':[]}
    callback=AsyncMock()
    engine.profile_save_callback=callback
    result=await engine.owner_set_private('session',False)
    assert result['profile_saved'] is True
    assert result['save_error'] is None
    assert result['private_mode'] is False
    assert session.profile_name=='telegram'
    callback.assert_awaited_once_with('telegram',{'cookies':[{'name':'test'}], 'origins':[]})


@pytest.mark.asyncio
async def test_telegram_private_mode_exposes_clean_save_failure():
    engine,page=mock_browser()
    page.url='https://web.telegram.org/k/'
    session=engine._sessions['session']
    session.private_mode=True
    loggedin=SimpleNamespace(is_visible=AsyncMock(return_value=True))
    login=SimpleNamespace(is_visible=AsyncMock(return_value=False))
    page.locator=lambda sel: loggedin if sel=='#column-left' else login
    session.context.storage_state=AsyncMock(return_value={'cookies':[],'origins':[]})
    engine.profile_save_callback=AsyncMock(side_effect=RuntimeError('sensitive-sentinel'))
    result=await engine.owner_set_private('session',False)
    assert result['profile_saved'] is False
    assert 'RuntimeError' in result['save_error']
    assert 'sensitive-sentinel' not in str(result)
    assert result['private_mode'] is False



@pytest.mark.asyncio
async def test_closing_fresh_telegram_login_saves_even_without_profile_name():
    """Closing the mobile /live tab before pressing Finish must not lose auth."""
    engine, page = mock_browser()
    session = engine._sessions['session']
    session.profile_name = None
    page.url = 'https://web.telegram.org/k/'
    page.locator = lambda sel: SimpleNamespace(
        is_visible=AsyncMock(return_value=sel == '#column-left'))
    session.context.storage_state = AsyncMock(
        return_value={'cookies': [{'name': 'fixture'}], 'origins': []})
    session.context.close = AsyncMock()
    callback = AsyncMock()
    engine.profile_save_callback = callback
    result = await engine.close('session')
    assert result['closed'] is True
    assert result['profile_updated'] is True
    callback.assert_awaited_once_with('telegram', {
        'cookies': [{'name': 'fixture'}], 'origins': []})


@pytest.mark.asyncio
async def test_telegram_private_login_waits_longer_than_standard_idle(monkeypatch):
    from engine import session_idle_limit, TTL_SECONDS, TELEGRAM_LOGIN_TTL_SECONDS
    engine, page = mock_browser()
    session = engine._sessions['session']
    page.url = 'https://web.telegram.org/k/'
    session.touched -= TTL_SECONDS + 20
    assert session_idle_limit(session) == TTL_SECONDS
    session.private_mode = True
    assert session_idle_limit(session) == TELEGRAM_LOGIN_TTL_SECONDS
    assert engine.telegram_session_id() == 'session'
    assert engine.get('session', owner=True) is session
    assert engine.telegram_session_id() == 'session'


@pytest.mark.asyncio
async def test_verified_telegram_owner_handoff_never_reads_secrets():
    engine, page = mock_browser()
    session = engine._sessions['session']
    page.url = 'https://web.telegram.org/k/'
    session.private_mode = True
    page.locator = lambda sel: SimpleNamespace(
        is_visible=AsyncMock(return_value=sel == '#column-left'))
    assert await engine.release_verified_telegram_login('session') is True
    assert session.private_mode is False
    assert session.profile_name == 'telegram'
    assert 'вход сохранён' in session.last_action
    assert 'value' not in session.last_action


@pytest.mark.asyncio
async def test_telegram_qr_screen_not_saved_on_close_when_profile_unnamed():
    engine, page = mock_browser()
    session = engine._sessions['session']
    session.profile_name = None
    page.url = 'https://web.telegram.org/k/'
    page.locator = lambda sel: SimpleNamespace(
        is_visible=AsyncMock(return_value=sel == '#auth-pages'))
    session.context.close = AsyncMock()
    session.context.storage_state = AsyncMock()
    engine.profile_save_callback = AsyncMock()
    result = await engine.close('session')
    assert result['profile_updated'] is False
    engine.profile_save_callback.assert_not_awaited()
    session.context.storage_state.assert_not_awaited()



@pytest.mark.asyncio
async def test_tap_coordinates_use_existing_safe_click():
    engine, page = mock_browser()
    page.evaluate = AsyncMock(return_value='#safe-button')
    target = SimpleNamespace(
        inner_text=AsyncMock(return_value='Open page'),
        get_attribute=AsyncMock(return_value=None),
        scroll_into_view_if_needed=AsyncMock(),
        bounding_box=AsyncMock(return_value={'x':10,'y':20,'width':40,'height':50}),
        click=AsyncMock())
    page.locator = lambda css: SimpleNamespace(first=target)
    engine._move_cursor = AsyncMock()
    result = await engine.tap('session', 30, 35)
    assert result['clicked'] == '#safe-button'
    page.evaluate.assert_awaited_once()
    engine._move_cursor.assert_awaited_once_with(engine._sessions['session'],30,45)
    target.click.assert_awaited_once()


@pytest.mark.asyncio
async def test_tap_protected_while_owner_is_entering_password():
    engine, page = mock_browser()
    engine._sessions['session'].private_mode = True
    page.evaluate = AsyncMock()
    with pytest.raises(PermissionError):
        await engine.tap('session', 80, 120)
    page.evaluate.assert_not_awaited()


@pytest.mark.asyncio
async def test_tap_never_bypasses_sensitive_click_confirmation():
    engine, page = mock_browser()
    page.evaluate = AsyncMock(return_value='#send')
    target = SimpleNamespace(
        inner_text=AsyncMock(return_value='Send'),
        get_attribute=AsyncMock(return_value=None),
        click=AsyncMock())
    page.locator = lambda css: SimpleNamespace(first=target)
    with pytest.raises(PermissionError, match='подтверждение'):
        await engine.tap('session', 20, 40)
    target.click.assert_not_awaited()
    assert engine._sessions['session'].pending_click


@pytest.mark.asyncio
async def test_tap_rejects_out_of_bounds_positions():
    engine, page = mock_browser()
    page.evaluate = AsyncMock()
    for xy in [(-1,2), (2,900), (1280,2), (True,2)]:
        with pytest.raises(ValueError):
            await engine.tap('session', *xy)
    page.evaluate.assert_not_awaited()


@pytest.mark.asyncio
async def test_owner_password_fill_does_not_report_false_success():
    engine, page = mock_browser()
    field = SimpleNamespace(
        get_attribute=AsyncMock(return_value='password'),
        fill=AsyncMock(), evaluate=AsyncMock(return_value=False))
    page.locator = lambda selector: SimpleNamespace(
        count=AsyncMock(return_value=1), nth=lambda index: field)
    with pytest.raises(ValueError, match='Поле не приняло ввод') as exc:
        await engine.owner_control('session', 'fill_field',
                                   field_index=0, text='sample-private-value')
    assert 'sample-private-value' not in str(exc.value)
    field.fill.assert_awaited_once()


@pytest.mark.asyncio
async def test_owner_telegram_next_click_is_explicit_and_only_for_telegram():
    engine, page = mock_browser()
    button = SimpleNamespace(count=AsyncMock(return_value=1), click=AsyncMock())
    page.get_by_role = lambda role, name, exact: button
    page.locator = lambda selector: SimpleNamespace(evaluate=AsyncMock(return_value=False))
    with pytest.raises(ValueError, match='только в Telegram'):
        await engine.owner_control('session', 'telegram_next')
    button.click.assert_not_awaited()
    page.url = 'https://web.telegram.org/k/'
    result = await engine.owner_control('session', 'telegram_next')
    assert result['ok'] is True
    button.click.assert_awaited_once_with(timeout=15000)
    assert 'парол' not in str(result).lower()


@pytest.mark.asyncio
async def test_owner_telegram_next_refuses_flood_retries():
    engine, page = mock_browser()
    page.url = 'https://web.telegram.org/k/'
    page.locator = lambda selector: SimpleNamespace(evaluate=AsyncMock(return_value=True))
    button = SimpleNamespace(count=AsyncMock(return_value=1), click=AsyncMock())
    page.get_by_role = lambda role, name, exact: button
    with pytest.raises(ValueError, match='PHONE_PASSWORD_FLOOD'):
        await engine.owner_control('session', 'telegram_next')
    button.click.assert_not_awaited()


def test_mobile_telegram_password_has_explicit_next_button():
    from live_view import PAGE
    assert 'id="streamNext"' in PAGE
    assert "ownerAction('telegram_next')" in PAGE
    assert "if(ok)input.value='';" in PAGE
    assert 'Ввод подтверждён браузером' in PAGE
