FROM mcr.microsoft.com/playwright/python:v1.63.0-noble
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY engine.py server.py web_auth.py dashboard.py smoke.py oauth_server.py live_view.py state_store.py remote_store.py jobs.py ./
COPY tests/ ./tests/
RUN python -m compileall -q engine.py server.py web_auth.py dashboard.py oauth_server.py live_view.py state_store.py jobs.py \
    && pip install --no-cache-dir pytest==8.4.2 pytest-asyncio==1.2.0 \
    && MINIFISH_PASSWORD=test-owner-password-long MINIFISH_SECRET=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
       MINIFISH_PUBLIC_URL=https://nxval-minifish-2026.onrender.com \
       BROWSER_ALLOWED_DOMAINS=example.com python -m pytest -q tests/

ENV PYTHONUNBUFFERED=1
USER pwuser
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
