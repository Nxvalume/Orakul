"""MCP Apps discovery and wire metadata must be present in deployed MiniFish."""
import pytest

from chat_ui import CHAT_UI_MIME, CHAT_UI_URI, CHAT_HTML


@pytest.mark.asyncio
async def test_chat_window_is_discoverable_as_mcp_app():
    from server import mcp
    tools = await mcp.list_tools()
    opened = next(tool for tool in tools if tool.name == 'browser_open')
    viewer = next(tool for tool in tools if tool.name == 'browser_window')
    assert opened.meta['openai/widgetAccessible'] is True
    assert 'resourceUri' not in opened.meta['ui']  # opening a site must not spawn a second window
    assert viewer.meta['ui']['resourceUri'] == CHAT_UI_URI

    resources = await mcp.list_resources()
    resource = next(r for r in resources if str(r.uri) == CHAT_UI_URI)
    assert resource.mimeType == CHAT_UI_MIME
    # A previously cached Android widget URI must remain readable.
    legacy = next(r for r in resources if str(r.uri) == 'ui://minifish/browser-v4.html')
    assert legacy.mimeType == CHAT_UI_MIME
    legacy_v5 = next(r for r in resources if str(r.uri) == 'ui://minifish/browser-v5.html')
    assert legacy_v5.mimeType == CHAT_UI_MIME
    legacy_v6 = next(r for r in resources if str(r.uri) == 'ui://minifish/browser-v6.html')
    assert legacy_v6.mimeType == CHAT_UI_MIME
    legacy_v7 = next(r for r in resources if str(r.uri) == 'ui://minifish/browser-v7.html')
    assert legacy_v7.mimeType == CHAT_UI_MIME
    legacy_v8 = next(r for r in resources if str(r.uri) == 'ui://minifish/browser-v8.html')
    assert legacy_v8.mimeType == CHAT_UI_MIME
    legacy_v9 = next(r for r in resources if str(r.uri) == 'ui://minifish/browser-v9.html')
    assert legacy_v9.mimeType == CHAT_UI_MIME
    legacy_v10 = next(r for r in resources if str(r.uri) == 'ui://minifish/browser-v10.html')
    assert legacy_v10.mimeType == CHAT_UI_MIME
    legacy_v11 = next(r for r in resources if str(r.uri) == 'ui://minifish/browser-v11.html')
    assert legacy_v11.mimeType == CHAT_UI_MIME
    legacy_v12 = next(r for r in resources if str(r.uri) == 'ui://minifish/browser-v12.html')
    assert legacy_v12.mimeType == CHAT_UI_MIME
    legacy_v13 = next(r for r in resources if str(r.uri) == 'ui://minifish/browser-v13.html')
    assert legacy_v13.mimeType == CHAT_UI_MIME
    legacy_v14 = next(r for r in resources if str(r.uri) == 'ui://minifish/browser-v14.html')
    assert legacy_v14.mimeType == CHAT_UI_MIME
    legacy_v15 = next(r for r in resources if str(r.uri) == 'ui://minifish/browser-v15.html')
    assert legacy_v15.mimeType == CHAT_UI_MIME
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
    assert tapped.meta['openai/widgetAccessible'] is True
    assert 'resourceUri' not in tapped.meta['ui']  # tapping should update current window
    assert CHAT_UI_URI.endswith('browser-v16.html')
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



def test_unavailable_mcp_host_fails_fast_instead_of_waiting_on_tool_calls():
    from chat_ui import CHAT_HTML
    assert 'let bridgeAvailable=true;' in CHAT_HTML
    assert 'bridgeAvailable=false;' in CHAT_HTML
    assert "if(!bridgeAvailable)throw new Error" in CHAT_HTML


@pytest.mark.asyncio
async def test_widget_helpers_are_accessible_without_opening_duplicate_windows():
    from server import mcp
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    viewer = tools['browser_window']
    assert viewer.meta['ui']['resourceUri'] == CHAT_UI_URI
    for name in ('browser_open', 'browser_snapshot', 'browser_screenshot',
                 'browser_tap', 'browser_click', 'browser_fill',
                 'browser_scroll', 'browser_back', 'browser_goto',
                 'browser_select'):
        meta = tools[name].meta
        assert meta['openai/widgetAccessible'] is True, name
        assert 'resourceUri' not in meta.get('ui', {}), name


def test_widget_stalled_image_reports_timeout_instead_of_infinite_spinner():
    from chat_ui import CHAT_HTML
    assert 'timeout(16000)' in CHAT_HTML
    assert 'Кадр не загрузился' in CHAT_HTML
    assert 'Нет соединения с сеансом' in CHAT_HTML


@pytest.mark.asyncio
async def test_android_widget_can_attach_one_existing_public_session(monkeypatch):
    import server
    monkeypatch.setattr(server.engine, 'live_sessions', lambda: [
        {'session_id': 'existing-123', 'site': 'example.com', 'private_mode': False}
    ])
    monkeypatch.setattr(server.engine, 'get', lambda sid: sid)
    result = await server.browser_attach()
    assert result == {'attached': True, 'session_id': 'existing-123',
                      'site': 'example.com'}


@pytest.mark.asyncio
async def test_android_widget_attach_never_exposes_private_or_ambiguous_sessions(monkeypatch):
    import server
    def prohibit_get(sid):
        raise AssertionError('Owner-private session must never be queried')
    monkeypatch.setattr(server.engine, 'get', prohibit_get)
    monkeypatch.setattr(server.engine, 'live_sessions', lambda: [])
    assert await server.browser_attach() == {'attached': False, 'reason': 'not_open'}
    private = {'session_id': 'private-123', 'site': 'web.telegram.org',
               'private_mode': True}
    monkeypatch.setattr(server.engine, 'live_sessions', lambda: [private])
    assert await server.browser_attach() == {'attached': False, 'reason': 'private_mode'}
    monkeypatch.setattr(server.engine, 'live_sessions', lambda: [private, private])
    assert await server.browser_attach() == {'attached': False, 'reason': 'ambiguous'}


def test_android_ui_auto_recovers_missing_tool_input_without_new_session():
    from chat_ui import CHAT_HTML
    assert "call('browser_attach',{})" in CHAT_HTML
    assert 'setTimeout(()=>{if(!session)attachExisting()},600)' in CHAT_HTML
    assert "if(!session)await attachExisting();" in CHAT_HTML
    assert "const ok=await recoverSession();" in CHAT_HTML
    assert 'window.openai?.toolInput' in CHAT_HTML
    assert "call('browser_open',{url:'https://example.com/'})" in CHAT_HTML


def test_mobile_tabs_load_independently_of_slow_page_snapshot():
    from chat_ui import CHAT_HTML
    start = CHAT_HTML.index('async function render(){')
    end = CHAT_HTML.index('async function act(', start)
    renderer = CHAT_HTML[start:end]
    assert renderer.index('void refreshPublicTabs();') < renderer.index("call('browser_screenshot'")
    assert renderer.index('void refreshPublicTabs();') < renderer.index("call('browser_snapshot'")
    assert 'let frameReady=false,recovered=false;' in renderer
    assert "Экран готов; элементы страницы временно недоступны:" in renderer
    # The DOM snapshot must never be required before tabs can load.
    assert "await refreshPublicTabs();" not in renderer


def test_tab_click_while_page_loading_is_queued_not_silently_dropped():
    from chat_ui import CHAT_HTML
    start = CHAT_HTML.index('async function act(')
    end = CHAT_HTML.index("$('refresh').onclick", start)
    action = CHAT_HTML[start:end]
    assert 'queuedAction={name,args};' in action
    assert 'if(!session||busy||secureToken||privateLocked)return;' not in action
    start = CHAT_HTML.index('async function render(){')
    end = CHAT_HTML.index('async function act(', start)
    renderer = CHAT_HTML[start:end]
    assert 'if(queuedAction&&!secureToken&&!privateLocked)' in renderer
    assert 'void act(next.name,next.args);' in renderer
    assert 'privateLocked=true;secureToken=\'\';queuedAction=null;' in CHAT_HTML


def test_android_omnibox_shows_search_keyboard_and_search_placeholder():
    from chat_ui import CHAT_HTML
    assert 'enterkeyhint="search"' in CHAT_HTML
    assert 'Поиск, например: телеграмм' in CHAT_HTML
    assert 'Поиск или адрес сайта' in CHAT_HTML
    assert "https://nxval-minifish-2026.onrender.com/search?q=" in CHAT_HTML
    assert "resolveOmnibox($('navUrl').value)" in CHAT_HTML
    assert "resolveOmnibox($('secureUrl').value)" in CHAT_HTML


def test_mobile_page_back_is_labeled_and_always_above_the_page_frame():
    from chat_ui import CHAT_HTML
    assert CHAT_HTML.count('id="back"') == 1
    assert CHAT_HTML.count('id="forward"') == 1
    assert CHAT_HTML.count('id="secureBack"') == 1
    assert CHAT_HTML.count('id="secureForward"') == 1
    assert CHAT_HTML.index('id="navigationBar"') < CHAT_HTML.index('id="navForm"')
    assert CHAT_HTML.index('id="navigationBar"') < CHAT_HTML.index('id="shot"')
    assert CHAT_HTML.index('id="secureNavigationBar"') < CHAT_HTML.index('id="secureNavForm"')
    assert CHAT_HTML.index('id="secureNavigationBar"') < CHAT_HTML.index('id="secureShot"')
    assert '>← Назад</button>' in CHAT_HTML
    assert 'aria-label="Назад на предыдущую страницу"' in CHAT_HTML
    assert "$('back').onclick=()=>act('browser_back',{session_id:session});" in CHAT_HTML
    assert "$('secureBack').onclick=()=>secureAction('back',{});" in CHAT_HTML
    assert "$('navigationBar').hidden=!enabled;" in CHAT_HTML


def test_mobile_omnibox_is_single_search_field_above_results_viewport():
    from chat_ui import CHAT_HTML
    assert CHAT_HTML.index('id="navUrl"') < CHAT_HTML.index('id="shot"')
    assert '<button class="primary" type="submit">Найти</button>' in CHAT_HTML
    assert "const url=resolveOmnibox($('navUrl').value);" in CHAT_HTML
    assert "act('browser_goto',{session_id:session,url});" in CHAT_HTML
    assert "if(document.activeElement!==$('navUrl')" in CHAT_HTML
    assert "$('navUrl').value=displayAddressOrQuery(result.url);" in CHAT_HTML
    assert "u.searchParams.get('q')" in CHAT_HTML
    assert "status('Открываю страницу или результаты поиска…')" in CHAT_HTML
