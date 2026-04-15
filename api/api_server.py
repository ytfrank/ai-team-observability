#!/usr/bin/env python3
"""
AI Team Observability - API Server

Serves REST API + static HTML pages for the monitoring dashboard.
Reads from SQLite database populated by collector.py.

Usage: python3 api_server.py [--db PATH] [--port PORT]
"""

import json
import os
import sys
import sqlite3
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path

DB_PATH = os.environ.get('DB_PATH', 'data/events.db')
STATIC_DIR = Path(__file__).parent.parent / 'web' / 'static'


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
        def _serve():
            filepath = STATIC_DIR / filename
            if filepath.exists():
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(filepath.read_bytes())
            else:
                self.send_error(404, f'Page {filename} not found')
        return _serve()

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
            agents = [dict(r) for r in rows]
            self.json_response(agents)
        finally:
            conn.close()

    def _api_projects(self, params):
        conn = self.get_db()
        try:
            rows = conn.execute("""
                SELECT project_id, current_stage, stage_owner, stage_enter_time,
                       total_elapsed_min, is_overtime, latest_artifact, block_reason, updated_at
                FROM agg_project_flow ORDER BY updated_at DESC
            """).fetchall()
            projects = [dict(r) for r in rows]
            self.json_response(projects)
        finally:
            conn.close()

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
            events = [dict(r) for r in rows]
            self.json_response(events)
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
                "agents": {"total": agent_total, "active": agent_active},
                "projects": {"total": proj_total, "blocked": proj_blocked},
                "events_24h": event_24h,
                "tokens_24h": {"input": tokens[0], "output": tokens[1]},
            })
        finally:
            conn.close()

    def _api_alerts(self, params):
        conn = self.get_db()
        try:
            limit = self._parse_limit(params.get('limit', [50])[0], default=50, maximum=200)
            rows = conn.execute(
                "SELECT * FROM alerts ORDER BY alert_time DESC LIMIT ?",
                (limit,),
            ).fetchall()
            alerts = [dict(r) for r in rows]
            self.json_response(alerts)
        finally:
            conn.close()

    def _parse_limit(self, raw_limit, default=100, maximum=500):
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            return default
        if limit < 1:
            return default
        return min(limit, maximum)

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {args[0]}")


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
    print(f"🚀 Monitor API running on :{args.port} (db={args.db})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")


if __name__ == '__main__':
    main()
