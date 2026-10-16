"""Owner-only input controls must not target the wrong Telegram field after DOM changes."""
import pytest
from playwright.async_api import async_playwright
from engine import BrowserEngine, Session
from chat_ui import CHAT_HTML


@pytest.mark.asyncio
async def test_owner_phone_field_identity_survives_country_search_insertion():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=['--disable-dev-shm-usage'])
        try:
            context = await browser.new_context(viewport={"width": 390, "height": 750})
            page = await context.new_page()
            await page.set_content("""
                <div class="input-field"><label class="input-field-label">Country</label>
                    <input id="country" type="text" placeholder="Country"></div>
                <div class="input-field"><label class="input-field-label">Phone Number</label>
                    <input id="phone" type="tel" placeholder="Phone Number"></div>
            """)
            eng = BrowserEngine()
            eng._sessions["private-phone"] = Session(
                context=context, page=page, private_mode=True
            )
            fields = (await eng.owner_fields("private-phone"))["fields"]
            assert len(fields) == 2
            phone = next(field for field in fields if field["label"] == "Phone Number")
            assert phone["ref"]
            assert all("value" not in field for field in fields)

            # Opening Country inserts a new visible input at the start, shifting
            # every numeric index. Ref must still find the original phone input.
            await page.evaluate("""() => {
                const field = document.createElement('input');
                field.placeholder = 'Search country';
                field.id = 'country-search';
                document.body.prepend(field);
            }""")
            await eng.owner_control("private-phone", "fill_field",
                                    field_ref=phone["ref"], text="5550100")
            assert await page.locator("#phone").input_value() == "5550100"
            assert await page.locator("#country").input_value() == ""
            assert await page.locator("#country-search").input_value() == ""

            refreshed = (await eng.owner_fields("private-phone"))["fields"]
            assert next(field for field in refreshed
                        if field["label"] == "Phone Number")["ref"] == phone["ref"]
            assert "5550100" not in str(refreshed)

            # Numeric indices used by stale mobile clients must fail closed.
            with pytest.raises(ValueError, match="Обновите окно MiniFish"):
                await eng.owner_control("private-phone", "fill_field",
                                        field_index=1, text="5559999")
            assert await page.locator("#country").input_value() == ""
            assert await page.locator("#phone").input_value() == "5550100"

            # When reactive Telegram replaces the node, never fall back to its
            # position, even when the replacement shares type/placeholder.
            await page.locator("#phone").evaluate(
                """el => el.replaceWith(el.cloneNode(true))""")
            with pytest.raises(ValueError, match="Выбранное поле изменилось"):
                await eng.owner_control("private-phone", "fill_field",
                                        field_ref=phone["ref"], text="5559999")
            assert await page.locator("#phone").input_value() == ""
        finally:
            await browser.close()


def test_private_widget_requires_explicit_field_pick_and_identity():
    assert "option.value=fld.ref;" in CHAT_HTML
    assert "secureAction('fill_field',{field_ref,text:value})" in CHAT_HTML
    assert "field_index:index,text:value" not in CHAT_HTML
    assert "select.value=previous;" in CHAT_HTML
    assert "else select.value='';" in CHAT_HTML
    assert "Выберите поле (Phone Number, не Country)" in CHAT_HTML
