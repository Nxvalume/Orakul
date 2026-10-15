"""MCP Apps discovery and wire metadata must be present in deployed MiniFish."""
import pytest

from chat_ui import CHAT_UI_MIME, CHAT_UI_URI, CHAT_HTML


@pytest.mark.asyncio
async def test_chat_window_is_discoverable_as_mcp_app():
    from server import mcp
    tools = await mcp.list_tools()
    opened = next(tool for tool in tools if tool.name == 'browser_open')
    viewer = next(tool for tool in tools if tool.name == 'browser_window')
    assert opened.meta['ui']['resourceUri'] == CHAT_UI_URI
    assert viewer.meta['ui']['resourceUri'] == CHAT_UI_URI

    resources = await mcp.list_resources()
    resource = next(r for r in resources if str(r.uri) == CHAT_UI_URI)
    assert resource.mimeType == CHAT_UI_MIME
    html = await mcp.read_resource(CHAT_UI_URI)
    assert 'ui/notifications/initialized' in str(html)
    assert 'tools/call' in str(html)


def test_chat_app_secret_form_is_not_connected_to_model_tool_bridge():
    # A private owner form is embedded, but sends its credentials DIRECTLY
    # over HTTPS. No secret is sent to tools/call or the assistant.
    assert 'type="password"' in CHAT_HTML
    assert 'secureRequest(\'unlock\'' in CHAT_HTML
    assert 'secureRequest(\'control\'' in CHAT_HTML
    assert 'MINIFISH_PASSWORD' not in CHAT_HTML
    assert "appCapabilities" in CHAT_HTML
    assert "bridge('ui/notifications/initialized'" not in CHAT_HTML
    assert 'https://nxval-minifish-2026.onrender.com/chat/secure/' in CHAT_HTML

@pytest.mark.asyncio
async def test_inline_ui_resource_csp_is_returned_in_resource_contents():
    from server import mcp
    from chat_ui import CHAT_UI_CSP
    contents = await mcp.read_resource(CHAT_UI_URI)
    assert contents, 'No resource content'
    item = contents[0]
    assert 'MiniFish' in item.content
    assert item.mime_type == CHAT_UI_MIME
    assert item.meta and item.meta['ui']['csp'] == CHAT_UI_CSP




def test_blocked_inline_tls_shows_clear_fallback_without_secret_exposure():
    from chat_ui import CHAT_HTML
    assert 'secureFallback' in CHAT_HTML
    assert 'Пароль MiniFish не был проверен' in CHAT_HTML
    assert 'https://nxval-minifish-2026.onrender.com/live?telegram=1' in CHAT_HTML
    assert "window.openai?.openExternal" in CHAT_HTML


def test_owner_login_preserves_deep_link_and_recovers_expired_browser():
    from live_view import LOGIN_PAGE, PAGE
    assert "location.replace('/live'+location.search)" in LOGIN_PAGE
    assert "launchTelegramIfEmpty" in PAGE
    assert "deepSession" in PAGE
    assert "$('openTelegram').click()" in PAGE



@pytest.mark.asyncio
async def test_mcp_v3_browser_tap_metadata_and_fullscreen():
    from server import mcp
    tools = await mcp.list_tools()
    opened = next(tool for tool in tools if tool.name == 'browser_open')
    tapped = next(tool for tool in tools if tool.name == 'browser_tap')
    assert opened.meta['openai/widgetAccessible'] is True
    assert opened.meta['ui']['visibility'] == ['model', 'app']
    assert tapped.meta['ui']['resourceUri'] == CHAT_UI_URI
    assert CHAT_UI_URI.endswith('browser-v3.html')
    resources = await mcp.list_resources()
    window = next(resource for resource in resources if str(resource.uri) == CHAT_UI_URI)
    assert window.meta['openai/ui']['availableDisplayModes'] == ['inline', 'fullscreen']
    assert 'https://nxval-minifish-2026.onrender.com' in window.meta['openai/widgetCSP']['redirect_domains']
    assert "browser_tap" in CHAT_HTML
    assert "window.openai?.callTool" in CHAT_HTML
    assert "setInterval" in CHAT_HTML


def test_native_chatgpt_widget_bridge_does_not_wait_on_mcp_initialize():
    from chat_ui import CHAT_HTML
    assert "typeof window.openai?.callTool==='function'" in CHAT_HTML
    assert 'ready=Promise.resolve()' in CHAT_HTML
    assert "ready=null;" in CHAT_HTML
    assert "ui/initialize" in CHAT_HTML

