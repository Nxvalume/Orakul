"""The ChatGPT Android widget behaves like a browser, not a static screenshot."""
import pytest
from playwright.async_api import async_playwright

from chat_ui import CHAT_HTML, CHAT_UI_URI


def test_v21_keeps_a_real_browser_surface_and_separate_private_path():
    assert CHAT_UI_URI.endswith('/browser-v21.html')
    assert CHAT_HTML.index('id="tabs"') < CHAT_HTML.index('id="navUrl"') < CHAT_HTML.index('id="shot"')
    assert 'touch-action:none' in CHAT_HTML
    assert "bindRemoteGesture($('shot')" in CHAT_HTML
    assert "bindRemoteGesture($('secureShot')" in CHAT_HTML
    assert "secureAction('scroll',{pixels,axis})" in CHAT_HTML
    assert "act('browser_scroll',{session_id:session,pixels,axis})" in CHAT_HTML
    assert "$('text').focus(); // Open Android keyboard" in CHAT_HTML
    assert "$('topbar').hidden=!enabled;" in CHAT_HTML


@pytest.mark.asyncio
async def test_android_swipe_scroll_and_field_tap_use_existing_chromium_session():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=['--disable-dev-shm-usage'])
        try:
            context = await browser.new_context(viewport={'width': 393, 'height': 860},
                                                is_mobile=True, has_touch=True)
            await context.add_init_script("""(() => {
                const reply = obj => ({content:[{type:'text',text:JSON.stringify(obj)}]});
                window.createImageBitmap = async () => {
                    const image=document.createElement('canvas');
                    image.width=800;image.height=560;return image;
                };
                window.calls=[];
                window.openai = {
                    toolInput:{session_id:'synthetic-v21-session',site:'example.com'},
                    callTool:async (name,args) => {
                        window.calls.push({name,args});
                        if(name==='browser_screenshot')return {content:[{
                            type:'image',mimeType:'image/png',data:'AA=='}]};
                        if(name==='browser_tabs')return reply({tabs:[{
                            index:0,title:'Example',site:'example.com',active:true}],
                            active:0,max_tabs:6});
                        if(name==='browser_snapshot')return reply({
                            url:'https://example.com/',title:'Example',text:'Example',
                            elements:[{selector:'#search',i:0,tag:'input',type:'search',
                                name:'search',id:'search'}]});
                        if(name==='browser_scroll')return reply({url:'https://example.com/',
                            scroll_pixels:args.pixels,axis:args.axis});
                        if(name==='browser_tap')return reply({url:'https://example.com/',
                            clicked:'#search'});
                        throw Error('Unexpected tool '+name);
                    }
                };
            })();""")
            page = await context.new_page()
            await page.route('https://minifish.test/', lambda route: route.fulfill(
                status=200, content_type='text/html', body=CHAT_HTML))
            await page.goto('https://minifish.test/')
            await page.wait_for_function("""() =>
                document.querySelector('#shot').width===800 &&
                document.querySelector('#status').textContent.startsWith('Готово')""",
                timeout=15000)
            assert await page.locator('#screen').evaluate(
                'el => el.getBoundingClientRect().top < 270')

            await page.locator('#shot').evaluate("""el => {
                const r=el.getBoundingClientRect(),x=r.left+r.width/2,y=r.top+r.height/2;
                el.dispatchEvent(new PointerEvent('pointerdown',{
                    bubbles:true,pointerId:1,isPrimary:true,pointerType:'touch',clientX:x,clientY:y}));
                el.dispatchEvent(new PointerEvent('pointerup',{
                    bubbles:true,pointerId:1,isPrimary:true,pointerType:'touch',clientX:x,clientY:y-85}));
            }""")
            await page.wait_for_function("window.calls.some(c=>c.name==='browser_scroll')")
            scroll = await page.evaluate("window.calls.find(c=>c.name==='browser_scroll').args")
            assert scroll['session_id'] == 'synthetic-v21-session'
            assert scroll['axis'] == 'vertical'
            assert scroll['pixels'] > 80

            await page.wait_for_function(
                "document.querySelector('#status').textContent.startsWith('Готово')")
            await page.locator('#shot').evaluate("""el => {
                const r=el.getBoundingClientRect(),x=r.left+r.width/2,y=r.top+r.height/2;
                el.dispatchEvent(new PointerEvent('pointerdown',{
                    bubbles:true,pointerId:2,isPrimary:true,pointerType:'touch',clientX:x,clientY:y}));
                el.dispatchEvent(new PointerEvent('pointerup',{
                    bubbles:true,pointerId:2,isPrimary:true,pointerType:'touch',clientX:x,clientY:y}));
            }""")
            await page.wait_for_function("window.calls.some(c=>c.name==='browser_tap')")
            await page.wait_for_function("document.activeElement?.id==='text'")
            assert await page.locator('#field').input_value() == '#search'
            assert not await page.locator('#secureTools').is_visible()
            await context.close()
        finally:
            await browser.close()
