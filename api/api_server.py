#!/usr/bin/env python3
"""
AI Team Observability - API Server

Serves REST API + static HTML pages for the monitoring dashboard.
Reads from SQLite database populated by collector.py.

Usage: python3 api_server.py [--db PATH] [--port PORT]
"""

import json
import mimetypes
import os
import sqlite3
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
from pathlib import Path

DB_PATH = os.environ.get('DB_PATH', 'data/events.db')
PROJECTS_HOME = Path(os.environ.get('PROJECTS_HOME', os.path.expanduser('~/projects')))
STATIC_DIR = Path(__file__).parent.parent / 'web' / 'static'
TEXT_EXTENSIONS = {'.md', '.markdown', '.txt', '.log', '.json', '.py', '.js', '.ts', '.tsx', '.jsx', '.html', '.css', '.yml', '.yaml'}
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'}
VIDEO_EXTENSIONS = {'.mp4', '.webm', '.mov', '.m4v'}


class MonitorHandler(BaseHTTPRequestHandler):
    """HTTP handler for monitoring dashboard."""

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == '/':
            self._serve_page('index.html')
        elif path == '/team/agents':
            self._serve_page('agents.html')
        elif path == '/team/projects':
            self._serve_page('projects.html')
        elif path == '/team/alerts':
            self._serve_page('alerts.html')
        elif path == '/api/agents':
            self._api_agents(params)
        elif path == '/api/projects':
            self._api_projects(params)
        elif path == '/api/artifacts':
            self._api_artifacts(params)
        elif path == '/api/artifact':
            self._api_artifact(params)
        elif path == '/api/events':
            self._api_events(params)
        elif path == '/api/stats':
            self._api_stats(params)
        elif path == '/api/alerts':
            self._api_alerts(params)
        elif path.startswith('/static/'):
            self._serve_static(path[1:])
        else:
            self.send_error(404)

    def get_db(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def json_response(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, default=str).encode())

    def _serve_page(self, filename):
        filepath = STATIC_DIR / filename
        if filepath.exists():
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(filepath.read_bytes())
        else:
            self.send_error(404, f'Page {filename} not found')

    def _serve_static(self, filepath):
        full = STATIC_DIR.parent / filepath
        if full.exists():
            self.send_response(200)
            ext = full.suffix
            ct = {'.css': 'text/css', '.js': 'application/javascript', '.png': 'image/png'}.get(ext, 'application/octet-stream')
            self.send_header('Content-Type', ct)
            self.end_headers()
            self.wfile.write(full.read_bytes())
        else:
            self.send_error(404)

    def _api_agents(self, params):
        conn = self.get_db()
        try:
            rows = conn.execute("""
                SELECT agent_name, status, current_project, current_task, current_stage,
                       task_start_time, last_action_time, updated_at
                FROM agg_agent_status ORDER BY agent_name
            """).fetchall()
            self.json_response([dict(r) for r in rows])
        finally:
            conn.close()

    def _api_projects(self, params):
        conn = self.get_db()
        try:
            rows = conn.execute("""
                SELECT project_id,
                       COALESCE(base_project, project_id) AS base_project,
                       COALESCE(version, '') AS version,
                       project_name,
                       lifecycle,
                       current_stage,
                       stage_owner,
                       stage_enter_time,
                       total_elapsed_min,
                       is_overtime,
                       latest_artifact,
                       block_reason,
                       status_file,
                       artifact_root,
                       updated_at
                FROM agg_project_flow
                ORDER BY updated_at DESC
            """).fetchall()
            projects = [dict(r) for r in rows]
            grouped = self._group_projects(projects)
            if params.get('grouped', ['0'])[0] in {'1', 'true', 'yes'}:
                self.json_response(grouped)
            else:
                self.json_response(projects)
        finally:
            conn.close()

    def _api_artifacts(self, params):
        project_id = params.get('project_id', [None])[0]
        version = params.get('version', [None])[0]
        stage = params.get('stage', [None])[0]
        conn = self.get_db()
        try:
            artifacts = []
            for project in self._load_project_records(conn, project_id=project_id, version=version):
                artifact_root = Path(project.get('artifact_root') or '').resolve()
                if not artifact_root.exists():
                    continue
                for file_path in sorted(artifact_root.rglob('*')):
                    if not file_path.is_file():
                        continue
                    rel = file_path.relative_to(artifact_root).as_posix()
                    if stage and not rel.startswith(f'{stage}/'):
                        continue
                    stat = file_path.stat()
                    artifacts.append({
                        'project_id': project['project_id'],
                        'base_project': project.get('base_project'),
                        'version': project.get('version'),
                        'stage': rel.split('/', 1)[0] if '/' in rel else '',
                        'name': file_path.name,
                        'path': str(file_path),
                        'relative_path': rel,
                        'size': stat.st_size,
                        'updated_at': self.date_time_string(stat.st_mtime),
                        'preview_type': self._preview_type(file_path),
                        'download_url': f"/api/artifact?path={file_path}",
                        'preview_url': f"/api/artifact?path={file_path}",
                    })
            self.json_response(artifacts)
        finally:
            conn.close()

    def _api_artifact(self, params):
        raw_path = params.get('path', [None])[0]
        if not raw_path:
            return self.json_response({'error': 'path is required'}, status=400)
        file_path = Path(unquote(raw_path)).expanduser().resolve()
        if not file_path.exists() or not file_path.is_file():
            return self.json_response({'error': 'artifact not found'}, status=404)
        if not self._is_safe_artifact_path(file_path):
            return self.json_response({'error': 'forbidden path'}, status=403)

        content_type = self._content_type(file_path)
        disposition = 'attachment' if params.get('download', ['0'])[0] in {'1', 'true', 'yes'} else 'inline'
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Disposition', f'{disposition}; filename="{file_path.name}"')
        self.end_headers()
        self.wfile.write(file_path.read_bytes())

    def _api_events(self, params):
        conn = self.get_db()
        try:
            agent = params.get('agent', [None])[0]
            category = params.get('category', [None])[0]
            limit = int(params.get('limit', [100])[0])

            query = """
                SELECT event_id, event_time, agent_name, project_id, event_category, event_type,
                       severity, model, input_tokens, output_tokens, summary
                FROM event_log WHERE 1=1
            """
            args = []
            if agent:
                query += " AND agent_name = ?"
                args.append(agent)
            if category:
                query += " AND event_category = ?"
                args.append(category)
            query += " ORDER BY event_time DESC LIMIT ?"
            args.append(limit)

            rows = conn.execute(query, args).fetchall()
            self.json_response([dict(r) for r in rows])
        finally:
            conn.close()

    def _api_stats(self, params):
        conn = self.get_db()
        try:
            agent_total = conn.execute("SELECT COUNT(*) FROM agg_agent_status").fetchone()[0]
            agent_active = conn.execute("SELECT COUNT(*) FROM agg_agent_status WHERE status='running'").fetchone()[0]
            proj_total = conn.execute("SELECT COUNT(*) FROM agg_project_flow").fetchone()[0]
            proj_blocked = conn.execute("SELECT COUNT(*) FROM agg_project_flow WHERE block_reason IS NOT NULL AND block_reason != ''").fetchone()[0]
            event_24h = conn.execute("SELECT COUNT(*) FROM event_log WHERE event_time > datetime('now', '-1 day')").fetchone()[0]
            tokens = conn.execute("SELECT COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0) FROM event_log WHERE event_time > datetime('now', '-1 day')").fetchone()

            self.json_response({
                'agents': {'total': agent_total, 'active': agent_active},
                'projects': {'total': proj_total, 'blocked': proj_blocked},
                'events_24h': event_24h,
                'tokens_24h': {'input': tokens[0], 'output': tokens[1]},
            })
        finally:
            conn.close()

    def _api_alerts(self, params):
        conn = self.get_db()
        try:
            limit = self._parse_limit(params.get('limit', [50])[0], default=50, maximum=200)
            rows = conn.execute('SELECT * FROM alerts ORDER BY alert_time DESC LIMIT ?', (limit,)).fetchall()
            self.json_response([dict(r) for r in rows])
        finally:
            conn.close()

    def _load_project_records(self, conn, project_id=None, version=None):
        rows = conn.execute("""
            SELECT project_id,
                   COALESCE(base_project, project_id) AS base_project,
                   COALESCE(version, '') AS version,
                   project_name,
                   lifecycle,
                   current_stage,
                   stage_owner,
                   artifact_root,
                   updated_at
            FROM agg_project_flow
        """).fetchall()
        projects = [dict(r) for r in rows]
        if project_id:
            projects = [p for p in projects if p['project_id'] == project_id]
        if version:
            projects = [p for p in projects if p.get('version') == version]
        return projects

    def _group_projects(self, projects):
        grouped = {}
        for project in projects:
            key = project.get('base_project') or project['project_id']
            group = grouped.setdefault(key, {'base_project': key, 'active_version': None, 'versions': []})
            group['versions'].append(project)
        result = []
        for group in grouped.values():
            group['versions'].sort(key=lambda item: (self._stage_priority(item.get('current_stage')), item.get('updated_at') or ''), reverse=True)
            group['active_version'] = group['versions'][0]['project_id'] if group['versions'] else None
            result.append(group)
        result.sort(key=lambda group: self._stage_priority(group['versions'][0].get('current_stage')) if group['versions'] else -1, reverse=True)
        return result

    def _stage_priority(self, stage):
        order = {'developing': 6, 'testing': 5, 'deploying': 4, 'deployed': 3, 'accepting': 2, 'planned': 1, 'done': 0}
        return order.get(stage or '', -1)

    def _preview_type(self, path):
        suffix = path.suffix.lower()
        if suffix in TEXT_EXTENSIONS:
            return 'markdown' if suffix in {'.md', '.markdown'} else 'text'
        if suffix in IMAGE_EXTENSIONS:
            return 'image'
        if suffix in VIDEO_EXTENSIONS:
            return 'video'
        return 'download'

    def _content_type(self, path):
        suffix = path.suffix.lower()
        if suffix in {'.md', '.markdown'}:
            return 'text/markdown; charset=utf-8'
        guessed, _ = mimetypes.guess_type(str(path))
        return guessed or 'application/octet-stream'

    def _is_safe_artifact_path(self, path):
        try:
            path.relative_to(PROJECTS_HOME.resolve())
            return True
        except ValueError:
            return False

    def _parse_limit(self, raw_limit, default=100, maximum=500):
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            return default
        if limit < 1:
            return default
        return min(limit, maximum)

    def log_message(self, format, *args):
        print(f'[{self.log_date_time_string()}] {args[0]}')


def make_handler(db_path):
    """Create handler class with db_path bound."""
    class Handler(MonitorHandler):
        def get_db(self):
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            return conn
    return Handler


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=int(os.environ.get('PORT', '8080')))
    parser.add_argument('--db', default='data/events.db')
    args = parser.parse_args()

    handler = make_handler(args.db)
    server = HTTPServer(('0.0.0.0', args.port), handler)
    print(f'🚀 Monitor API running on :{args.port} (db={args.db})')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down...')


if __name__ == '__main__':
    main()
