"""Android widget must not operate model-visible controls in owner private mode."""
import re
import shutil
import subprocess

import pytest

from chat_ui import CHAT_HTML


def test_protected_mode_hides_public_controls_and_restores_only_after_release():
    assert 'id="publicControls"' in CHAT_HTML
    assert "function publicView(enabled)" in CHAT_HTML
    assert "publicView(false);" in CHAT_HTML
    assert "publicView(true);" in CHAT_HTML
    assert CHAT_HTML.count("if(!session||busy||secureToken||privateLocked)return;") == 1
    assert "if(!session||secureToken||privateLocked)return;" in CHAT_HTML
    assert "queuedAction=null;" in CHAT_HTML
    assert "if(session&&!busy&&!secureToken&&!privateLocked" in CHAT_HTML
    assert "if(ownerDenied(e))lockPrivateView(" in CHAT_HTML
    assert "invalidSessionIds.has(next)" in CHAT_HTML


def test_private_frame_does_not_embed_owner_token_in_image_url_or_mcp():
    assert "await drawFrame($('secureShot'),blob)" in CHAT_HTML
    assert "await drawFrame($('shot'),new Blob(" in CHAT_HTML
    assert "createImageBitmap(blob)" in CHAT_HTML
    assert "ctx.drawImage(bitmap,0,0)" in CHAT_HTML
    assert "URL.createObjectURL(blob)" not in CHAT_HTML
    assert "reader.readAsDataURL(blob)" not in CHAT_HTML
    assert '<canvas id="shot"' in CHAT_HTML
    assert '<canvas id="secureShot"' in CHAT_HTML
    assert "secureAction('telegram_open',{})" in CHAT_HTML
    assert "secureRequest('frame',null,'GET')" in CHAT_HTML
    assert "headers['X-MiniFish-Owner']=secureToken" in CHAT_HTML
    assert "bridge('tools/call',{name,arguments:args})" in CHAT_HTML
    assert "secureAction('scroll',{pixels:-460})" in CHAT_HTML
    assert "secureAction('scroll',{pixels:460})" in CHAT_HTML
    assert "Защищённый доступ истёк" in CHAT_HTML


def test_failed_profile_checkpoint_never_reenables_model_ui():
    assert "if(result.private_mode){" in CHAT_HTML
    block = CHAT_HTML.split("if(result.private_mode){", 1)[1].split("if(securePoll)", 1)[0]
    assert "return;" in block
    assert "result.save_error" in block


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js unavailable")
def test_embedded_browser_javascript_parses_without_syntax_errors():
    match = re.search(r"(?s)<script>\s*(.*?)\s*</script>", CHAT_HTML)
    assert match is not None
    result = subprocess.run(["node", "--check"], input=match.group(1),
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
async def test_android_successful_owner_unlock_opens_private_browser_panel():
    """Reproduce field report: successful owner password left details collapsed."""
    from playwright.async_api import async_playwright

    test_session = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=['--disable-dev-shm-usage'])
        try:
            context = await browser.new_context(viewport={'width': 390, 'height': 740})
            await context.add_init_script("""(() => {
                window.openai = {
                    toolInput: {session_id: '""" + test_session + """'},
                    callTool: () => new Promise(() => {})
                };
                window.fetch = async (url) => {
                    const u=String(url);
                    if(u.includes('/unlock'))
                        return new Response(JSON.stringify({token:'fake-local-test-token'}),
                            {status:200,headers:{'Content-Type':'application/json'}});
                    if(u.includes('/fields'))
                        return new Response(JSON.stringify({fields:[],viewport:{width:390,height:740}}),
                            {status:200,headers:{'Content-Type':'application/json'}});
                    if(u.includes('/tabs'))
                        return new Response(JSON.stringify({tabs:[],max_tabs:6}),
                            {status:200,headers:{'Content-Type':'application/json'}});
                    if(u.includes('/frame'))
                        return new Response(new Blob(['fake jpeg data'],{type:'image/jpeg'}),
                            {status:200,headers:{'Content-Type':'image/jpeg'}});
                    return new Response('{}',{status:200});
                };
            })();""")
            page = await context.new_page()
            await page.route('https://minifish-ui-test.invalid/', lambda route: route.fulfill(
                status=200, content_type='text/html', body=CHAT_HTML))
            await page.goto('https://minifish-ui-test.invalid/')
            await page.locator('#securePanel > summary').click()
            await page.locator('#ownerKey').fill('test-password-not-real')
            await page.locator('#unlock').click()
            await page.wait_for_function(
                "() => document.getElementById('status').textContent.includes('Защищённый ввод активен')",
                timeout=5000
            )
            assert await page.locator('#securePanel').evaluate('(el)=>el.open') is True
            assert await page.locator('#secureTools').is_visible()
            assert await page.locator('#secureShot').is_visible()
            assert not await page.locator('#screen').is_visible()
            assert await page.locator('#ownerKey').input_value() == ''

            # A mis-tap on the summary must not remove the only private screen.
            await page.locator('#securePanel > summary').click()
            await page.wait_for_timeout(120)
            assert await page.locator('#securePanel').evaluate('(el)=>el.open') is True
            assert await page.locator('#secureShot').is_visible()
        finally:
            await browser.close()


def test_android_owner_panel_is_explicitly_opened_after_valid_unlock():
    start = CHAT_HTML.index("async function activatePrivate(token){")
    block = CHAT_HTML[start:CHAT_HTML.index("async function tryResume(){", start)]
    assert "$('securePanel').open=true;" in block
    assert "$('securePanel').scrollIntoView(" in block
    assert "$('secureTools').hidden=false;" in block
    assert "if(secureToken && !$('securePanel').open) $('securePanel').open=true;" in CHAT_HTML
    assert "await activatePrivate(body.token);" in CHAT_HTML
    assert "securePoll=setInterval(()=>{void secureFrame()},1200);" in CHAT_HTML
