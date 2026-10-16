# MiniFish Android v7 — 2026-10-16
Project: Nxvalume/Orakul, branch minifish-v02. Leave main unchanged.

Android screenshot confirmed live Canvas displaying example.com. Browser address bar and navigation visible. Tab strip stuck at loading while page snapshot was pending.

Fixed UI ordering: request tabs independently and before slow snapshot. Retain rendered frame on DOM snapshot failure. Queue tap made during render for execution afterward. Kept owner-private restrictions. New resource: ui://minifish/browser-v7.html with compatibility for v4-v6.

Code revision: 9f010b968ff4eb18cc911e1ecf00acf9966d6e68. Three GitHub workflows success.
Render: dep-db97jb5g1s2s73c9kja0, live.
After deploy tested browser_open example.com, browser_tab_action new example.org, browser_tabs two entries, switch back to tab 0, and browser_window invoked once. Session recreation after deployment is expected.

Remaining: ask user to validate Android tab rendering and taps. Telegram sign-in and session persistence across restart remain unverified. Existing plugin published 0.5.2, HTTP remote MCP. No new paid resources.
