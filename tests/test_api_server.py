import sqlite3
import tempfile
import unittest
from pathlib import Path

import api.api_server as api_server
from api.api_server import MonitorHandler
from collector.collector import init_db, scan_status_json


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
        return 'Fri, 17 Apr 2026 10:00:00 GMT'

    _parse_limit = MonitorHandler._parse_limit
    _group_projects = MonitorHandler._group_projects
    _stage_priority = MonitorHandler._stage_priority
    _load_project_records = MonitorHandler._load_project_records
    _api_alerts = MonitorHandler._api_alerts
    _api_projects = MonitorHandler._api_projects
    _api_artifacts = MonitorHandler._api_artifacts
    _api_artifact = MonitorHandler._api_artifact
    _preview_type = MonitorHandler._preview_type
    _content_type = MonitorHandler._content_type
    _is_safe_artifact_path = MonitorHandler._is_safe_artifact_path


class APIServerBackendTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.projects_home = self.root / 'projects'
        self.projects_home.mkdir()
        self.db_path = self.root / 'events.db'
        init_db(self.db_path)
        self._seed_projects()
        self._seed_alerts()
        self.old_projects_home = api_server.PROJECTS_HOME
        api_server.PROJECTS_HOME = self.projects_home

    def tearDown(self):
        api_server.PROJECTS_HOME = self.old_projects_home
        self.temp_dir.cleanup()

    def _seed_projects(self):
        vb_v16 = self.projects_home / 'voice-bridge' / 'monitor' / 'v1.6'
        vb_v17 = self.projects_home / 'voice-bridge' / 'monitor' / 'v1.7'
        obs_v3 = self.projects_home / 'ai-team-observability' / 'monitor' / 'v3'
        for path in [vb_v16 / 'qa', vb_v17 / 'deploy', obs_v3 / 'requirements']:
            path.mkdir(parents=True, exist_ok=True)

        (vb_v16 / 'qa' / 'report.md').write_text('# report v1.6\n', encoding='utf-8')
        (vb_v17 / 'deploy' / 'demo.mp4').write_bytes(b'mp4-bytes')
        (obs_v3 / 'requirements' / 'REQUIREMENTS.md').write_text('# requirements\n', encoding='utf-8')

        (vb_v16 / 'status.json').write_text('''{
          "project_id": "voice-bridge-v1.6",
          "lifecycle": "completed",
          "artifacts": {"test_report": {"path": "qa/report.md"}},
          "workflow": {"current_stage": "done", "stage_owner": "doraemon", "stage_entered_at": "2026-04-16T10:00:00+08:00"},
          "runtime": {"current_blockers": [], "latest_artifact_update": "2026-04-16T10:00:00+08:00"},
          "official": {"updated_at": "2026-04-16T10:00:00+08:00"}
        }''', encoding='utf-8')

        (vb_v17 / 'status.json').write_text('''{
          "project_id": "voice-bridge-v1.7",
          "lifecycle": "active",
          "artifacts": {"deploy_report": {"path": "deploy/demo.mp4"}},
          "workflow": {"current_stage": "testing", "stage_owner": "guard", "stage_entered_at": "2026-04-17T09:00:00+08:00"},
          "runtime": {"current_blockers": ["待验收"], "latest_artifact_update": "2026-04-17T09:00:00+08:00"},
          "official": {"updated_at": "2026-04-17T09:00:00+08:00"}
        }''', encoding='utf-8')

        (obs_v3 / 'status.json').write_text('''{
          "project": "ai-team-observability",
          "artifacts_base_path": "monitor/v3/",
          "workflow": {"current_stage": "developing", "stage_owner": "peter", "stage_entered_at": "2026-04-17T08:05:00+08:00"},
          "runtime": {"current_blockers": [], "latest_artifact_update": "2026-04-17T09:53:00+08:00"},
          "official": {"updated_at": "2026-04-17T09:53:00+08:00"}
        }''', encoding='utf-8')

        from collector import collector as collector_module
        old_projects_home = collector_module.PROJECTS_HOME
        collector_module.PROJECTS_HOME = self.projects_home
        try:
            conn = sqlite3.connect(self.db_path)
            scan_status_json(conn)
            conn.close()
        finally:
            collector_module.PROJECTS_HOME = old_projects_home

    def _seed_alerts(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """INSERT INTO alerts (alert_id, alert_time, alert_type, severity, agent_name, project_id, message, notified, acknowledged, resolved_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ('alert-newest', '2026-04-15T10:05:00Z', 'agent_blocked', 'critical', 'atlas', 'proj-v3', 'blocked', None, 0, None),
        )
        conn.commit()
        conn.close()

    def test_alerts_api_respects_limit_and_order(self):
        handler = FakeHandler(str(self.db_path))
        handler._api_alerts({'limit': ['1']})
        self.assertEqual(handler.status, 200)
        self.assertEqual(len(handler.payload), 1)
        self.assertEqual(handler.payload[0]['alert_id'], 'alert-newest')

    def test_projects_api_supports_grouped_versions(self):
        handler = FakeHandler(str(self.db_path))
        handler._api_projects({'grouped': ['1']})
        grouped = handler.payload
        voice_bridge = next(group for group in grouped if group['base_project'] == 'voice-bridge')
        self.assertEqual(len(voice_bridge['versions']), 2)
        self.assertEqual(voice_bridge['active_version'], 'voice-bridge-v1.7')
        self.assertEqual(voice_bridge['versions'][0]['current_stage'], 'testing')

    def test_projects_api_flat_records_include_version_metadata(self):
        handler = FakeHandler(str(self.db_path))
        handler._api_projects({})
        obs = next(project for project in handler.payload if project['base_project'] == 'ai-team-observability')
        self.assertEqual(obs['project_id'], 'ai-team-observability-v3')
        self.assertEqual(obs['version'], 'v3')
        self.assertEqual(obs['current_stage'], 'developing')

    def test_artifacts_api_indexes_previewable_files(self):
        handler = FakeHandler(str(self.db_path))
        handler._api_artifacts({'project_id': ['ai-team-observability-v3']})
        item = next(artifact for artifact in handler.payload if artifact['name'] == 'REQUIREMENTS.md')
        self.assertEqual(item['preview_type'], 'markdown')
        self.assertEqual(item['stage'], 'requirements')

    def test_artifact_api_streams_file_inline(self):
        file_path = self.projects_home / 'ai-team-observability' / 'monitor' / 'v3' / 'requirements' / 'REQUIREMENTS.md'
        handler = FakeHandler(str(self.db_path))
        handler._api_artifact({'path': [str(file_path)]})
        self.assertEqual(handler.status, 200)
        self.assertIn(('Content-Type', 'text/markdown; charset=utf-8'), handler.headers)
        self.assertTrue(handler.body.startswith(b'# requirements'))

    def test_alerts_page_serves_live_dashboard_markup(self):
        page = Path('web/static/alerts.html').read_text(encoding='utf-8')
        self.assertIn('告警中心', page)
        self.assertIn('/api/alerts?limit=100', page)
        self.assertIn('alert-table-body', page)


if __name__ == '__main__':
    unittest.main()
