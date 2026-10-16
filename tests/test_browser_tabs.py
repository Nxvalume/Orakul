"""Real Playwright tab management in one browser context, with owner isolation."""
import re
import shutil
import subprocess

import pytest
from playwright.async_api import async_playwright

from engine import BrowserEngine, Session
from chat_ui import CHAT_HTML


@pytest.mark.asyncio
async def test_real_chromium_tabs_open_switch_close_and_preserve_page_contents():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=['--disable-dev-shm-usage'])
        try:
            context = await browser.new_context(viewport={'width': 480, 'height': 720})
            first = await context.new_page()
            await first.set_content("<title>First tab</title><button id='test'>Click</button><p id='count'>0</p><script>document.querySelector('#test').onclick = () => document.querySelector('#count').textContent='1'</script>")
            engine = BrowserEngine()
            sid = "tabs-test"
            engine._sessions[sid] = Session(context=context, page=first)
            assert (await engine.tab_list(sid))["tabs"][0]["title"] == "First tab"

            new = await engine.tab_action(sid, "new")
            assert new["count"] == 2 and new["active"] == 1
            second = engine.get(sid).page
            await second.set_content("<title>Second tab</title><p>Second page</p>")
            assert second is not first
            listed = await engine.tab_list(sid)
            assert [t["title"] for t in listed["tabs"]] == ["First tab", "Second tab"]

            assert (await engine.tab_action(sid, "switch", index=0))["active"] == 0
            # Regression: merely having more than one tab must not silently
            # switch to the last tab after the assistant clicks a button.
            await engine.click(sid, "#test")
            assert engine.get(sid).page is first
            assert await first.locator("#count").inner_text() == "1"

            assert (await engine.tab_action(sid, "switch", index=1))["active"] == 1
            assert "Second page" in (await engine.snapshot(sid))["text"]
            assert (await engine.tab_action(sid, "close", index=1))["active"] == 0
            assert engine.get(sid).page is first
            assert second.is_closed()
            assert (await engine.tab_action(sid, "close", index=0))["count"] == 1
            assert engine.get(sid).page.url == "about:blank"
            assert len(context.pages) == 1
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_private_tabs_require_owner_capability_even_to_list_tab_titles():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=['--disable-dev-shm-usage'])
        try:
            context = await browser.new_context()
            page = await context.new_page()
            await page.set_content("<title>Private session</title>")
            engine = BrowserEngine()
            sid = "private-tabs"
            engine._sessions[sid] = Session(context=context, page=page, private_mode=True)
            with pytest.raises(PermissionError):
                await engine.tab_list(sid)
            with pytest.raises(PermissionError):
                await engine.tab_action(sid, "new")
            assert (await engine.tab_list(sid, owner=True))["tabs"][0]["title"] == "Private session"
            assert (await engine.tab_action(sid, "new", owner=True))["count"] == 2
            assert engine._sessions[sid].private_mode
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_bound_to_six_tabs_and_rejects_invalid_actions_and_indices():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=['--disable-dev-shm-usage'])
        try:
            context = await browser.new_context()
            page = await context.new_page()
            eng = BrowserEngine()
            eng._sessions["limited-tabs"] = Session(context=context, page=page)
            for _ in range(5):
                await eng.tab_action("limited-tabs", "new")
            assert (await eng.tab_list("limited-tabs"))["max_tabs"] == 6
            with pytest.raises(ValueError, match="6 вкладок"):
                await eng.tab_action("limited-tabs", "new")
            for action,index in (("switch", -1), ("close", 6), ("switch", True), ("delete-all", 0)):
                with pytest.raises(ValueError):
                    await eng.tab_action("limited-tabs", action, index=index)
            assert len(context.pages) == 6
        finally:
            await browser.close()


def test_mobile_tab_strip_uses_live_mcp_and_owner_https_tools_only():
    assert 'id="tabs"' in CHAT_HTML
    assert 'id="secureTabs"' in CHAT_HTML
    assert "call('browser_tabs',{session_id:session})" in CHAT_HTML
    assert "act('browser_tab_action',{session_id:session,action,index})" in CHAT_HTML
    assert "secureRequest('tabs',{})" in CHAT_HTML
    assert "secureRequest('tab_action',{action,index})" in CHAT_HTML
    assert "secureToken" in CHAT_HTML
    assert "paintTabs('tabs'" in CHAT_HTML
    assert "paintTabs('secureTabs'" in CHAT_HTML
    assert "add.disabled=info.tabs.length>=info.max_tabs" in CHAT_HTML


@pytest.mark.asyncio
async def test_new_mcp_tabs_tools_are_widget_callable_without_spawning_duplicate_windows():
    from server import mcp
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    for name in ("browser_tabs", "browser_tab_action"):
        meta = tools[name].meta
        assert meta["openai/widgetAccessible"] is True
        assert meta["ui"]["visibility"] == ["model", "app"]
        assert "resourceUri" not in meta["ui"]
