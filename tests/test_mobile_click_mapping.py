"""Mobile live-view touch regressions without requiring a Telegram login."""
from pathlib import Path
from engine import BrowserEngine

VIEW = Path(__file__).resolve().parent.parent.joinpath('live_view.py').read_text()


def test_mobile_tap_coordinates_use_real_viewport():
    assert "currentViewport={width:1280,height:900}" in VIEW
    assert "nx*w" in VIEW and "ny*h" in VIEW
    assert "'viewport': s.page.viewport_size" in Path(__file__).resolve().parent.parent.joinpath('engine.py').read_text()
    assert "naturalWidth||1280)/r.width" not in VIEW


def test_mobile_taps_enabled_by_default_and_visible_above_stream():
    assert "let clickEnabled=true" in VIEW
    assert '<div class="screen interactive">' in VIEW
    assert VIEW.index('id="touch"') < VIEW.index('id="live"')
    assert "aria-pressed=\"true\"" in VIEW


def test_click_owner_endpoint_requires_authenticated_cookie():
    assert 'if not owner(req):' in VIEW
    assert "await engine.owner_control" in VIEW


def test_mobile_stream_has_real_keyboard_input_next_to_video():
    assert 'id="streamEntry"' in VIEW
    assert 'id="streamInsert"' in VIEW
    assert 'id="streamInputStatus"' in VIEW
    assert 'Поле ввода телефона' in VIEW
    assert VIEW.index('id="urlBar"') < VIEW.index('id="touch"') < VIEW.index('id="live"') < VIEW.index('id="streamEntry"')
    assert "input.focus()" in VIEW


def test_mobile_stream_input_uses_selected_browser_field_not_clipboard():
    assert "ownerAction('fill_field',{field_index:Number(field),text})" in VIEW
    assert "input.value='';" in VIEW
    assert "stream.type=entry.type" in VIEW
    assert "stream.inputMode=entry.inputMode" in VIEW
    assert "PHONE_PASSWORD_FLOOD" in VIEW
    assert "navigator.clipboard" not in VIEW


def test_telegram_entry_is_single_guided_mobile_flow():
    """Critical owner UX: one obvious protected input rather than duplicate forms."""
    from live_view import PAGE, LOGIN_PAGE
    assert 'id="telegramTitle"' in PAGE
    assert 'id="loginPhase"' in PAGE
    assert 'id="openTelegram"' in PAGE
    assert 'id="entryLabel"' in PAGE
    assert 'id="streamEntry"' in PAGE
    assert 'id="streamInsert"' in PAGE
    assert 'id="streamNext"' in PAGE
    assert PAGE.index('id="openTelegram"') < PAGE.index('id="live"') < PAGE.index('id="streamEntry"')
    assert PAGE.count('id="openTelegram"') == 1
    assert PAGE.count('id="streamEntry"') == 1
    assert 'id="quickValue"' not in PAGE
    assert 'id="quickApply"' not in PAGE
    assert 'id="quickNext"' not in PAGE
    assert "$('fieldRefresh').onclick" not in PAGE
    assert 'Другие сайты, навигация и дополнительные кнопки' in PAGE
    assert 'Дополнительно: управление другими сайтами' in PAGE
    assert "$('entryLabel').textContent=" in PAGE
    assert "if(data.logged_in&&data.saved&&data.durable)" in PAGE
    assert 'Это пароль MiniFish, не код и не пароль Telegram' in LOGIN_PAGE


def test_telegram_mobility_keeps_password_input_private_and_clear_on_success():
    from live_view import PAGE
    assert "stream.type=secret?'password':'text'" in PAGE
    assert "if(ok)input.value='';" in PAGE
    assert "ownerAction('fill_field',{field_index:Number(field),text})" in PAGE
    assert "ownerAction('telegram_next')" in PAGE
    assert "'streamInsert').disabled=true" in PAGE
    assert 'Не повторяй попытки входа' not in PAGE or 'PHONE_PASSWORD_FLOOD' in PAGE
