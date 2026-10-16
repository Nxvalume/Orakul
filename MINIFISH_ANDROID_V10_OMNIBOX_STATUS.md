# MiniFish Android v10 — one search bar above frame

Date: 2026-10-16 (Moscow time). Existing GitHub repo Nxvalume/Orakul, branch minifish-v02. Do not change main.

Owner's UX clarification: enter natural language ("телеграмм") in one search/address bar ABOVE remote browser frame; search results appear inside remote browser screenshot BELOW, without a second search box in webpage. Preserve typed words in bar; user typing must not be replaced by URL during 4.6s screenshot polling.

Changes:
- chat_ui.py resource ui://minifish/browser-v10.html, normal and private address bars display "Найти" action and use resolveOmnibox to open a site or MiniFish /search?q= query. displayAddressOrQuery extracts human-readable q from search URL. While navUrl has focus, render polling does not overwrite it. Blur keyboard on submitted search.
- search_view.py formats large, mobile-readable results only, no redundant embedded search form; official-site HTTPS links preserved.
- server.py retains v9 resource as compatibility alias, new default v10.
- tests/test_mcp_apps_window.py, tests/test_search_view.py confirm ordering, labels, query persistence, removal of redundant search form, mobile font sizes and compatibility.
- Production SHA: aab641b65a0e668b3523364aa6ec72029cdc9047. GitHub Actions CI/checks/stability all passed. Render deploy dep-db98bnm1egvs73crqk7g confirmed live.
- On live server: new browser session ed8072a4-68d9-46fe-9184-5af663d7ce78; browser_goto /search?q=телеграмм, snapshot showed title "Поиск: телеграмм · MiniFish", plain text "Результаты: телеграмм", multiple real Telegram-related links, NO redundant field. Real browser_click official telegram.org succeeded; browser_back returned to results with previous title. browser_window called once, host responded embedded UI displayed.
- Still needs direct Android touch/keyboard acceptance confirmation by owner; backend success alone does not prove phone tap/input behavior.
- Telegram signed-in persistence not involved or revalidated; never collect Telegram secrets in chat.

No new paid resources. Plugin package v0.5.2 unchanged; UI v10 is server-side.
