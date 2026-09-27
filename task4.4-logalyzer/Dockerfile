# syntax=docker/dockerfile:1
# SWE40006 Task 4.4 - logalyzer, a containerised non-web CLI tool

ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /opt/logalyzer

# ---------- test stage: `docker build --target test .` runs the unit tests ----------
FROM base AS test
COPY logalyzer/ ./logalyzer/
COPY tests/ ./tests/
RUN python -m unittest discover -s tests -v

# ---------- runtime stage: standard library only, no pip install needed ----------
FROM base AS runtime
LABEL org.opencontainers.image.title="swe40006-logalyzer" \
      org.opencontainers.image.description="SWE40006 Task 4.4 - access log analysis CLI" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.source="https://github.com/Karam1008/swe40006-task4-docker"

ARG APP_UID=10001
RUN useradd --system --uid ${APP_UID} --no-create-home --shell /usr/sbin/nologin logalyzer \
 && mkdir -p /data/input /data/output /data/state \
 && chown -R logalyzer:logalyzer /data

# Code stays owned by root, so the running user cannot modify it
COPY logalyzer/ ./logalyzer/

ENV INPUT_DIR=/data/input \
    OUTPUT_DIR=/data/output \
    STATE_DIR=/data/state \
    LOG_LEVEL=INFO \
    WATCH_INTERVAL=10

USER logalyzer

# ENTRYPOINT fixes the executable; CMD supplies default arguments that
# `docker run <image> analyze ...` replaces. Exec form means Python is PID 1
# and receives SIGTERM directly.
ENTRYPOINT ["python", "-m", "logalyzer"]
CMD ["--help"]
