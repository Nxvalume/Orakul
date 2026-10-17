"""Mobile private telephone replacement/clearing regression tests.

Only fictional values are used; real owner inputs stay in the HTTPS-only channel.
"""
import pytest
from playwright.async_api import async_playwright

from chat_ui import CHAT_HTML
from engine import BrowserEngine, Session


@pytest.mark.asyncio
async def test_private_phone_replaces_old_international_number_and_country_reacts():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
        try:
            context = await browser.new_context(viewport={"width": 390, "height": 760})
            page = await context.new_page()
            await page.set_content("""<!doctype html><html><body>
              <label>Country <span id="country">Germany</span></label>
              <input id="phone" type="tel" autocomplete="tel" value="+49 123 456">
              <script>
                const phone = document.querySelector('#phone');
                phone.addEventListener('input', () => {
                  document.querySelector('#country').textContent =
                    phone.value.startsWith('+7') ? 'Russia' :
                    phone.value.startsWith('+49') ? 'Germany' : 'Choose country';
                });
              </script>
            </body></html>""")
            engine = BrowserEngine()
            engine._sessions["phone-replace"] = Session(
                context=context, page=page, private_mode=True)
            await page.locator("#phone").click()
            result = await engine.owner_control(
                "phone-replace", "type_focused", text="+7 123 000")
            assert result["ok"] is True
            assert "+7 123 000" not in str(result)
            assert "+49 123 456" not in str(result)
            assert await page.locator("#phone").input_value() == "+7 123 000"
            assert await page.locator("#country").inner_text() == "Russia"

            erased = await engine.owner_control("phone-replace", "clear_focused")
            assert erased["ok"] is True
            assert await page.locator("#phone").input_value() == ""
            assert await page.locator("#country").inner_text() == "Choose country"
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_clear_focused_does_not_clear_arbitrary_other_field():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
        try:
            context = await browser.new_context()
            page = await context.new_page()
            await page.set_content("""<button id="action">Action</button>
                <input id="phone" type="tel" value="old-example">
                <input id="country" value="Germany">""")
            engine = BrowserEngine()
            engine._sessions["phone-no-target"] = Session(
                context=context, page=page, private_mode=True)
            with pytest.raises(ValueError, match="Коснитесь поля"):
                await engine.owner_control("phone-no-target", "clear_focused")
            assert await page.locator("#phone").input_value() == "old-example"
            await page.locator("#country").click()
            await engine.owner_control("phone-no-target", "clear_focused")
            assert await page.locator("#country").input_value() == ""
            assert await page.locator("#phone").input_value() == "old-example"
        finally:
            await browser.close()


def test_android_secure_panel_exposes_two_clear_actions_without_mcp_text():
    assert 'id="secureClearDraft"' in CHAT_HTML
    assert 'id="secureClearFocused"' in CHAT_HTML
    assert "secureAction('clear_focused',{})" in CHAT_HTML
    assert "$('secureValue').value=''" in CHAT_HTML
    assert "secureAction('type_focused',{text:value})" in CHAT_HTML
    assert "secureRequest('control',{action,...extra})" in CHAT_HTML
