"""Reproduce stale Android MCP iframe session in a real Chromium page."""
import pytest
from playwright.async_api import async_playwright
from chat_ui import CHAT_HTML


@pytest.mark.asyncio
async def test_old_chatgpt_session_id_recovers_without_reopening_private_login():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=['--disable-dev-shm-usage'])
        try:
            context = await browser.new_context()
            await context.add_init_script("""(() => {
                const oldId='old-session-1234', newId='fresh-session-5678';
                window.testCalls=[];
                const txt=data=>({content:[{type:'text',text:JSON.stringify(data)}]});
                window.openai={
                    toolInput:{session_id:oldId},
                    callTool:async (name,args)=>{
                        window.testCalls.push({name,args});
                        if(name==='browser_attach')return txt({attached:false,reason:'not_open'});
                        if(name==='browser_open'){
                            if(args.url!=='https://example.com/')throw Error('Wrong recovery URL');
                            return txt({session_id:newId,url:args.url});
                        }
                        if(name==='browser_tabs'){
                            if(args.session_id===oldId)throw Error('INVALID_ARGUMENT: stale');
                            return txt({tabs:[{index:0,title:'Recovered page',
                                site:'example.com',active:true}],active:0,max_tabs:6});
                        }
                        if(name==='browser_screenshot'){
                            if(args.session_id===oldId)throw Error('INVALID_ARGUMENT: stale');
                            throw Error('No screenshot in mock browser');
                        }
                        throw Error('Unknown tool: '+name);
                    }
                };
            })();""")
            page = await context.new_page()
            await page.route('https://minifish.test/', lambda route: route.fulfill(
                status=200, content_type='text/html', body=CHAT_HTML))
            await page.goto('https://minifish.test/')
            await page.wait_for_function(
                "() => document.querySelector('#tabs').textContent.includes('Recovered page')",
                timeout=15000)
            calls = await page.evaluate('window.testCalls')
            assert [x['name'] for x in calls].count('browser_open') == 1
            assert [x['name'] for x in calls].count('browser_attach') >= 1
            assert all(x['name'] != 'browser_open' or
                       x['args']['url'] == 'https://example.com/' for x in calls)
            assert not await page.locator('#secureTools').is_visible()
            assert 'INVALID_ARGUMENT' not in await page.locator('#status').inner_text()
        finally:
            await browser.close()
