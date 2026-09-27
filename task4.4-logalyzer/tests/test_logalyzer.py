import json
import os
import tempfile
import unittest
from pathlib import Path

from logalyzer.analysis import analyse_lines, parse_line
from logalyzer.history import History

GOOD = '203.0.113.9 - - [08/Sep/2026:05:26:18 +0000] "GET /health.html?x=1 HTTP/1.1" 200 3 "-" "ELB-HealthChecker/2.0"'
NOT_FOUND = '198.51.100.2 - - [08/Sep/2026:06:01:00 +0000] "GET /wp-login.php HTTP/1.1" 404 512 "-" "curl/8.5.0"'
SERVER_ERR = '198.51.100.2 - - [08/Sep/2026:06:02:00 +0000] "POST /notes HTTP/1.1" 500 - "-" "curl/8.5.0"'


class ParseTests(unittest.TestCase):
    def test_parses_combined_format_and_strips_query(self):
        entry = parse_line(GOOD)
        self.assertEqual(entry.ip, "203.0.113.9")
        self.assertEqual(entry.path, "/health.html")
        self.assertEqual(entry.status, 200)

    def test_dash_size_is_zero(self):
        self.assertEqual(parse_line(SERVER_ERR).size, 0)

    def test_rejects_garbage_and_bad_dates(self):
        self.assertIsNone(parse_line("not a log line"))
        self.assertIsNone(parse_line(GOOD.replace("08/Sep/2026", "99/Xyz/2026")))


class AnalysisTests(unittest.TestCase):
    def test_counts_and_error_rate(self):
        report = analyse_lines([GOOD, NOT_FOUND, SERVER_ERR, "junk", ""], source="t.log")
        self.assertEqual(report.total_lines, 4)  # blank line ignored
        self.assertEqual(report.parsed, 3)
        self.assertEqual(report.malformed, 1)
        self.assertEqual(report.status_classes, {"2xx": 1, "4xx": 1, "5xx": 1})
        self.assertAlmostEqual(report.error_rate, 0.6667, places=4)
        self.assertEqual(report.unique_ips, 2)
        json.dumps(report.to_dict())  # must be serialisable

    def test_empty_input_has_zero_error_rate(self):
        self.assertEqual(analyse_lines([], source="empty.log").error_rate, 0.0)


class HistoryTests(unittest.TestCase):
    def test_history_persists_across_connections(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = History(Path(tmp))
            first.record(run_utc="2026-09-26T00:00:00+00:00", source="a.log", sha256="abc",
                         lines=1, malformed=0, error_rate=0.0, duration_ms=1,
                         hostname="h", report_path="r")
            first.close()
            second = History(Path(tmp))  # simulates a new container on the same volume
            self.assertTrue(second.already_processed("abc"))
            self.assertEqual(len(second.recent()), 1)
            second.close()


if __name__ == "__main__":
    unittest.main()
