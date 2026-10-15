"""Universal mobile MiniFish controls: real Chromium tests."""
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from playwright.async_api import async_playwright
from engine import BrowserEngine, Session


@pytest.mark.asyncio
async def test_native_mobile_actions_click_page_button():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=['--disable-dev-shm-usage'])
        try:
            ctx = await browser.new_context()
            page = await ctx.new_page()
            await page.set_content('''<main><button id="login">LOG IN BY PHONE NUMBER</button>
                <button id="other">Other website button</button><p id="result">before</p>
                <script>document.querySelector('#login').onclick = () =>
                    document.querySelector('#result').textContent = 'clicked phone option';</script></main>''')
            eng = BrowserEngine()
            eng._sessions['native-buttons'] = Session(context=ctx, page=page)
            result = await eng.owner_elements('native-buttons')
            assert any('LOG IN BY PHONE NUMBER' in a['label'] for a in result['actions'])
            action = next(a for a in result['actions'] if 'LOG IN BY PHONE NUMBER' in a['label'])
            assert (await eng.owner_control('native-buttons', 'click_element',
                                             element_index=action['index']))['ok']
            assert await page.locator('#result').inner_text() == 'clicked phone option'
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_owner_screen_coordinate_clicks_real_browser():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=['--disable-dev-shm-usage'])
        try:
            ctx = await browser.new_context(viewport={'width':1280,'height':900})
            page = await ctx.new_page()
            await page.set_content('''<button style="position:absolute;left:300px;top:200px;
                width:260px;height:100px" id="target">Click me</button>
                <p id="result">before</p>
                <script>document.querySelector('#target').onclick = () =>
                    document.querySelector('#result').textContent='clicked';</script>''')
            eng = BrowserEngine()
            eng._sessions['touch-test'] = Session(context=ctx,page=page)
            assert (await eng.owner_control('touch-test','click',x=430,y=250))['ok']
            assert await page.locator('#result').inner_text()=='clicked'
        finally:
            await browser.close()


def test_generic_mobile_page_has_stable_pointer_layer_and_native_controls():
    view = Path(__file__).resolve().parents[1].joinpath('live_view.py').read_text()
    server = Path(__file__).resolve().parents[1].joinpath('server.py').read_text()
    assert 'id="tapLayer"' in view
    assert "'pointerdown'" in view and "'pointerup'" in view
    assert 'setPointerCapture' in view
    assert "ownerAction('click_element',{element_index:a.index})" in view
    assert "ownerAction('navigate',{url})" in view
    assert "ownerAction('scroll',{pixels:550})" in view
    assert view.index('id="urlBar"') < view.index('id="live"') < view.index('Дополнительно: вход в Telegram')
    assert "app.add_route('/live/elements',elements_api(engine)" in server


@pytest.mark.asyncio
async def test_android_tap_overlay_emits_real_chromium_viewport_coordinates():
    from live_view import PAGE
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=['--disable-dev-shm-usage'])
        try:
            ctx = await browser.new_context(viewport={'width':393, 'height':860},
                                            is_mobile=True, has_touch=True)
            page = await ctx.new_page()
            await page.set_content(PAGE)
            await page.evaluate("""() => {
                current='mobile-test'; streaming=true; currentViewport={width:1280,height:900};
                window.__actions=[];
                ownerAction=async(action,payload)=>{window.__actions.push({action,payload});return true};
                refreshActions=()=>{}; refreshFields=()=>{};
                const img=document.querySelector('#live');
                img.style.display='block';
                document.querySelector('#placeholder').style.display='none';
                img.src='data:image/svg+xml,%3Csvg%20xmlns="http://www.w3.org/2000/svg"%20width="1280"%20height="900"%3E%3C/svg%3E';
            }""")
            await page.locator('#live').evaluate('(img) => img.decode()')
            await page.locator('#tapLayer').tap()
            await page.wait_for_function('window.__actions.length > 0',timeout=4000)
            result = await page.evaluate('window.__actions[0]')
            assert result['action']=='click'
            assert 250 <= result['payload']['x'] <= 1030
            assert 200 <= result['payload']['y'] <= 700
        finally:
            await browser.close()
