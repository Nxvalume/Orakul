"""Owner universal secure input works with OTP widgets and ordinary sites.

Use synthetic non-secret values only. Private input text must never appear in
tool results or model-visible MCP operations.
"""
from types import SimpleNamespace
import pytest

from playwright.async_api import async_playwright
from engine import BrowserEngine, Session
from chat_ui import CHAT_HTML


@pytest.mark.asyncio
async def test_owner_type_focused_splits_synthetic_code_across_five_boxes():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True, args=["--disable-dev-shm-usage"])
        try:
            context = await browser.new_context(viewport={"width": 390, "height": 760})
            page = await context.new_page()
            await page.set_content("""<!doctype html><html><body>
              <input id="country" placeholder="Country">
              <section id="verification">
                <label>Verification code</label>
                <input id="code0" maxlength="1" inputmode="numeric" autocomplete="one-time-code">
                <input id="code1" maxlength="1" inputmode="numeric">
                <input id="code2" maxlength="1" inputmode="numeric">
                <input id="code3" maxlength="1" inputmode="numeric">
                <input id="code4" maxlength="1" inputmode="numeric">
              </section>
              <script>
                [...document.querySelectorAll('#verification input')].forEach((field,i,all)=>{
                  field.addEventListener('input',()=>{
                    if(field.value && all[i+1])all[i+1].focus();
                  });
                });
              </script>
            </body></html>""")
            engine = BrowserEngine()
            engine._sessions["private-otp"] = Session(
                context=context, page=page, private_mode=True)
            # Do exactly what a tap on the viewport does: select a real field.
            box = await page.locator("#code0").bounding_box()
            result = await engine.owner_control("private-otp", "click",
                x=box["x"]+box["width"]/2,
                y=box["y"]+box["height"]/2)
            assert result["ok"] is True
            typed = await engine.owner_control("private-otp", "type_focused",
                                                text="24680")
            assert typed["ok"] is True
            assert "24680" not in str(typed)
            boxes = await page.locator("#verification input").evaluate_all(
                "(els) => els.map(el=>el.value)")
            assert boxes == list("24680"), boxes
            assert await page.locator("#country").input_value() == ""
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_owner_focused_input_fails_closed_when_page_has_no_selected_field():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True, args=["--disable-dev-shm-usage"])
        try:
            context = await browser.new_context(viewport={"width": 390, "height": 760})
            page = await context.new_page()
            await page.set_content("""<button id="button">Test button</button>
                <input id="ordinary" aria-label="Search" />""")
            engine = BrowserEngine()
            engine._sessions["private-form"] = Session(
                context=context, page=page, private_mode=True)
            with pytest.raises(ValueError, match="Коснитесь поля"):
                await engine.owner_control("private-form", "type_focused",
                                           text="test-non-secret")
            assert await page.locator("#ordinary").input_value() == ""
            await page.locator("#ordinary").click()
            sent = await engine.owner_control("private-form", "type_focused",
                                              text="ordinary test")
            assert sent["ok"] and "ordinary test" not in str(sent)
            assert await page.locator("#ordinary").input_value() == "ordinary test"
            with pytest.raises(ValueError, match="Введите текст"):
                await engine.owner_control("private-form", "type_focused", text="")
            await page.locator("#button").click()
            with pytest.raises(ValueError, match="Коснитесь поля"):
                await engine.owner_control("private-form", "type_focused",
                                           text="wrong destination")
        finally:
            await browser.close()


def test_secure_otp_does_not_enter_mcp_tool_bridge():
    assert "secureAction('type_focused',{text:value})" in CHAT_HTML
    assert "secureAction('fill_field',{field_ref,text:value})" in CHAT_HTML
    assert "secureRequest('control',{action,...extra})" in CHAT_HTML
    assert "call('type_focused'" not in CHAT_HTML
    assert "id=\"secureFieldAdvanced\"" in CHAT_HTML
    assert "Коснитесь нужного поля" in CHAT_HTML
    assert 'id="secureShot"' in CHAT_HTML
    assert CHAT_HTML.index('id="secureShot"') < CHAT_HTML.index('id="secureForm"')
    assert CHAT_HTML.index('id="secureForm"') < CHAT_HTML.index('id="secureBackspace"')
