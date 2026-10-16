# MiniFish Android Search (omnibox) - verified release, 2026-10-16

Repo: Nxvalume/Orakul
Branch: minifish-v02 (main untouched)
Existing personal plugin: plugins_6ace90389e2c819192f0fb8f6fd58657, v0.5.2
Render service: srv-db789o5g1s2s739g756g
Live deploy: dep-db97tprncjis73cvpklg
Live source SHA: d5f424cdf9582c638512c97b11820e02d98660fb

## User request
On ChatGPT Android MiniFish address bars, typing a word such as "телеграмм" and submitting should produce actual web search results, without typing an exact URL. Direct domains must still open normally. Both public and owner-private address bars need this behavior.

## Changes
- chat_ui.py: UI resource bumped to ui://minifish/browser-v8.html; retained v7 and earlier compatibility via server.py. Both address inputs are search-keyboard inputs. resolveOmnibox(raw) distinguishes explicit HTTPS URL / bare domain / plain search text; rejects non-HTTPS explicit URLs and credential-bearing URLs. Searches navigate to https://nxval-minifish-2026.onrender.com/search?q=... instead of captcha-prone third-party search UI. Private mode uses owner-only HTTPS control, never MCP to transmit credentials.
- search_view.py: fixed-host Bing RSS reader with bounded requests/timeouts, capped XML size, no external entity declarations, 12 HTTPS-only results maximum, HTML escaping of all titles/links/descriptions. Outputs a mobile readable HTML page with clickable results and native search form. No data is saved and results have noindex.
- server.py: GET /search search page route; historical UI resources retained.
- Dockerfile includes search_view.py in COPY and compileall. Regression tests cover URL vs Cyrillic search, XML safety, XSS, invalid URLs, Docker module presence, failures without secret logs.

## Verification
- All three GitHub Actions workflows (MiniFish CI, MiniFish checks, MiniFish stability CI) green for SHA d5f424cd; Render Docker build succeeded and deploy dep-db97tprncjis73cvpklg is live.
- Google Search showed challenge, DDG timed out, Bing HTML returned only a header, Yandex and Brave challenged; direct Bing RSS successfully returned results.
- LIVE MiniFish browser_open to /search?q=телеграмм returned session 8c87616d-c64e-44f5-b709-3d2c704a859c, title "Поиск: телеграмм · MiniFish". browser_snapshot showed 9 real results including Telegram Messenger, Telegram Web, Telegram Desktop, Google Play, Wikipedia; real HTTPS links.
- browser_click on first official Telegram result navigated to https://telegram.org/ (title Telegram Messenger); browser_back returned to the same search results; browser_snapshot reconfirmed titles. Thus links and browser history work in deployed Chromium.
- browser_window invoked once for this search session; the host reported that embedded UI was displayed in ChatGPT.

## Remaining verification
- User must verify text entry, keyboard search submit, and visible results/clicks INSIDE native Android ChatGPT iframe; server tests don't replace mobile UI validation.
- Telegram authenticated session persistence over a Render restart remains unverified.
- Keep protected owner mode and main branch unchanged. Do not state Android acceptance success before user evidence.
