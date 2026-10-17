"""Android ChatGPT host can wrap FastMCP outputs in multiple envelopes."""
import pytest
from playwright.async_api import async_playwright
from chat_ui import CHAT_HTML

SESSION = "e3c3a4a2-ff92-4444-aa55-0c93e0c3b655"


@pytest.mark.asyncio
async def test_android_widget_attaches_existing_backend_through_nested_mcp_envelopes():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
        try:
            context = await browser.new_context(viewport={"width": 390, "height": 720})
            await context.add_init_script("""(() => {
                const sid='e3c3a4a2-ff92-4444-aa55-0c93e0c3b655';
                window.testCalls=[];
                window.openai={
                  callTool:async(name,args)=>{
                    window.testCalls.push({name,args});
                    if(name==='browser_attach')return {
                      result:{structuredContent:{result:{attached:true,
                        session_id:sid,site:'example.com'}}}};
                    if(name==='browser_tabs')return {result:{
                       content:[{type:'text',text:JSON.stringify({result:{
                          tabs:[{index:0,title:'Example Domain',site:'example.com',
                                 active:true}],active:0,max_tabs:6}})}]}};
                    if(name==='browser_screenshot')throw Error('Frame temporarily unavailable');
                    if(name==='browser_snapshot')return {result:{text:JSON.stringify({
                        url:'https://example.com/',title:'Example Domain',elements:[]})}};
                    throw Error('Unexpected tool '+name);
                  }
                };
            })();""")
            page = await context.new_page()
            await page.route("https://minifish.test/", lambda route: route.fulfill(
                status=200, content_type="text/html", body=CHAT_HTML))
            await page.goto("https://minifish.test/")
            await page.wait_for_function(
                "() => document.querySelector('#tabs').textContent.includes('Example Domain')",
                timeout=12000)
            calls = await page.evaluate("window.testCalls")
            assert any(c["name"] == "browser_attach" for c in calls)
            assert any(c["name"] == "browser_tabs" and c["args"]["session_id"] == SESSION
                       for c in calls)
            assert not any(c["name"] == "browser_open" for c in calls)
            assert "Браузер временно недоступен" not in await page.locator("#status").inner_text()
            assert "Подключение" not in await page.locator("#tabs").inner_text()
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_android_widget_decodes_multiple_host_response_shapes():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
        try:
            context = await browser.new_context()
            await context.add_init_script("window.openai={callTool:async()=>({})};")
            page = await context.new_page()
            await page.route("https://minifish.test/", lambda route: route.fulfill(
                status=200, content_type="text/html", body=CHAT_HTML))
            await page.goto("https://minifish.test/")
            # The production decoder is scoped inside the widget closure;
            # evaluate that exact function source rather than assuming a global.
            decoder = "function data(result){" + CHAT_HTML.split(" function data(result){", 1)[1].split("\n // Some clients", 1)[0]
            results = await page.evaluate("(function(){\n" + decoder + "\n" + """ 
              const response={attached:true,session_id:'example-session-12'};
              const text={type:'text',text:JSON.stringify(response)};
              const variants=[
                response,{result:response},{structuredContent:{result:response}},
                {result:{structuredContent:{result:response}}},
                {result:{content:[text]}},{output:{content:[text]}},
                {data:{text:JSON.stringify(response)}}
              ];
              return variants.map(v=>data(v)?.session_id||null);
            })();""")
            assert results == ["example-session-12"] * 7
        finally:
            await browser.close()
