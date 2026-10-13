FROM mcr.microsoft.com/playwright/python:v1.63.0-noble
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY engine.py server.py web_auth.py dashboard.py smoke.py ./
ENV PYTHONUNBUFFERED=1
USER pwuser
EXPOSE 8000
CMD ["sh", "-c", "if [ \"${MINIFISH_STARTUP_SMOKE:-0}\" = \"1\" ]; then python smoke.py; fi; exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
