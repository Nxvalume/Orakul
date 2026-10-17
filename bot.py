"""Fresh NXVAL Telegram lead intake bot. Python stdlib, no reused application code."""
from __future__ import annotations
import hmac, html, json, logging, os, threading, time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

TOKEN = os.getenv("BOT_TOKEN", "").strip()
SECRET = os.getenv("WEBHOOK_SECRET", "").strip()
PUBLIC_URL = os.getenv("PUBLIC_URL", "").strip().rstrip("/")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
PORT = int(os.getenv("PORT", "10000"))
CONFIGURED = bool(TOKEN and SECRET and PUBLIC_URL and OWNER_ID > 0)
SEEN = deque(maxlen=1000)
SEEN_SET = set()
LOCK = threading.Lock()
INTRO = ("Здравствуйте! Здесь можно заказать Telegram-бота.\n\n"
         "Опишите одним сообщением задачу, обязательные функции, "
         "желаемые сроки и бюджет (если известны).\n\n"
         "Сообщение попадёт разработчику для оценки. "
         "Отправка заявки не означает заключение договора.")

def api(method: str, payload: dict) -> dict:
    if not CONFIGURED:
        raise RuntimeError("Bot not configured")
    data = json.dumps(payload, ensure_ascii=False).encode()
    req = Request("https://api.telegram.org/bot" + TOKEN + "/" + method,
                  data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=12) as response:
            obj = json.loads(response.read(262144))
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError("Telegram request failed") from exc
    if not obj.get("ok"):
        raise RuntimeError("Telegram declined request")
    return obj

def reply(chat: int, text: str) -> None:
    api("sendMessage", {"chat_id": chat, "text": text, "disable_web_page_preview": True})

def lead_text(msg: dict) -> str:
    u = msg.get("from") or {}
    uid = int(u.get("id") or 0)
    name = " ".join(str(u.get(k) or "") for k in ("first_name", "last_name")).strip() or "Без имени"
    username = str(u.get("username") or "")
    request = str(msg.get("text") or "")[:3500]
    handle = "@" + html.escape(username) if username else "не указан"
    return (f"<b>Новая заявка на Telegram-бота</b>\n"
            f"От: <a href=\"tg://user?id={uid}\">{html.escape(name)}</a>\n"
            f"Username: {handle}\nID: {uid}\n\n"
            f"<b>Запрос:</b>\n{html.escape(request)}")

def process(update: dict) -> None:
    msg = update.get("message") or {}
    if not isinstance(msg, dict) or (msg.get("chat") or {}).get("type") != "private":
        return
    chat = int(msg["chat"]["id"])
    user = int((msg.get("from") or {}).get("id") or 0)
    text = str(msg.get("text") or "").strip()
    cmd = text.split(maxsplit=1)[0].split("@", 1)[0].lower() if text else ""
    if cmd in ("/start", "/help"):
        reply(chat, INTRO)
    elif cmd == "/id":
        reply(chat, f"Ваш Telegram ID: {user}")
    elif cmd == "/admin":
        reply(chat, "Заявки приходят лично владельцу." if user == OWNER_ID else "Нет доступа.")
    elif not text or cmd.startswith("/"):
        reply(chat, "Отправьте текст заявки одним сообщением или используйте /start.")
    elif user == OWNER_ID:
        reply(chat, "Бот принимает заявки. Для проверки используйте другой Telegram-аккаунт.")
    else:
        api("sendMessage", {"chat_id": OWNER_ID, "text": lead_text(msg),
                            "parse_mode": "HTML", "disable_web_page_preview": True})
        reply(chat, "Заявка передана разработчику на рассмотрение.")

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        pass
    def answer(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def do_GET(self) -> None:
        self.answer(200, {"ok": True, "configured": CONFIGURED}) if self.path == "/health" else self.answer(404, {"ok": False})
    def do_POST(self) -> None:
        if self.path != "/telegram":
            self.answer(404, {"ok": False}); return
        if not CONFIGURED:
            self.answer(503, {"ok": False}); return
        if not hmac.compare_digest(self.headers.get("X-Telegram-Bot-Api-Secret-Token", ""), SECRET):
            self.answer(403, {"ok": False}); return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self.answer(400, {"ok": False}); return
        if not 0 < length <= 65536:
            self.answer(413, {"ok": False}); return
        try:
            update = json.loads(self.rfile.read(length))
            uid = int(update["update_id"])
        except (ValueError, KeyError, TypeError):
            self.answer(400, {"ok": False}); return
        with LOCK:
            if uid in SEEN_SET:
                self.answer(200, {"ok": True, "duplicate": True}); return
            try:
                process(update)
            except RuntimeError:
                logging.error("Telegram API error; update not acknowledged")
                self.answer(502, {"ok": False}); return
            if len(SEEN) == SEEN.maxlen:
                SEEN_SET.discard(SEEN[0])
            SEEN.append(uid)
            SEEN_SET.add(uid)
        self.answer(200, {"ok": True})

def register_webhook() -> None:
    if not CONFIGURED:
        logging.warning("Waiting for server configuration")
        return
    for delay in (0, 5, 15, 30, 60):
        if delay: time.sleep(delay)
        try:
            api("setWebhook", {"url": PUBLIC_URL + "/telegram", "secret_token": SECRET,
                               "allowed_updates": ["message"], "drop_pending_updates": False})
            logging.info("Webhook registered")
            return
        except RuntimeError:
            logging.warning("Webhook registration retry")
    logging.error("Webhook setup failed")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    threading.Thread(target=register_webhook, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
