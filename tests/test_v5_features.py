"""
tests/test_v5_features.py

Unit tests for V5 new features:
  1. Alert rule engine  (collector/collector.py :: run_alert_checks)
  2. API enhancements   (api/api_server.py :: _api_alerts, _api_stats, _api_projects)
  3. Event classification (_classify_event milestone types)

All tests use an in-memory / temp-dir SQLite DB; no network, no disk side-effects.
"""

import json
import sqlite3
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collector.collector import init_db, run_alert_checks, event_id
import api.api_server as api_server
from api.api_server import MonitorHandler

CST = __import__('collector.collector', fromlist=['CST']).CST


# ── Minimal FakeHandler (mirrors test_api_server.py) ────────────────────────

class FakeHandler:
    def __init__(self, db_path):
        self.db_path = db_path
        self.payload = None
        self.status = None
        self.headers = []
        self.body = b''
        self.wfile = self

    def get_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def json_response(self, data, status=200):
        self.payload = data
        self.status = status

    def send_response(self, status):
        self.status = status

    def send_header(self, key, value):
        self.headers.append((key, value))

    def end_headers(self):
        pass

    def write(self, data):
        self.body += data

    def date_time_string(self, timestamp=None):
        return 'Mon, 21 Apr 2026 10:00:00 GMT'

    _parse_limit = MonitorHandler._parse_limit
    _group_projects = MonitorHandler._group_projects
    _stage_priority = MonitorHandler._stage_priority
    _load_project_records = MonitorHandler._load_project_records
    _api_alerts = MonitorHandler._api_alerts
    _api_projects = MonitorHandler._api_projects
    _api_agents = MonitorHandler._api_agents
    _api_stats = MonitorHandler._api_stats
    _classify_event = MonitorHandler._classify_event
    _event_title = MonitorHandler._event_title
    _event_detail = MonitorHandler._event_detail
    _extract_counterparty = MonitorHandler._extract_counterparty
    _normalize_agent_event = MonitorHandler._normalize_agent_event
    _agent_summary = MonitorHandler._agent_summary
    _build_heatmap = MonitorHandler._build_heatmap
    _range_start = MonitorHandler._range_start
    _parse_datetime = MonitorHandler._parse_datetime
    _parse_payload = MonitorHandler._parse_payload
    _trend = MonitorHandler._trend
    _artifact_stage_rank = MonitorHandler._artifact_stage_rank
    _group_artifacts = MonitorHandler._group_artifacts


# ── Helper: open an in-memory DB with full schema ────────────────────────────

def make_db():
    """Return (conn, tmp_path) for a fresh temp-file DB with row_factory set."""
    tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tmp.close()
    conn = init_db(tmp.name)
    conn.row_factory = sqlite3.Row
    return conn, tmp.name


def _dt_ago(**kwargs):
    """UTC ISO string for 'now minus kwargs'."""
    return (datetime.now(timezone.utc) - timedelta(**kwargs)).isoformat(timespec='seconds')


def _dt_cst_ago(**kwargs):
    """CST ISO string for 'now minus kwargs'."""
    return (datetime.now(CST) - timedelta(**kwargs)).isoformat(timespec='seconds')


# ════════════════════════════════════════════════════════════════════════════
# 1. Alert Rule Engine
# ════════════════════════════════════════════════════════════════════════════

class TestAlertRuleAgentStalled(unittest.TestCase):
    """Rule 1: agent_stalled — running agent idle > 30 min → warning."""

    def setUp(self):
        self.conn, self.db_path = make_db()

    def tearDown(self):
        self.conn.close()
        Path(self.db_path).unlink(missing_ok=True)

    def _insert_agent(self, name, status, last_action_time):
        self.conn.execute("""
            INSERT OR REPLACE INTO agg_agent_status
            (agent_name, status, last_action_time, updated_at)
            VALUES (?, ?, ?, ?)
        """, (name, status, last_action_time, _dt_cst_ago(minutes=1)))
        self.conn.commit()

    def test_stalled_agent_triggers_warning(self):
        """Agent running with last_action 45 min ago → alert inserted."""
        self._insert_agent('peter', 'running', _dt_cst_ago(minutes=45))
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT * FROM alerts WHERE alert_type='agent_stalled' AND agent_name='peter'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row['severity'], 'warning')

    def test_stalled_alert_message_contains_agent_name(self):
        self._insert_agent('guard', 'running', _dt_cst_ago(minutes=60))
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT message FROM alerts WHERE alert_type='agent_stalled' AND agent_name='guard'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertIn('guard', row[0])

    def test_recent_agent_does_not_trigger(self):
        """Agent last active 10 min ago — must NOT fire."""
        self._insert_agent('atlas', 'running', _dt_cst_ago(minutes=10))
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT * FROM alerts WHERE alert_type='agent_stalled' AND agent_name='atlas'"
        ).fetchone()
        self.assertIsNone(row)

    def test_idle_agent_does_not_trigger(self):
        """Non-running agent — must NOT fire even if action is old."""
        self._insert_agent('doraemon', 'idle', _dt_cst_ago(hours=2))
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT * FROM alerts WHERE alert_type='agent_stalled' AND agent_name='doraemon'"
        ).fetchone()
        self.assertIsNone(row)

    def test_duplicate_runs_do_not_duplicate_alerts(self):
        """Alert engine uses INSERT OR IGNORE — running twice must yield one row."""
        self._insert_agent('jarvis', 'running', _dt_cst_ago(minutes=90))
        run_alert_checks(self.conn)
        run_alert_checks(self.conn)
        count = self.conn.execute(
            "SELECT COUNT(*) FROM alerts WHERE alert_type='agent_stalled' AND agent_name='jarvis'"
        ).fetchone()[0]
        self.assertEqual(count, 1)


class TestAlertRuleProjectOvertime(unittest.TestCase):
    """Rules 2-4: project overtime at 12h/24h/48h thresholds."""

    def setUp(self):
        self.conn, self.db_path = make_db()

    def tearDown(self):
        self.conn.close()
        Path(self.db_path).unlink(missing_ok=True)

    def _insert_project(self, project_id, stage, stage_enter_hours_ago):
        self.conn.execute("""
            INSERT OR REPLACE INTO agg_project_flow
            (project_id, base_project, version, current_stage, stage_enter_time,
             block_reason, updated_at)
            VALUES (?, ?, ?, ?, ?, '', ?)
        """, (project_id, project_id, 'v1', stage,
              _dt_cst_ago(hours=stage_enter_hours_ago),
              _dt_cst_ago(hours=1)))
        self.conn.commit()

    def test_12h_overtime_triggers_warning(self):
        self._insert_project('proj-12h', 'developing', 13)
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT severity FROM alerts WHERE alert_type='project_overtime_12h' AND project_id='proj-12h'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 'warning')

    def test_24h_overtime_triggers_critical(self):
        self._insert_project('proj-24h', 'testing', 25)
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT severity FROM alerts WHERE alert_type='project_overtime_24h' AND project_id='proj-24h'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 'critical')

    def test_48h_overtime_triggers_critical(self):
        self._insert_project('proj-48h', 'qa', 50)
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT severity FROM alerts WHERE alert_type='project_overtime_48h' AND project_id='proj-48h'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 'critical')

    def test_48h_supersedes_lower_thresholds(self):
        """A 50h project should only get the 48h alert, NOT 12h or 24h."""
        self._insert_project('proj-super', 'developing', 50)
        run_alert_checks(self.conn)
        types = {row[0] for row in self.conn.execute(
            "SELECT alert_type FROM alerts WHERE project_id='proj-super'"
        ).fetchall()}
        self.assertIn('project_overtime_48h', types)
        self.assertNotIn('project_overtime_12h', types)
        self.assertNotIn('project_overtime_24h', types)

    def test_under_12h_does_not_trigger(self):
        self._insert_project('proj-fresh', 'developing', 5)
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT * FROM alerts WHERE project_id='proj-fresh'"
        ).fetchone()
        self.assertIsNone(row)

    def test_done_stage_excluded(self):
        """Projects in 'done' stage must never fire overtime alerts."""
        self._insert_project('proj-done', 'done', 72)
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT * FROM alerts WHERE project_id='proj-done'"
        ).fetchone()
        self.assertIsNone(row)

    def test_deployed_stage_excluded(self):
        self._insert_project('proj-deployed', 'deployed', 72)
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT * FROM alerts WHERE project_id='proj-deployed'"
        ).fetchone()
        self.assertIsNone(row)

    def test_archived_stage_excluded(self):
        self._insert_project('proj-archived', 'archived', 72)
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT * FROM alerts WHERE project_id='proj-archived'"
        ).fetchone()
        self.assertIsNone(row)

    def test_alert_message_includes_project_and_stage(self):
        self._insert_project('proj-msg', 'testing', 25)
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT message FROM alerts WHERE project_id='proj-msg'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertIn('proj-msg', row[0])
        self.assertIn('testing', row[0])


class TestAlertRuleConsecutiveStalled(unittest.TestCase):
    """Rule 5: consecutive_stalled — blocked project with no update > 1h → critical."""

    def setUp(self):
        self.conn, self.db_path = make_db()

    def tearDown(self):
        self.conn.close()
        Path(self.db_path).unlink(missing_ok=True)

    def _insert_blocked_project(self, project_id, updated_hours_ago, block_reason='待验收'):
        self.conn.execute("""
            INSERT OR REPLACE INTO agg_project_flow
            (project_id, base_project, version, current_stage, stage_enter_time,
             block_reason, updated_at)
            VALUES (?, ?, ?, 'testing', ?, ?, ?)
        """, (project_id, project_id, 'v1',
              _dt_cst_ago(hours=updated_hours_ago + 2),
              block_reason,
              _dt_cst_ago(hours=updated_hours_ago)))
        self.conn.commit()

    def test_stalled_blocked_project_triggers_critical(self):
        self._insert_blocked_project('proj-stall', 2)
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT severity FROM alerts WHERE alert_type='consecutive_stalled' AND project_id='proj-stall'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 'critical')

    def test_recently_updated_blocked_does_not_trigger(self):
        """Block reason set but updated < 1h ago — must NOT fire."""
        self._insert_blocked_project('proj-new-block', 0)
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT * FROM alerts WHERE alert_type='consecutive_stalled' AND project_id='proj-new-block'"
        ).fetchone()
        self.assertIsNone(row)

    def test_empty_block_reason_does_not_trigger(self):
        """No block reason — must NOT fire."""
        self.conn.execute("""
            INSERT OR REPLACE INTO agg_project_flow
            (project_id, base_project, version, current_stage, stage_enter_time,
             block_reason, updated_at)
            VALUES ('proj-clear', 'proj-clear', 'v1', 'testing', ?, '', ?)
        """, (_dt_cst_ago(hours=10), _dt_cst_ago(hours=5)))
        self.conn.commit()
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT * FROM alerts WHERE alert_type='consecutive_stalled' AND project_id='proj-clear'"
        ).fetchone()
        self.assertIsNone(row)

    def test_alert_message_includes_block_reason(self):
        self._insert_blocked_project('proj-reason', 2, block_reason='等待PM确认')
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT message FROM alerts WHERE alert_type='consecutive_stalled' AND project_id='proj-reason'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertIn('等待PM确认', row[0])


class TestAlertRuleCollectorState(unittest.TestCase):
    """Verify that run_alert_checks records last_alert_run in collector_state."""

    def setUp(self):
        self.conn, self.db_path = make_db()

    def tearDown(self):
        self.conn.close()
        Path(self.db_path).unlink(missing_ok=True)

    def test_last_alert_run_recorded(self):
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT value FROM collector_state WHERE key='last_alert_run'"
        ).fetchone()
        self.assertIsNotNone(row)
        # Value should parse as an ISO datetime
        try:
            datetime.fromisoformat(row[0])
        except ValueError:
            self.fail(f"last_alert_run is not a valid ISO datetime: {row[0]}")


# ════════════════════════════════════════════════════════════════════════════
# 2. API — /api/alerts
# ════════════════════════════════════════════════════════════════════════════

class TestApiAlerts(unittest.TestCase):
    """Tests for _api_alerts: pagination, ordering, filtering."""

    def setUp(self):
        self.conn, self.db_path = make_db()
        self._seed_alerts()

    def tearDown(self):
        self.conn.close()
        Path(self.db_path).unlink(missing_ok=True)

    def _seed_alerts(self):
        alerts = [
            ('a-001', '2026-04-20T10:00:00Z', 'agent_stalled',        'warning',  'peter',  None,       'peter stalled'),
            ('a-002', '2026-04-20T11:00:00Z', 'project_overtime_12h', 'warning',  None,     'proj-v3',  'proj overtime 12h'),
            ('a-003', '2026-04-20T12:00:00Z', 'project_overtime_24h', 'critical', None,     'proj-v4',  'proj overtime 24h'),
            ('a-004', '2026-04-20T13:00:00Z', 'consecutive_stalled',  'critical', None,     'proj-v5',  'proj stalled'),
        ]
        self.conn.executemany("""
            INSERT INTO alerts (alert_id, alert_time, alert_type, severity, agent_name, project_id, message, acknowledged)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
        """, alerts)
        self.conn.commit()

    def _handler(self):
        return FakeHandler(self.db_path)

    def test_default_returns_all_alerts_newest_first(self):
        h = self._handler()
        h._api_alerts({})
        self.assertEqual(h.status, 200)
        times = [row['alert_time'] for row in h.payload]
        self.assertEqual(times, sorted(times, reverse=True))

    def test_limit_restricts_result_count(self):
        h = self._handler()
        h._api_alerts({'limit': ['2']})
        self.assertEqual(len(h.payload), 2)

    def test_limit_1_returns_newest(self):
        h = self._handler()
        h._api_alerts({'limit': ['1']})
        self.assertEqual(h.payload[0]['alert_id'], 'a-004')

    def test_offset_skips_rows(self):
        h = self._handler()
        h._api_alerts({'limit': ['2'], 'offset': ['2']})
        ids = {row['alert_id'] for row in h.payload}
        # Oldest two (a-001, a-002)
        self.assertIn('a-001', ids)
        self.assertIn('a-002', ids)

    def test_invalid_limit_falls_back_to_default(self):
        h = self._handler()
        h._api_alerts({'limit': ['bad']})
        self.assertEqual(h.status, 200)
        self.assertIsInstance(h.payload, list)

    def test_negative_offset_treated_as_zero(self):
        h = self._handler()
        h._api_alerts({'offset': ['-5']})
        self.assertEqual(h.status, 200)
        self.assertIsInstance(h.payload, list)

    def test_response_includes_expected_fields(self):
        h = self._handler()
        h._api_alerts({'limit': ['1']})
        row = h.payload[0]
        for field in ('alert_id', 'alert_time', 'alert_type', 'severity', 'message'):
            self.assertIn(field, row)

    def test_limit_exceeding_max_capped(self):
        """parse_limit caps at maximum=200 for alerts endpoint."""
        h = self._handler()
        h._api_alerts({'limit': ['9999']})
        # Should not raise; all 4 seeded rows returned
        self.assertLessEqual(len(h.payload), 200)


# ════════════════════════════════════════════════════════════════════════════
# 3. API — /api/stats data freshness fields
# ════════════════════════════════════════════════════════════════════════════

class TestApiStatsFreshness(unittest.TestCase):
    """Verify _api_stats returns last_collector_run and collector_status."""

    def setUp(self):
        self.conn, self.db_path = make_db()

    def tearDown(self):
        self.conn.close()
        Path(self.db_path).unlink(missing_ok=True)

    def _handler(self):
        return FakeHandler(self.db_path)

    def test_stats_returns_200(self):
        h = self._handler()
        h._api_stats({})
        self.assertEqual(h.status, 200)

    def test_no_collector_run_unknown_status(self):
        """With no collector_state rows, collector_status should be 'unknown'."""
        h = self._handler()
        h._api_stats({})
        self.assertEqual(h.payload['collector_status'], 'unknown')
        self.assertIsNone(h.payload['last_collector_run'])

    def test_recent_run_ok_status(self):
        """last_run timestamp < 300s old → collector_status='ok'."""
        ts = str(time.time() - 60)  # 60 seconds ago
        self.conn.execute(
            "INSERT OR REPLACE INTO collector_state (key, value) VALUES ('last_run', ?)", (ts,)
        )
        self.conn.commit()
        h = self._handler()
        h._api_stats({})
        self.assertEqual(h.payload['collector_status'], 'ok')
        self.assertIsNotNone(h.payload['last_collector_run'])

    def test_stale_run_stale_status(self):
        """last_run timestamp > 300s old → collector_status='stale'."""
        ts = str(time.time() - 400)  # 400 seconds ago
        self.conn.execute(
            "INSERT OR REPLACE INTO collector_state (key, value) VALUES ('last_run', ?)", (ts,)
        )
        self.conn.commit()
        h = self._handler()
        h._api_stats({})
        self.assertEqual(h.payload['collector_status'], 'stale')

    def test_last_collector_run_is_iso_string(self):
        ts = str(time.time() - 30)
        self.conn.execute(
            "INSERT OR REPLACE INTO collector_state (key, value) VALUES ('last_run', ?)", (ts,)
        )
        self.conn.commit()
        h = self._handler()
        h._api_stats({})
        run_value = h.payload['last_collector_run']
        try:
            datetime.fromisoformat(run_value.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            self.fail(f"last_collector_run is not ISO: {run_value!r}")

    def test_stats_structure_has_agent_and_project_keys(self):
        h = self._handler()
        h._api_stats({})
        self.assertIn('agents', h.payload)
        self.assertIn('projects', h.payload)
        self.assertIn('events_24h', h.payload)


# ════════════════════════════════════════════════════════════════════════════
# 4. API — /api/projects sorting logic
# ════════════════════════════════════════════════════════════════════════════

class TestApiProjectsSorting(unittest.TestCase):
    """_api_projects grouped mode: active > blocked > done ordering via _stage_priority."""

    def setUp(self):
        self.conn, self.db_path = make_db()
        self._seed_projects()

    def tearDown(self):
        self.conn.close()
        Path(self.db_path).unlink(missing_ok=True)

    def _seed_projects(self):
        projects = [
            # (project_id, base, version, project_name, lifecycle, stage, block_reason, updated_at)
            ('proj-done-v1',    'proj-done',    'v1', 'proj-done',    'completed', 'done',       '',       '2026-04-19T10:00:00Z'),
            ('proj-active-v1',  'proj-active',  'v1', 'proj-active',  'active',    'developing', '',       '2026-04-20T10:00:00Z'),
            ('proj-blocked-v1', 'proj-blocked', 'v1', 'proj-blocked', 'active',    'testing',    '待验收', '2026-04-20T09:00:00Z'),
            ('proj-testing-v1', 'proj-testing', 'v1', 'proj-testing', 'active',    'testing',    '',       '2026-04-20T08:00:00Z'),
        ]
        self.conn.executemany("""
            INSERT INTO agg_project_flow
            (project_id, base_project, version, project_name, lifecycle,
             current_stage, stage_owner, stage_enter_time, block_reason, updated_at,
             status_file, artifact_root)
            VALUES (?, ?, ?, ?, ?, ?, 'peter', '2026-04-18T00:00:00Z', ?, ?, '', '')
        """, projects)
        self.conn.commit()

    def _handler(self):
        return FakeHandler(self.db_path)

    def test_stage_priority_developing_beats_done(self):
        h = self._handler()
        priority_dev = h._stage_priority('developing')
        priority_done = h._stage_priority('done')
        self.assertGreater(priority_dev, priority_done)

    def test_stage_priority_testing_beats_done(self):
        h = self._handler()
        self.assertGreater(h._stage_priority('testing'), h._stage_priority('done'))

    def test_stage_priority_developing_beats_testing(self):
        h = self._handler()
        self.assertGreater(h._stage_priority('developing'), h._stage_priority('testing'))

    def test_grouped_order_active_first(self):
        h = self._handler()
        h._api_projects({'grouped': ['1']})
        stages = [grp['versions'][0]['current_stage'] for grp in h.payload]
        # 'done' should NOT be first
        self.assertNotEqual(stages[0], 'done')

    def test_flat_projects_returns_list(self):
        h = self._handler()
        h._api_projects({})
        self.assertEqual(h.status, 200)
        self.assertIsInstance(h.payload, list)
        self.assertEqual(len(h.payload), 4)

    def test_flat_blocked_filter_returns_only_blocked(self):
        h = self._handler()
        h._api_projects({'filter': ['blocked']})
        self.assertEqual(h.status, 200)
        for p in h.payload:
            self.assertTrue(p.get('block_reason'), f"Expected non-empty block_reason but got: {p}")

    def test_grouped_versions_count_per_base(self):
        h = self._handler()
        h._api_projects({'grouped': ['1']})
        for group in h.payload:
            # Each test project has exactly 1 version
            self.assertEqual(len(group['versions']), 1)

    def test_active_version_set_in_grouped(self):
        h = self._handler()
        h._api_projects({'grouped': ['1']})
        for group in h.payload:
            self.assertIn('active_version', group)
            self.assertIsNotNone(group['active_version'])


# ════════════════════════════════════════════════════════════════════════════
# 5. Event Classification — _classify_event milestone types
# ════════════════════════════════════════════════════════════════════════════

class TestClassifyEvent(unittest.TestCase):
    """_classify_event must correctly classify milestone-type payloads."""

    def setUp(self):
        self.h = FakeHandler(':memory:')  # db not used in these tests

    def _event(self, summary='', payload=None):
        return {
            'summary': summary,
            'payload_json': json.dumps(payload or {}),
            'severity': 'info',
        }

    # ── a2a ──────────────────────────────────────────────────────────────

    def test_a2a_send_by_sessions_send_in_summary(self):
        ev = self._event(summary='sessions_send guard: please review')
        self.assertEqual(self.h._classify_event(ev), 'a2a')

    def test_a2a_send_by_payload_key(self):
        ev = self._event(payload={'tool': 'sessions_send', 'target': 'guard'})
        self.assertEqual(self.h._classify_event(ev), 'a2a')

    def test_a2a_receive_by_a2a_keyword(self):
        ev = self._event(summary='a2a_receive from peter')
        self.assertEqual(self.h._classify_event(ev), 'a2a')

    def test_agent_to_agent_keyword(self):
        ev = self._event(summary='agent-to-agent handoff')
        self.assertEqual(self.h._classify_event(ev), 'a2a')

    # ── subagent ─────────────────────────────────────────────────────────

    def test_subagent_spawn_by_summary(self):
        ev = self._event(summary='spawn subagent frontend-dev')
        self.assertEqual(self.h._classify_event(ev), 'subagent')

    def test_subagent_spawn_by_payload_tool(self):
        ev = self._event(payload={'tool': 'sessions_spawn', 'label': 'qa-agent'})
        self.assertEqual(self.h._classify_event(ev), 'subagent')

    def test_subagent_return_by_summary(self):
        ev = self._event(summary='subagent_return completed')
        self.assertEqual(self.h._classify_event(ev), 'subagent')

    def test_session_colon_prefix(self):
        ev = self._event(summary='session: started new task')
        self.assertEqual(self.h._classify_event(ev), 'subagent')

    # ── error ─────────────────────────────────────────────────────────────

    def test_error_keyword_in_summary(self):
        ev = self._event(summary='tool error: preview failed')
        self.assertEqual(self.h._classify_event(ev), 'error')

    def test_severity_error_classifies_as_error(self):
        ev = {'summary': '', 'payload_json': '{}', 'severity': 'error'}
        self.assertEqual(self.h._classify_event(ev), 'error')

    def test_warning_severity_does_not_classify_as_error(self):
        """'warning' severity is not an error classification."""
        ev = {'summary': 'slight warning', 'payload_json': '{}', 'severity': 'warning'}
        # Should not be 'error'; 'tool' or 'timeline' are both acceptable
        result = self.h._classify_event(ev)
        self.assertNotEqual(result, 'error')

    # ── tool ──────────────────────────────────────────────────────────────

    def test_tool_keyword_in_summary(self):
        ev = self._event(summary='tool call: Read file')
        self.assertEqual(self.h._classify_event(ev), 'tool')

    def test_read_paren_in_summary(self):
        ev = self._event(summary='read( /some/file.py )')
        self.assertEqual(self.h._classify_event(ev), 'tool')

    def test_exec_in_summary(self):
        ev = self._event(summary='exec command: pytest')
        self.assertEqual(self.h._classify_event(ev), 'tool')

    # ── artifact / milestone passthrough ─────────────────────────────────

    def test_artifact_commit_in_summary_not_a2a(self):
        """artifact_commit is not an a2a/subagent — should be 'timeline' or 'tool'."""
        ev = self._event(summary='artifact_commit requirements/REQUIREMENTS.md')
        result = self.h._classify_event(ev)
        self.assertNotIn(result, ('a2a', 'subagent'))

    def test_stage_enter_in_summary_not_a2a(self):
        ev = self._event(summary='stage_enter developing')
        result = self.h._classify_event(ev)
        self.assertNotIn(result, ('a2a', 'subagent'))

    def test_stage_exit_in_summary_not_a2a(self):
        ev = self._event(summary='stage_exit testing')
        result = self.h._classify_event(ev)
        self.assertNotIn(result, ('a2a', 'subagent'))

    # ── fallthrough ───────────────────────────────────────────────────────

    def test_generic_event_returns_timeline(self):
        ev = self._event(summary='Implemented dashboard cards')
        self.assertEqual(self.h._classify_event(ev), 'timeline')

    def test_empty_event_returns_timeline(self):
        ev = self._event()
        self.assertEqual(self.h._classify_event(ev), 'timeline')

    def test_a2a_priority_over_subagent(self):
        """sessions_send beats subagent keyword when both present."""
        ev = self._event(summary='sessions_send guard: spawned subagent helper')
        self.assertEqual(self.h._classify_event(ev), 'a2a')


# ════════════════════════════════════════════════════════════════════════════
# 6. Alert severity correctness (integration: insert then query)
# ════════════════════════════════════════════════════════════════════════════

class TestAlertSeverityLevels(unittest.TestCase):
    """Ensure the correct severity level is used for each rule type."""

    def setUp(self):
        self.conn, self.db_path = make_db()

    def tearDown(self):
        self.conn.close()
        Path(self.db_path).unlink(missing_ok=True)

    def _seed_agent(self, name, minutes_stalled):
        self.conn.execute("""
            INSERT OR REPLACE INTO agg_agent_status
            (agent_name, status, last_action_time, updated_at)
            VALUES (?, 'running', ?, ?)
        """, (name, _dt_cst_ago(minutes=minutes_stalled), _dt_cst_ago(minutes=1)))
        self.conn.commit()

    def _seed_project(self, pid, stage, hours_ago, block=''):
        self.conn.execute("""
            INSERT OR REPLACE INTO agg_project_flow
            (project_id, base_project, version, current_stage, stage_enter_time,
             block_reason, updated_at)
            VALUES (?, ?, 'v1', ?, ?, ?, ?)
        """, (pid, pid, stage,
              _dt_cst_ago(hours=hours_ago),
              block,
              _dt_cst_ago(hours=max(hours_ago - 1, 2))))
        self.conn.commit()

    def test_agent_stalled_severity_is_warning(self):
        self._seed_agent('sev-agent', 45)
        run_alert_checks(self.conn)
        sev = self.conn.execute(
            "SELECT severity FROM alerts WHERE alert_type='agent_stalled'"
        ).fetchone()[0]
        self.assertEqual(sev, 'warning')

    def test_overtime_12h_severity_is_warning(self):
        self._seed_project('sev-12h', 'developing', 13)
        run_alert_checks(self.conn)
        sev = self.conn.execute(
            "SELECT severity FROM alerts WHERE alert_type='project_overtime_12h'"
        ).fetchone()[0]
        self.assertEqual(sev, 'warning')

    def test_overtime_24h_severity_is_critical(self):
        self._seed_project('sev-24h', 'testing', 25)
        run_alert_checks(self.conn)
        sev = self.conn.execute(
            "SELECT severity FROM alerts WHERE alert_type='project_overtime_24h'"
        ).fetchone()[0]
        self.assertEqual(sev, 'critical')

    def test_overtime_48h_severity_is_critical(self):
        self._seed_project('sev-48h', 'qa', 50)
        run_alert_checks(self.conn)
        sev = self.conn.execute(
            "SELECT severity FROM alerts WHERE alert_type='project_overtime_48h'"
        ).fetchone()[0]
        self.assertEqual(sev, 'critical')

    def test_consecutive_stalled_severity_is_critical(self):
        self._seed_project('sev-stall', 'testing', 10, block='等待PM')
        run_alert_checks(self.conn)
        sev = self.conn.execute(
            "SELECT severity FROM alerts WHERE alert_type='consecutive_stalled'"
        ).fetchone()[0]
        self.assertEqual(sev, 'critical')


# ════════════════════════════════════════════════════════════════════════════
# 7. Alert Rule — llm_consecutive_errors (Fix 2)
# ════════════════════════════════════════════════════════════════════════════

class TestAlertRuleLlmConsecutiveErrors(unittest.TestCase):
    """Rule 6: 3+ consecutive LLM call failures per agent → warning."""

    def setUp(self):
        self.conn, self.db_path = make_db()

    def tearDown(self):
        self.conn.close()
        Path(self.db_path).unlink(missing_ok=True)

    def _insert_event(self, agent_name, severity, summary, minutes_ago):
        eid = event_id(agent_name, severity, summary, str(minutes_ago))
        self.conn.execute("""
            INSERT OR IGNORE INTO event_log
            (event_id, event_time, source_type, agent_name, event_category, event_type, severity, summary)
            VALUES (?, ?, 'session', ?, 'llm', 'llm_call', ?, ?)
        """, (eid, _dt_ago(minutes=minutes_ago), agent_name, severity, summary))
        self.conn.commit()

    def test_three_consecutive_errors_triggers_warning(self):
        """3 most recent events all have severity=error → alert inserted."""
        for i, ago in enumerate([1, 2, 3]):
            self._insert_event('bot-err', 'error', f'LLM call error #{i}', ago)
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT severity FROM alerts WHERE alert_type='llm_consecutive_errors' AND agent_name='bot-err'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 'warning')

    def test_error_keyword_in_summary_triggers_warning(self):
        """Events with 'error' in summary (not severity field) also count."""
        for ago in [1, 2, 3]:
            self._insert_event('bot-summary', 'info', 'API error occurred', ago)
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT * FROM alerts WHERE alert_type='llm_consecutive_errors' AND agent_name='bot-summary'"
        ).fetchone()
        self.assertIsNotNone(row)

    def test_two_consecutive_errors_does_not_trigger(self):
        """Only 2 consecutive errors → must NOT fire."""
        self._insert_event('bot-two', 'error', 'error call', 1)
        self._insert_event('bot-two', 'error', 'error call', 2)
        self._insert_event('bot-two', 'info', 'ok call', 3)
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT * FROM alerts WHERE alert_type='llm_consecutive_errors' AND agent_name='bot-two'"
        ).fetchone()
        self.assertIsNone(row)

    def test_successful_call_breaks_streak(self):
        """Error, ok, error, error sequence → streak is only 2, no alert."""
        self._insert_event('bot-streak', 'error', 'error', 1)
        self._insert_event('bot-streak', 'error', 'error', 2)
        self._insert_event('bot-streak', 'info', 'success', 3)
        self._insert_event('bot-streak', 'error', 'error', 4)
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT * FROM alerts WHERE alert_type='llm_consecutive_errors' AND agent_name='bot-streak'"
        ).fetchone()
        self.assertIsNone(row)

    def test_alert_message_contains_agent_name(self):
        for ago in [1, 2, 3]:
            self._insert_event('bot-msg', 'error', 'error msg', ago)
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT message FROM alerts WHERE alert_type='llm_consecutive_errors' AND agent_name='bot-msg'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertIn('bot-msg', row[0])


# ════════════════════════════════════════════════════════════════════════════
# 8. Alert Rule — token_spike (Fix 3)
# ════════════════════════════════════════════════════════════════════════════

class TestAlertRuleTokenSpike(unittest.TestCase):
    """Rule 7: agent token usage in last hour exceeds 3x daily average → warning."""

    def setUp(self):
        self.conn, self.db_path = make_db()

    def tearDown(self):
        self.conn.close()
        Path(self.db_path).unlink(missing_ok=True)

    def _insert_token_event(self, agent_name, input_tokens, output_tokens, hours_ago):
        import hashlib
        raw = f"{agent_name}|{hours_ago}|{input_tokens}"
        eid = hashlib.sha256(raw.encode()).hexdigest()[:16]
        self.conn.execute("""
            INSERT OR IGNORE INTO event_log
            (event_id, event_time, source_type, agent_name, event_category, event_type,
             severity, input_tokens, output_tokens, summary)
            VALUES (?, ?, 'session', ?, 'llm', 'llm_call', 'info', ?, ?, 'token event')
        """, (eid, _dt_ago(hours=hours_ago), agent_name, input_tokens, output_tokens))
        self.conn.commit()

    def test_spike_triggers_warning(self):
        """Daily avg ~1000 tokens, recent burst = 5000 → alert fires."""
        # Historical: 1000 tokens each over 3 past days (well outside 1-hour window)
        self._insert_token_event('tok-agent', 500, 500, 48)
        self._insert_token_event('tok-agent', 500, 500, 72)
        self._insert_token_event('tok-agent', 500, 500, 96)
        # Recent spike: 5000 tokens within last hour
        self._insert_token_event('tok-agent', 3000, 2000, 0)
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT severity FROM alerts WHERE alert_type='token_spike' AND agent_name='tok-agent'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 'warning')

    def test_normal_usage_does_not_trigger(self):
        """Recent tokens within 3x daily average → no alert."""
        # Historical: 5000 tokens each over 2 past days
        self._insert_token_event('tok-normal', 2500, 2500, 48)
        self._insert_token_event('tok-normal', 2500, 2500, 72)
        # Recent: 3000 tokens (well under 3x of 5000 daily avg = 15000)
        self._insert_token_event('tok-normal', 1500, 1500, 0)
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT * FROM alerts WHERE alert_type='token_spike' AND agent_name='tok-normal'"
        ).fetchone()
        self.assertIsNone(row)

    def test_single_day_history_does_not_trigger(self):
        """Only 1 day of history (active_days < 2) → rule skipped, no alert."""
        self._insert_token_event('tok-one-day', 100, 100, 12)
        self._insert_token_event('tok-one-day', 5000, 5000, 0)
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT * FROM alerts WHERE alert_type='token_spike' AND agent_name='tok-one-day'"
        ).fetchone()
        self.assertIsNone(row)

    def test_alert_message_includes_agent_name(self):
        self._insert_token_event('tok-msgtest', 500, 500, 48)
        self._insert_token_event('tok-msgtest', 500, 500, 72)
        self._insert_token_event('tok-msgtest', 5000, 5000, 0)
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT message FROM alerts WHERE alert_type='token_spike' AND agent_name='tok-msgtest'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertIn('tok-msgtest', row[0])


# ════════════════════════════════════════════════════════════════════════════
# 9. Alert Rule — subagent_abnormal_exit (Fix 4)
# ════════════════════════════════════════════════════════════════════════════

class TestAlertRuleSubagentAbnormalExit(unittest.TestCase):
    """Rule 8: sub-agent starts then exits abnormally → warning."""

    def setUp(self):
        self.conn, self.db_path = make_db()

    def tearDown(self):
        self.conn.close()
        Path(self.db_path).unlink(missing_ok=True)

    def _insert_event(self, agent_name, severity, summary, event_type='llm_call', hours_ago=0):
        import hashlib
        raw = f"{agent_name}|{summary}|{hours_ago}"
        eid = hashlib.sha256(raw.encode()).hexdigest()[:16]
        self.conn.execute("""
            INSERT OR IGNORE INTO event_log
            (event_id, event_time, source_type, agent_name, event_category, event_type,
             severity, summary)
            VALUES (?, ?, 'session', ?, 'agent', ?, ?, ?)
        """, (eid, _dt_ago(hours=hours_ago), agent_name, event_type, severity, summary))
        self.conn.commit()

    def test_subagent_error_in_summary_triggers_warning(self):
        """Event with 'subagent error' in summary → alert."""
        self._insert_event('parent-agent', 'info', 'subagent error: frontend-dev crashed')
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT severity FROM alerts WHERE alert_type='subagent_abnormal_exit' AND agent_name='parent-agent'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 'warning')

    def test_subagent_abort_triggers_warning(self):
        """Event with 'subagent abort' in summary → alert."""
        self._insert_event('parent-b', 'info', 'subagent qa-agent abort: timeout')
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT severity FROM alerts WHERE alert_type='subagent_abnormal_exit' AND agent_name='parent-b'"
        ).fetchone()
        self.assertIsNotNone(row)

    def test_spawn_error_triggers_warning(self):
        """Event with 'spawn' in summary AND severity=error → alert."""
        self._insert_event('parent-c', 'error', 'spawn subagent failed to start')
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT severity FROM alerts WHERE alert_type='subagent_abnormal_exit' AND agent_name='parent-c'"
        ).fetchone()
        self.assertIsNotNone(row)

    def test_subagent_exit_type_with_error_severity_triggers(self):
        """event_type=subagent_exit AND severity=error → alert."""
        self._insert_event('parent-d', 'error', 'subagent completed', event_type='subagent_exit')
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT severity FROM alerts WHERE alert_type='subagent_abnormal_exit' AND agent_name='parent-d'"
        ).fetchone()
        self.assertIsNotNone(row)

    def test_normal_subagent_completion_does_not_trigger(self):
        """Normal subagent return event (no error/fail/abort) → no alert."""
        self._insert_event('parent-ok', 'info', 'subagent frontend-dev completed successfully')
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT * FROM alerts WHERE alert_type='subagent_abnormal_exit' AND agent_name='parent-ok'"
        ).fetchone()
        self.assertIsNone(row)

    def test_old_event_outside_24h_does_not_trigger(self):
        """Subagent error event older than 24h → no alert."""
        self._insert_event('parent-old', 'info', 'subagent error: old crash', hours_ago=25)
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT * FROM alerts WHERE alert_type='subagent_abnormal_exit' AND agent_name='parent-old'"
        ).fetchone()
        self.assertIsNone(row)

    def test_alert_message_contains_agent_name(self):
        self._insert_event('parent-msg', 'info', 'subagent fail: backend exited')
        run_alert_checks(self.conn)
        row = self.conn.execute(
            "SELECT message FROM alerts WHERE alert_type='subagent_abnormal_exit' AND agent_name='parent-msg'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertIn('parent-msg', row[0])


if __name__ == '__main__':
    unittest.main()
