"""DockNotes - SWE40006 Task 4.3 custom web application.

A small deployment notes board. Notes and a visit counter live in Redis,
which runs in a separate container on an internal-only Docker network.
All configuration comes from environment variables so the same image runs
unchanged on a laptop and on a cloud host.
"""
import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path

import redis
from fastapi import FastAPI, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

APP_NAME = os.getenv("APP_NAME", "DockNotes")
APP_ENV = os.getenv("APP_ENV", "development")
APP_VERSION = os.getenv("APP_VERSION", "dev")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
MAX_NOTES = int(os.getenv("MAX_NOTES", "25"))
MAX_NOTE_LENGTH = 280

NOTES_KEY = "docknotes:notes"
VISITS_KEY = "docknotes:visits"

store = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
)

app = FastAPI(title=APP_NAME, version=APP_VERSION)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def container_info() -> dict:
    return {
        "app": APP_NAME,
        "version": APP_VERSION,
        "environment": APP_ENV,
        "container_hostname": socket.gethostname(),
        "redis_host": f"{REDIS_HOST}:{REDIS_PORT}",
    }


def redis_ok() -> bool:
    try:
        return bool(store.ping())
    except redis.RedisError:
        return False


@app.get("/")
def index(request: Request):
    notes, visits, storage_error = [], None, None
    try:
        visits = store.incr(VISITS_KEY)
        notes = [json.loads(n) for n in store.lrange(NOTES_KEY, 0, MAX_NOTES - 1)]
    except redis.RedisError as exc:
        storage_error = f"Notes can't be loaded: Redis at {REDIS_HOST}:{REDIS_PORT} is unreachable ({type(exc).__name__})."
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "info": container_info(),
            "notes": notes,
            "visits": visits,
            "storage_error": storage_error,
            "max_len": MAX_NOTE_LENGTH,
        },
    )


@app.post("/notes")
def add_note(text: str = Form(...), author: str = Form("")):
    text = text.strip()[:MAX_NOTE_LENGTH]
    if text:
        note = {
            "text": text,
            "author": author.strip()[:40] or "anonymous",
            "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "served_by": socket.gethostname(),
        }
        try:
            store.lpush(NOTES_KEY, json.dumps(note))
            store.ltrim(NOTES_KEY, 0, MAX_NOTES - 1)
        except redis.RedisError:
            pass  # the index page reports the storage problem
    # 303 so the browser follows with GET and a refresh does not resubmit
    return RedirectResponse(url="/", status_code=303)


@app.get("/api/info")
def api_info():
    info = container_info()
    info["redis_reachable"] = redis_ok()
    try:
        info["visits"] = int(store.get(VISITS_KEY) or 0)
        info["notes_stored"] = store.llen(NOTES_KEY)
    except redis.RedisError:
        info["visits"] = info["notes_stored"] = None
    return info


@app.get("/healthz")
def healthz():
    """Liveness probe used by the Dockerfile HEALTHCHECK.

    Reports Redis status but returns 200 regardless, so a Redis outage does
    not cause Docker to restart a web container that is itself healthy.
    """
    return JSONResponse({"status": "ok", "redis": "up" if redis_ok() else "down"})
