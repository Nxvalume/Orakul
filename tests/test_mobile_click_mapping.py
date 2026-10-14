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
    assert 'Это настоящее поле ввода Android' in VIEW
    assert VIEW.index('id="touch"') < VIEW.index('id="streamEntry"') < VIEW.index('id="live"')
    assert "input.focus()" in VIEW


def test_mobile_stream_input_uses_selected_browser_field_not_clipboard():
    assert "ownerAction('fill_field',{field_index:Number(field),text})" in VIEW
    assert "input.value='';" in VIEW
    assert "stream.type=entry.type" in VIEW
    assert "stream.inputMode=entry.inputMode" in VIEW
    assert "PHONE_PASSWORD_FLOOD" in VIEW
    assert "navigator.clipboard" not in VIEW
