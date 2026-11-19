# Executive Admin API (FastAPI). Internal only: the web container proxies /api/* to it.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt constraints.txt ./
RUN pip install -r requirements.txt -c constraints.txt

COPY app ./app

# Run as an unprivileged user; uploads (documents, item photos) live on a volume.
RUN useradd --uid 10001 --create-home ea \
 && mkdir -p /data/uploads \
 && chown -R ea:ea /data
USER ea

ENV ENV=production \
    UPLOAD_DIR=/data/uploads
VOLUME ["/data/uploads"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"

# One worker on purpose: the SLA escalation loop and sign-in throttle live in this process.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--workers", "1"]
