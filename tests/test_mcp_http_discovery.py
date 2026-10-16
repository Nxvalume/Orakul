"""Wire-level MCP discovery regression.

A published plugin can keep an old approved tool snapshot even when the
running MCP server advertises fresh tools. Test the real /mcp HTTP handler,
not only FastMCP's in-memory registration. No Telegram credentials are used.
"""
from starlette.testclient import TestClient


def test_authenticated_mcp_http_discovers_current_browser_tools(monkeypatch):
    import server
    from chat_ui import CHAT_UI_URI, CHAT_UI_MIME

    # Isolated dummy bearer approved only inside this test process.
    token = 'minifish-ci-wire-test-token'
    monkeypatch.setattr(server, 'authorized_access', lambda supplied: supplied == token)

    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json, text/event-stream',
        'Content-Type': 'application/json',
        'MCP-Protocol-Version': '2025-06-18',
    }

    with TestClient(server.app, base_url='http://localhost:8000') as client:
        def rpc(method, request_id, params=None):
            response = client.post(
                '/mcp', headers=headers,
                json={'jsonrpc': '2.0', 'id': request_id, 'method': method,
                      'params': params or {}})
            assert response.status_code == 200, (method, response.status_code, response.text[:500])
            result = response.json()
            assert 'error' not in result, (method, result.get('error'))
            return result['result']

        init = rpc('initialize', 1, {
            'protocolVersion': '2025-06-18',
            'capabilities': {},
            'clientInfo': {'name': 'minifish-wire-ci', 'version': '1.0.0'},
        })
        assert init['serverInfo']['name']

        tools = rpc('tools/list', 2)['tools']
        names = {tool['name'] for tool in tools}
        required = {'browser_open', 'browser_window', 'browser_tap',
                    'browser_telegram_status', 'browser_screenshot',
                    'browser_snapshot'}
        assert required <= names, 'Live MCP HTTP tools/list is missing: ' + repr(sorted(required - names))

        viewer = next(tool for tool in tools if tool['name'] == 'browser_window')
        assert viewer.get('_meta', {}).get('ui', {}).get('resourceUri') == CHAT_UI_URI

        resources = rpc('resources/list', 3)['resources']
        resource = next(item for item in resources if item['uri'] == CHAT_UI_URI)
        assert resource['mimeType'] == CHAT_UI_MIME
        contents = rpc('resources/read', 4, {'uri': CHAT_UI_URI})['contents']
        assert any('MiniFish' in item.get('text', '') for item in contents)
