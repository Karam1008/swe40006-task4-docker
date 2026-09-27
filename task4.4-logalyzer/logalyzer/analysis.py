"""Parsing and analysis of Apache/Nginx Combined Log Format access logs."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# 203.0.113.9 - - [08/Sep/2026:05:26:18 +0000] "GET /health.html HTTP/1.1" 200 3 "-" "ELB-HealthChecker/2.0"
LINE_RE = re.compile(
    r'(?P<ip>\S+) \S+ \S+ \[(?P<time>[^\]]+)\] '
    r'"(?P<method>[A-Z]+) (?P<path>\S+) (?P<proto>[^"]+)" '
    r'(?P<status>\d{3}) (?P<size>\d+|-)'
    r'(?: "(?P<referrer>[^"]*)" "(?P<agent>[^"]*)")?'
)
TIME_FORMAT = "%d/%b/%Y:%H:%M:%S %z"


@dataclass
class LogEntry:
    ip: str
    time: datetime
    method: str
    path: str
    status: int
    size: int
    agent: str


def parse_line(line: str) -> LogEntry | None:
    """Return a LogEntry, or None if the line is not valid Combined Log Format."""
    match = LINE_RE.match(line.strip())
    if not match:
        return None
    try:
        when = datetime.strptime(match["time"], TIME_FORMAT)
    except ValueError:
        return None
    return LogEntry(
        ip=match["ip"],
        time=when,
        method=match["method"],
        path=match["path"].split("?", 1)[0],
        status=int(match["status"]),
        size=0 if match["size"] == "-" else int(match["size"]),
        agent=match["agent"] or "",
    )


@dataclass
class Report:
    source: str
    total_lines: int = 0
    parsed: int = 0
    malformed: int = 0
    bytes_served: int = 0
    first_seen: str | None = None
    last_seen: str | None = None
    status_classes: dict = field(default_factory=dict)
    methods: dict = field(default_factory=dict)
    top_paths: list = field(default_factory=list)
    top_ips: list = field(default_factory=list)
    top_errors: list = field(default_factory=list)
    requests_per_hour: dict = field(default_factory=dict)
    unique_ips: int = 0

    @property
    def error_rate(self) -> float:
        errors = self.status_classes.get("4xx", 0) + self.status_classes.get("5xx", 0)
        return round(errors / self.parsed, 4) if self.parsed else 0.0

    def to_dict(self) -> dict:
        data = self.__dict__.copy()
        data["error_rate"] = self.error_rate
        return data


def analyse_lines(lines, source: str, top: int = 5) -> Report:
    report = Report(source=source)
    statuses, methods, paths, ips, errors, hours = (Counter() for _ in range(6))
    first = last = None

    for line in lines:
        if not line.strip():
            continue
        report.total_lines += 1
        entry = parse_line(line)
        if entry is None:
            report.malformed += 1
            continue
        report.parsed += 1
        report.bytes_served += entry.size
        statuses[f"{entry.status // 100}xx"] += 1
        methods[entry.method] += 1
        paths[entry.path] += 1
        ips[entry.ip] += 1
        hours[entry.time.strftime("%Y-%m-%d %H:00")] += 1
        if entry.status >= 400:
            errors[f"{entry.status} {entry.path}"] += 1
        first = entry.time if first is None or entry.time < first else first
        last = entry.time if last is None or entry.time > last else last

    report.status_classes = dict(sorted(statuses.items()))
    report.methods = dict(methods.most_common())
    report.top_paths = paths.most_common(top)
    report.top_ips = ips.most_common(top)
    report.top_errors = errors.most_common(top)
    report.requests_per_hour = dict(sorted(hours.items()))
    report.unique_ips = len(ips)
    report.first_seen = first.isoformat() if first else None
    report.last_seen = last.isoformat() if last else None
    return report


def analyse_file(path: Path, top: int = 5) -> Report:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return analyse_lines(handle, source=path.name, top=top)


def to_markdown(report: Report) -> str:
    def table(rows, head):
        out = [f"| {head[0]} | {head[1]} |", "|---|---:|"]
        out += [f"| `{k}` | {v} |" for k, v in rows] or ["| (none) | 0 |"]
        return "\n".join(out)

    return "\n\n".join([
        f"# Access log report: {report.source}",
        f"- Lines read: **{report.total_lines}** (parsed {report.parsed}, malformed {report.malformed})\n"
        f"- Time range: {report.first_seen} to {report.last_seen}\n"
        f"- Unique client IPs: {report.unique_ips}\n"
        f"- Bytes served: {report.bytes_served:,}\n"
        f"- Error rate (4xx + 5xx): **{report.error_rate:.2%}**",
        "## Status classes\n\n" + table(report.status_classes.items(), ("Class", "Requests")),
        "## Top paths\n\n" + table(report.top_paths, ("Path", "Requests")),
        "## Top client IPs\n\n" + table(report.top_ips, ("IP", "Requests")),
        "## Most frequent errors\n\n" + table(report.top_errors, ("Status and path", "Count")),
    ]) + "\n"
