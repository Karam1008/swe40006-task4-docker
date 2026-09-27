# syntax=docker/dockerfile:1
# SWE40006 Task 4.3 - optimised multi-stage Dockerfile for DockNotes

ARG PYTHON_VERSION=3.12

# ---------- Stage 1: builder - resolve and install dependencies into a venv ----------
FROM python:${PYTHON_VERSION}-slim AS builder
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
# Copied alone so this expensive layer is reused until requirements.txt changes
COPY requirements.txt .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install -r requirements.txt

# ---------- Stage 2: runtime - only the venv and application code ----------
FROM python:${PYTHON_VERSION}-slim AS runtime

LABEL org.opencontainers.image.title="swe40006-docknotes" \
      org.opencontainers.image.description="SWE40006 Task 4.3 - DockNotes FastAPI web app" \
      org.opencontainers.image.source="https://github.com/Karam1008/swe40006-task4-docker"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_ENV=production \
    APP_VERSION=1.0.0

# Unprivileged runtime user - the process never runs as root
RUN groupadd --system app && useradd --system --gid app --no-create-home app

WORKDIR /srv
COPY --from=builder /opt/venv /opt/venv
COPY app/ ./app/

USER app
EXPOSE 8000

# Uses the Python standard library, so no curl/wget needs to be added to the image
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]

# Exec form: uvicorn is PID 1 and receives SIGTERM directly from `docker stop`
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
