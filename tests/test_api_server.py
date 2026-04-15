import sqlite3
import tempfile
import unittest
from pathlib import Path

from api.api_server import MonitorHandler


SCHEMA = """
CREATE TABLE alerts (
    alert_id TEXT PRIMARY KEY,
    alert_time TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    agent_name TEXT,
    project_id TEXT,
    message TEXT,
    notified TEXT,
    acknowledged INTEGER DEFAULT 0,
    resolved_at TEXT
);
"""


class APIServerAlertsTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "events.db"
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(SCHEMA)
            conn.executemany(
                """
                INSERT INTO alerts (
                    alert_id, alert_time, alert_type, severity,
                    agent_name, project_id, message, notified,
                    acknowledged, resolved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        "alert-newest",
                        "2026-04-15T10:05:00Z",
                        "agent_blocked",
                        "critical",
                        "atlas",
                        "proj-v3",
                        "Agent blocked on deploy approval",
                        None,
                        0,
                        None,
                    ),
                    (
                        "alert-older",
                        "2026-04-15T09:00:00Z",
                        "project_delay",
                        "warning",
                        "guard",
                        "proj-v2",
                        "Project exceeded stage SLA",
                        "slack",
                        1,
                        None,
                    ),
                ],
            )
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_alerts_api_respects_limit_and_order(self):
        class FakeHandler:
            def __init__(self, db_path):
                self.db_path = db_path
                self.payload = None

            def get_db(self):
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                return conn

            def json_response(self, data, status=200):
                self.payload = {"status": status, "data": data}

            _parse_limit = MonitorHandler._parse_limit

        handler = FakeHandler(str(self.db_path))
        MonitorHandler._api_alerts(handler, {"limit": ["1"]})

        alerts = handler.payload["data"]
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["alert_id"], "alert-newest")
        self.assertEqual(alerts[0]["severity"], "critical")

    def test_alerts_page_serves_live_dashboard_markup(self):
        page = Path("web/static/alerts.html").read_text(encoding="utf-8")
        self.assertIn("告警中心", page)
        self.assertIn("/api/alerts?limit=100", page)
        self.assertIn("alert-table-body", page)


if __name__ == "__main__":
    unittest.main()
