# NXVAL Sales Agent

Brand-new, standalone Telegram lead-intake bot. No code imported or copied from any previous project.

- /start and /help: explain the single-message request format.
- Any inbound private text from a customer is forwarded to OWNER_ID via Telegram Bot API.
- /id displays the sender's numeric Telegram ID; /admin is restricted to owner.
- No database, AI, customer payments, unsolicited bulk messages, old projects or paid APIs.

Run Python 3.12 or newer: python bot.py

Secret environment: BOT_TOKEN (from BotFather), WEBHOOK_SECRET (random), PUBLIC_URL (HTTPS web address), OWNER_ID (numeric Telegram ID). PORT defaults to 10000.

Visit /health to confirm server state. The service registers Telegram webhook automatically on startup if configured. Owner must first send /start to the bot to receive new requests.

Limitations: leads appear in owner's Telegram inbox, not a CRM. Free hosting can sleep or restart, so delivery may be delayed. Some updates can be repeated after restart. There are no sales guarantees or payment functions.
