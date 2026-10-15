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
