"""Command-line interface for logalyzer.

Sub-commands
  analyze          analyse log files once, write reports, exit
  watch            long-running: poll the input directory and analyse new files
  history          show previous runs stored on the state volume
  generate-sample  write a synthetic access log for demonstration

Exit codes
  0 success | 1 unexpected error | 2 usage error or no input | 3 error-rate threshold exceeded
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import signal
import socket
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import __version__
from .analysis import analyse_file, to_markdown
from .history import History, file_sha256

EXIT_OK, EXIT_ERROR, EXIT_USAGE, EXIT_THRESHOLD = 0, 1, 2, 3

INPUT_DIR = Path(os.getenv("INPUT_DIR", "./data/input"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./data/output"))
STATE_DIR = Path(os.getenv("STATE_DIR", "./data/state"))

log = logging.getLogger("logalyzer")


def configure_logging() -> None:
    logging.Formatter.converter = time.gmtime
    logging.basicConfig(
        stream=sys.stdout,  # stdout is what `docker logs` collects
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)sZ level=%(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def process_file(path: Path, history: History, top: int, fmt: str, sha256: str | None = None):
    started = time.perf_counter()
    sha256 = sha256 or file_sha256(path)
    report = analyse_file(path, top=top)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    base = OUTPUT_DIR / f"{path.stem}-{utc_stamp()}"
    suffix = 1
    while base.with_suffix(".json").exists() or base.with_suffix(".md").exists():
        base = OUTPUT_DIR / f"{path.stem}-{utc_stamp()}-{suffix}"  # never overwrite a report
        suffix += 1
    written = []
    if fmt in ("json", "both"):
        base.with_suffix(".json").write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
        written.append(base.with_suffix(".json"))
    if fmt in ("md", "both"):
        base.with_suffix(".md").write_text(to_markdown(report), encoding="utf-8")
        written.append(base.with_suffix(".md"))

    duration_ms = int((time.perf_counter() - started) * 1000)
    run_id = history.record(
        run_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        source=path.name, sha256=sha256, lines=report.total_lines,
        malformed=report.malformed, error_rate=report.error_rate,
        duration_ms=duration_ms, hostname=socket.gethostname(),
        report_path=str(written[0]),
    )
    log.info(
        'analysed file="%s" lines=%d parsed=%d malformed=%d error_rate=%.2f%% duration_ms=%d run_id=%d',
        path.name, report.total_lines, report.parsed, report.malformed,
        report.error_rate * 100, duration_ms, run_id,
    )
    for out in written:
        log.info('report written path="%s"', out)
    return report


def find_inputs(pattern: str) -> list[Path]:
    return sorted(p for p in INPUT_DIR.glob(pattern) if p.is_file())


def cmd_analyze(args) -> int:
    files = [Path(f) if Path(f).is_absolute() or Path(f).exists() else INPUT_DIR / f for f in args.files] \
        if args.files else find_inputs(args.pattern)
    missing = [f for f in files if not f.is_file()]
    if missing:
        log.error('input not found paths="%s"', ", ".join(map(str, missing)))
        return EXIT_USAGE
    if not files:
        log.error('no input files matched dir="%s" pattern="%s"', INPUT_DIR, args.pattern)
        return EXIT_USAGE

    history = History(STATE_DIR)
    worst = 0.0
    try:
        for path in files:
            worst = max(worst, process_file(path, history, args.top, args.format).error_rate)
    finally:
        history.close()

    if args.fail_on_error_rate is not None and worst > args.fail_on_error_rate:
        log.warning("threshold exceeded error_rate=%.2f%% limit=%.2f%%",
                    worst * 100, args.fail_on_error_rate * 100)
        return EXIT_THRESHOLD
    log.info("analyze complete files=%d", len(files))
    return EXIT_OK


def cmd_watch(args) -> int:
    stop = threading.Event()

    def request_stop(signum, _frame):
        log.info("received %s - finishing current cycle, then shutting down", signal.Signals(signum).name)
        stop.set()

    # Without these handlers a Python PID 1 would ignore SIGTERM and Docker
    # would SIGKILL it after the 10 s grace period.
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    history = History(STATE_DIR)
    log.info('watch started version=%s input="%s" interval_s=%d pid=%d',
             __version__, INPUT_DIR, args.interval, os.getpid())
    cycles = 0
    try:
        while not stop.is_set():
            cycles += 1
            new = 0
            for path in find_inputs(args.pattern):
                sha = file_sha256(path)
                if history.already_processed(sha):
                    continue
                process_file(path, history, args.top, args.format, sha256=sha)
                new += 1
            log.debug("cycle=%d new_files=%d", cycles, new)
            if new:
                log.info("cycle=%d processed new_files=%d", cycles, new)
            stop.wait(args.interval)
    finally:
        history.close()
    log.info("watch stopped cleanly cycles=%d", cycles)
    return EXIT_OK


def cmd_history(args) -> int:
    history = History(STATE_DIR)
    try:
        rows = history.recent(args.limit)
    finally:
        history.close()
    if not rows:
        print(f"No runs recorded yet in {STATE_DIR / 'history.db'}")
        return EXIT_OK
    head = ("id", "run_utc", "source", "lines", "malformed", "error_rate", "ms", "container")
    table = [head] + [(str(r[0]), r[1], r[2], str(r[3]), str(r[4]), f"{r[5]:.2%}", str(r[6]), r[7]) for r in rows]
    widths = [max(len(row[i]) for row in table) for i in range(len(head))]
    for i, row in enumerate(table):
        print("  ".join(cell.ljust(w) for cell, w in zip(row, widths)))
        if i == 0:
            print("  ".join("-" * w for w in widths))
    return EXIT_OK


def cmd_generate(args) -> int:
    rng = random.Random(args.seed)
    out = Path(args.out) if args.out else INPUT_DIR / "sample-access.log"
    out.parent.mkdir(parents=True, exist_ok=True)
    paths = ["/", "/notes", "/api/info", "/healthz", "/health.html",
             "/wp-login.php", "/favicon.ico", "/missing-page"]
    path_weights = [40, 12, 8, 20, 10, 3, 4, 3]
    agents = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "curl/8.5.0",
              "ELB-HealthChecker/2.0", "python-requests/2.32"]
    ips = [f"203.0.113.{n}" for n in range(1, 25)] + [f"198.51.100.{n}" for n in range(1, 8)]
    start = datetime.now(timezone.utc) - timedelta(hours=6)
    with out.open("w", encoding="utf-8") as handle:
        for i in range(args.lines):
            if rng.random() < args.malformed_ratio:
                handle.write("this line is not in combined log format\n")
                continue
            path = rng.choices(paths, weights=path_weights)[0]
            method = "POST" if path == "/notes" else "GET"
            status = (404 if path in ("/wp-login.php", "/missing-page", "/favicon.ico")
                      else rng.choices([200, 304, 500, 503], weights=[90, 6, 3, 1])[0])
            when = (start + timedelta(seconds=i * 21600 / max(args.lines, 1))).strftime("%d/%b/%Y:%H:%M:%S +0000")
            size = 0 if status == 304 else rng.randint(120, 9000)
            handle.write(f'{rng.choice(ips)} - - [{when}] "{method} {path} HTTP/1.1" {status} {size} '
                         f'"-" "{rng.choice(agents)}"\n')
    log.info('sample generated path="%s" lines=%d seed=%s', out, args.lines, args.seed)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="logalyzer",
        description="Analyse web server access logs (Combined Log Format) and write JSON/Markdown reports.",
        epilog="Directories: INPUT_DIR, OUTPUT_DIR and STATE_DIR environment variables.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p):
        p.add_argument("--pattern", default="*.log", help="glob for files in INPUT_DIR (default: *.log)")
        p.add_argument("--top", type=int, default=5, help="entries in each top-N table (default: 5)")
        p.add_argument("--format", choices=["json", "md", "both"], default="both")

    p = sub.add_parser("analyze", help="analyse log files once and exit")
    p.add_argument("files", nargs="*", help="files to analyse (default: every match in INPUT_DIR)")
    p.add_argument("--fail-on-error-rate", type=float, metavar="RATIO",
                   help="exit with code 3 if any file's 4xx+5xx rate exceeds RATIO, e.g. 0.10")
    add_common(p)
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("watch", help="poll INPUT_DIR and analyse each new file once")
    p.add_argument("--interval", type=int, default=int(os.getenv("WATCH_INTERVAL", "10")),
                   help="seconds between scans (default: WATCH_INTERVAL or 10)")
    add_common(p)
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("history", help="list previous runs")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_history)

    p = sub.add_parser("generate-sample", help="write a synthetic access log")
    p.add_argument("--lines", type=int, default=2000)
    p.add_argument("--seed", type=int, default=40006)
    p.add_argument("--malformed-ratio", type=float, default=0.01)
    p.add_argument("--out", help="output file (default: INPUT_DIR/sample-access.log)")
    p.set_defaults(func=cmd_generate)
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except PermissionError as exc:
        log.error('permission denied path="%s" - the mounted directory must be writable by UID %d', exc.filename, os.getuid())
        return EXIT_ERROR
    except Exception:  # noqa: BLE001 - last-resort handler so failures are logged, not silent
        log.exception("unexpected failure")
        return EXIT_ERROR
