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
                    toolInput:{session_id:oldId,site:'web.telegram.org'},
                    callTool:async (name,args)=>{
                        window.testCalls.push({name,args});
                        if(name==='browser_attach')return txt({attached:false,reason:'not_open'});
                        if(name==='browser_open'){
                            if(args.url!=='https://web.telegram.org/k/')throw Error('Wrong recovery URL');
                            return txt({session_id:newId,url:args.url});
                        }
                        if(name==='browser_tabs'){
                            if(args.session_id===oldId)throw Error('INVALID_ARGUMENT: stale');
                            return txt({tabs:[{index:0,title:'Recovered page',
                                site:'web.telegram.org',active:true}],active:0,max_tabs:6});
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
                       x['args']['url'] == 'https://web.telegram.org/k/' for x in calls)
            assert not await page.locator('#secureTools').is_visible()
            assert 'INVALID_ARGUMENT' not in await page.locator('#status').inner_text()
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_stale_example_placeholder_is_replaced_with_saved_telegram_not_duplicated():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=['--disable-dev-shm-usage'])
        try:
            context = await browser.new_context()
            await context.add_init_script("""(() => {
                window.calls = [];
                const encode=data=>({content:[{type:'text',text:JSON.stringify(data)}]});
                window.openai={
                    toolInput:{session_id:'expired-telegram-99',site:'web.telegram.org'},
                    callTool:async(name,args)=>{
                        window.calls.push({name,args});
                        if(name==='browser_attach')return encode({
                            attached:true,session_id:'placeholder-example-13',site:'example.com'});
                        if(name==='browser_close')return encode({closed:true});
                        if(name==='browser_open')return encode({
                            session_id:'reloaded-telegram-77',url:'https://web.telegram.org/k/'});
                        if(name==='browser_tabs')return encode({
                            tabs:[{index:0,title:'Telegram',site:'web.telegram.org',active:true}],
                            active:0,max_tabs:6});
                        if(name==='browser_screenshot')throw Error('No screenshot in fixture');
                        throw Error('Unexpected tool '+name);
                    }
                };
            })();""")
            page=await context.new_page()
            await page.route('https://minifish.test/', lambda route: route.fulfill(
                status=200, content_type='text/html',body=CHAT_HTML))
            await page.goto('https://minifish.test/')
            await page.wait_for_function(
                "() => window.calls.some(c=>c.name==='browser_open')", timeout=15000)
            calls=await page.evaluate('window.calls')
            assert [x['name'] for x in calls].index('browser_close') < [x['name'] for x in calls].index('browser_open')
            assert [x['name'] for x in calls].count('browser_open') == 1
            assert [x for x in calls if x['name']=='browser_close'][0]['args']['session_id']=='placeholder-example-13'
            assert [x for x in calls if x['name']=='browser_open'][0]['args']['url']=='https://web.telegram.org/k/'
            assert not await page.locator('#secureTools').is_visible()
        finally:
            await browser.close()


def test_unknown_expired_session_never_opens_example_or_any_account_by_default():
    assert "if(!recoveryUrl)" in CHAT_HTML
    assert "const opened=data(await call('browser_open',{url:recoveryUrl}))" in CHAT_HTML
    assert "browser_open',{url:'https://example.com/'" not in CHAT_HTML
