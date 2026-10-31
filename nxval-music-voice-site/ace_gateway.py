"""NXVAL Music ACE Music pass-through gateway.
Receives a key only per request, never stores it. Fixed upstream and restricted CORS.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
import urllib.error
import urllib.request

API_ROOT = "https://api.acemusic.ai"
SITE_ORIGIN = "https://nxval-music-voice-studio.onrender.com"
MAX_INPUT = 180000
MAX_RESPONSE = 32000000

class Handler(BaseHTTPRequestHandler):
    server_version = "NXVALMusic/3.0"
    def log_message(self, fmt, *args):
        # Disable logging of requests and content entirely; keys must not leak.
        pass

    def send_json(self, status, payload):
        value = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        origin = self.headers.get("Origin", "")
        if origin == SITE_ORIGIN:
            self.send_header("Access-Control-Allow-Origin", SITE_ORIGIN)
            self.send_header("Vary", "Origin")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(value)))
        self.end_headers()
        self.wfile.write(value)

    def do_OPTIONS(self):
        if self.path not in ("/models", "/generate") or self.headers.get("Origin") != SITE_ORIGIN:
            self.send_response(403)
            self.end_headers()
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", SITE_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "300")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"status": "ok", "provider": "ACE Music", "key_stored": False})
        else:
            self.send_json(404, {"error": "Not found"})

    def do_POST(self):
        if self.path not in ("/models", "/generate"):
            self.send_json(404, {"error": "Not found"})
            return
        if self.headers.get("Origin") not in ("", SITE_ORIGIN):
            self.send_json(403, {"error": "Forbidden origin"})
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if n <= 0 or n > MAX_INPUT:
                self.send_json(413, {"error": "Payload too large"})
                return
            body = json.loads(self.rfile.read(n))
            if not isinstance(body, dict):
                raise ValueError()
            key = body.get("key", "")
            if not isinstance(key, str) or not (8 <= len(key) <= 400) or "\n" in key or "\r" in key:
                self.send_json(400, {"error": "Введите корректный ключ ACE Music"})
                return
            path = "/v1/models" if self.path == "/models" else "/v1/chat/completions"
            request_data = None
            if self.path == "/generate":
                caption = body.get("caption", "")
                lyrics = body.get("lyrics", "")
                delivery = body.get("delivery", "")
                if any(not isinstance(v, str) for v in (caption, lyrics, delivery)):
                    self.send_json(400, {"error": "Invalid text input"})
                    return
                if not lyrics.strip() or len(lyrics) > 14000 or len(caption) > 5000 or len(delivery) > 4000:
                    self.send_json(400, {"error": "Введите текст песни; размер промпта ограничен"})
                    return
                duration = body.get("duration", 180)
                bpm = body.get("bpm", 92)
                if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not (20 <= duration <= 240):
                    self.send_json(400, {"error": "Некорректная длительность"})
                    return
                if isinstance(bpm, bool) or not isinstance(bpm, (int, float)) or not (60 <= bpm <= 200):
                    self.send_json(400, {"error": "Некорректный BPM"})
                    return
                lang = body.get("language", "ru")
                if lang not in ("ru","en","de","fr","es","unknown"):
                    lang = "ru"
                desc = caption.strip()
                if delivery.strip():
                    desc += "\nVocal delivery: " + delivery.strip()
                model = body.get("model", "acemusic/acestep-v1.5-turbo")
                if not isinstance(model, str) or not re.fullmatch(r"acemusic/[A-Za-z0-9._-]{3,70}", model):
                    self.send_json(400, {"error": "Некорректный идентификатор модели ACE Music"})
                    return
                contents = "<prompt>" + desc + "</prompt><lyrics>" + lyrics.strip() + "</lyrics>"
                job = {
                    "model": model,
                    "messages": [{"role":"user", "content":contents}],
                    "stream": False,
                    "thinking": True,
                    "use_format": False,
                    "audio_config": {
                        "duration": int(duration),
                        "bpm": int(bpm),
                        "format": "mp3",
                        "vocal_language": lang
                    }
                }
                request_data = json.dumps(job).encode("utf-8")
            req = urllib.request.Request(
                API_ROOT + path,
                data=request_data,
                headers={"Authorization": "Bearer " + key, "Accept": "application/json",
                         "Content-Type":"application/json", "User-Agent":"NXVAL-Music-Voice/3.0"},
                method="POST" if request_data is not None else "GET"
            )
            try:
                with urllib.request.urlopen(req, timeout=230) as resp:
                    raw = resp.read(MAX_RESPONSE + 1)
                    if len(raw) > MAX_RESPONSE:
                        self.send_json(502, {"error": "Ответ музыкального API слишком большой"})
                        return
                    data = json.loads(raw)
                    self.send_json(200, data)
            except urllib.error.HTTPError as e:
                # Do not echo upstream error body: it could inadvertently contain private data.
                code = e.code
                messages = {401: "Неверный или неактивный API-ключ",
                            403:"Ключ не имеет доступа к модели",
                            404:"Endpoint ACE Music недоступен",
                            429:"Лимит запросов ACE Music исчерпан",
                            502:"Ошибка ACE Music 502 — попробуй позже",
                            503:"ACE Music временно недоступен"}
                self.send_json(code if 400 <= code < 600 else 502,
                               {"error": messages.get(code, "ACE Music вернул HTTP " + str(code))})
            except (urllib.error.URLError, TimeoutError) as e:
                self.send_json(504, {"error":"ACE Music не ответил. Проверь доступность сервиса или попробуй позже."})
        except (json.JSONDecodeError, ValueError, TypeError):
            self.send_json(400, {"error":"Неверный формат запроса"})
        except Exception:
            self.send_json(502, {"error":"Не удалось выполнить запрос к ACE Music"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
