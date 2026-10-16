# MiniFish Android v9: Back is previous-page navigation
Date: 2026-10-16, local Moscow evening.

User clarified: button "Назад" must return to the previously visited WEB PAGE, not act as a left-arrow gesture or horizontal scroll.

Fixes:
- chat_ui.py: visible "← Назад" and "Вперёд →" named buttons in a dedicated toolbar above the URL/search field and above the Canvas; old unlabeled buttons removed below Canvas.
- Same change to protected owner-only view. JavaScript handler for public Back uses browser_back with current session_id; protected Back uses direct owner-only HTTPS secureAction('back'). Both preserve existing security boundaries and a single browser session.
- UI resource bumped from ui://minifish/browser-v8.html to v9; server retains v8 compatibility resource.
- tests/test_mcp_apps_window.py asserts button uniqueness, label, exact history handlers, and their position before the address bar/frame.

Checks:
- SHA 8e56cd87ad33eb9af6898e9082413f8ac0844315: three GitHub CI workflows success.
- Render deploy dep-db987hu1egvs73crcqlg, live.
- After deploy, created one MiniFish browser session c7126100-912a-438b-a089-22b824fa4eec. Navigated example.com -> example.org then browser_back returned to example.com; browser_snapshot reconfirmed exact URL.
- browser_window for that session invoked once; host confirmed embedded UI displayed in conversation.
- Android physical button tap and visibility still require owner-side observation. Do not mark verified without screenshot.

Branch minifish-v02 only; main unchanged. No new paid resources. Telegram login not involved.
