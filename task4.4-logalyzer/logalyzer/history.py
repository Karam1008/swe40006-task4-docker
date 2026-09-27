"""Run history kept in SQLite on a Docker named volume, so it survives the
container being removed and recreated."""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_utc      TEXT NOT NULL,
    source       TEXT NOT NULL,
    sha256       TEXT NOT NULL,
    lines        INTEGER NOT NULL,
    malformed    INTEGER NOT NULL,
    error_rate   REAL NOT NULL,
    duration_ms  INTEGER NOT NULL,
    hostname     TEXT NOT NULL,
    report_path  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_sha ON runs(sha256);
"""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


class History:
    def __init__(self, state_dir: Path):
        state_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = state_dir / "history.db"
        self.conn = sqlite3.connect(self.db_path)
        self.conn.executescript(SCHEMA)

    def already_processed(self, sha256: str) -> bool:
        return self.conn.execute("SELECT 1 FROM runs WHERE sha256 = ? LIMIT 1", (sha256,)).fetchone() is not None

    def record(self, **row) -> int:
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        with self.conn:
            cur = self.conn.execute(f"INSERT INTO runs ({cols}) VALUES ({marks})", tuple(row.values()))
        return cur.lastrowid

    def recent(self, limit: int = 10) -> list[tuple]:
        return self.conn.execute(
            "SELECT id, run_utc, source, lines, malformed, error_rate, duration_ms, hostname "
            "FROM runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    def close(self) -> None:
        self.conn.close()
