"""Verify Android frame polling is cheap while every user action updates DOM."""
import pytest
from playwright.async_api import async_playwright
from chat_ui import CHAT_HTML

ONE_PIXEL = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
    "AAAAC0lEQVR42mP8/x8AAwMCAO+/8j0AAAAASUVORK5CYII="
)

@pytest.mark.asyncio
async def test_android_frames_update_without_repeated_dom_snapshot():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=['--disable-dev-shm-usage'])
        try:
            context = await browser.new_context()
            await context.add_init_script("""(imageData => {
                const wrap = obj => ({content:[{type:'text',text:JSON.stringify(obj)}]});
                // Canvas fixture avoids browser-dependent PNG decoder behaviour.
                window.createImageBitmap = async () => {
                    const canvas=document.createElement('canvas');
                    canvas.width=1;canvas.height=1;
                    return canvas;
                };
                window.events = [];
                window.openai = {
                    toolInput:{session_id:'synthetic-active-1234',site:'web.telegram.org'},
                    callTool:async (name,args)=>{
                        window.events.push(name);
                        if(name==='browser_screenshot')
                            return {content:[{type:'image',data:imageData,mimeType:'image/png'}]};
                        if(name==='browser_tabs')
                            return wrap({tabs:[{index:0,title:'Telegram',
                                    site:'web.telegram.org',active:true}],active:0,max_tabs:6});
                        if(name==='browser_snapshot')
                            return wrap({url:'https://web.telegram.org/k/',
                                    title:'Telegram fixture',text:'Fixture',
                                    elements:[{selector:'#test',i:0,tag:'button',text:'Test'}]});
                        if(name==='browser_back')return wrap({url:'https://web.telegram.org/k/'});
                        if(name==='browser_attach')
                            return wrap({attached:true,
                                    session_id:'synthetic-active-1234',site:'web.telegram.org'});
                        throw Error('unexpected '+name);
                    }
                };
            })(""" + repr(ONE_PIXEL) + """);""")
            page = await context.new_page()
            await page.route('https://minifish.test/', lambda route: route.fulfill(
                status=200,content_type='text/html',body=CHAT_HTML))
            await page.goto('https://minifish.test/')
            await page.wait_for_function(
                "() => window.events.filter(x=>x==='browser_snapshot').length>=1",
                timeout=15000)
            await page.wait_for_function(
                "() => window.events.filter(x=>x==='browser_screenshot').length>=2",
                timeout=15000)
            assert (await page.evaluate(
                "window.events.filter(x=>x==='browser_snapshot').length")) == 1
            await page.locator('#back').click()
            await page.wait_for_function(
                "() => window.events.filter(x=>x==='browser_snapshot').length>=2",
                timeout=15000)
            assert (await page.evaluate(
                "window.events.filter(x=>x==='browser_back').length")) == 1
            await context.close()
        finally:
            await browser.close()
