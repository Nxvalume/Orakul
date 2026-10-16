# MiniFish Android v11 - Protected field identity fix

Date: 2026-10-16, 23:37 Moscow time. Keep only branch minifish-v02; main not changed.

## Report
The user sent an Android screenshot from MiniFish owner-private Telegram Web mode. After choosing what they believed was Phone Number, phone digits appeared in the Country search/dropdown field. Do not repeat any displayed phone digits in logs or messages.

## Confirmed root cause
- engine.owner_fields exposed field positions (0, 1, ...), derived from a snapshot of currently visible inputs.
- engine.owner_control('fill_field') used fresh locator('input:visible,...').nth(field_index). Opening Country changes which inputs are visible/first, so a stale position can refer to a different input.
- chat_ui secureFields rebuilt the option list after interactions and auto-selected the first option (often Country), rather than retaining the explicitly selected element.

## Changes
- engine.py: each visible owner-only editable input gets a stable temporary data-minifish-owner-field reference; /fields returns opaque per-element ref, kind, and label (including Telegram input-field wrapper label) without field values. /control fill_field targets the exact same ref in the DOM, not nth(index). If the node was detached/replaced or no ref was supplied, reject with an actionable message; no fallback to numeric index. Typed data never appear in tool results/logs.
- chat_secure.py: forward field_ref via already-authorized HTTPS owner control only.
- chat_ui.py: secure dropdown no longer defaults to the first input, preserves an explicit selection only while its stable ref still exists; shows 'Phone Number, not Country' hint. Submits field_ref over owner-only HTTPS, never model tools; UI resource bumped v10 -> v11.
- server.py: old UI resource v10 compatibility alias, with current patched content. Old Android UI sending numeric index now fails closed instead of corrupting the wrong field.
- Tests: tests/test_owner_field_identity.py exercises actual Chromium inputs with Country, Phone Number, dynamic insertion (position changes), stale numeric index rejection, replacing input with a fresh node and rejecting stale ref; tests/test_owner_control.py migrated old mocks to stable refs; tests/test_mcp_apps_window.py checks new UI resource. No real user account or OTP used.

## Verified
- GitHub HEAD functional: 2bec33e3a6bc2b2971b1b48ae7d5f7b868eb1426.
- Three GitHub Actions workflows MiniFish CI, MiniFish checks, MiniFish stability CI passed after test updates.
- Render deployment dep-db98liifngtc739aabf0 is LIVE at that SHA.
- Safe Telegram status before deploy: private_login, logged_in false. Render restart cleared this unfinished session; after deploy status not_open / logged_in false / saved false / storage ok (no authenticated session was deleted).
- Following live deployment browser_open https://web.telegram.org/k/ created session 28c46e24-5c9c-4288-8547-994048db88bc; browser_window called once and host reported inline UI displayed.
- Protected fields in user's real Android client after v11 and real Telegram authorization are not yet confirmed; must be tested by owner in the owner-private UI. Never ask for phone number/password/OTP in ChatGPT.
- No paid resources or changes to main.
