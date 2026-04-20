#!/usr/bin/env python3
"""
AI Team Observability - Event Collector

Scans OpenClaw session files, agent logs, status.json etc.
Writes events to SQLite for the monitoring dashboard.

Usage: python3 collector.py [--db PATH] [--once]
  --db    Path to SQLite database (default: data/events.db)
  --once  Run once instead of continuous loop
"""

import json
import os
import sys
import time
import glob
import sqlite3
import hashlib
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Config ──────────────────────────────────────────────

OPENCLAW_HOME = Path(os.environ.get('OPENCLAW_HOME', os.path.expanduser('~/.openclaw')))
PROJECTS_HOME = Path(os.environ.get('PROJECTS_HOME', os.path.expanduser('~/projects')))
AGENTS_DIR = OPENCLAW_HOME / 'agents'

CST = timezone(timedelta(hours=8))

# ── SQLite Schema ───────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS event_log (
    event_id      TEXT PRIMARY KEY,
    event_time    TEXT NOT NULL,
    source_type   TEXT NOT NULL,
    agent_name    TEXT NOT NULL,
    project_id    TEXT,
    event_category TEXT NOT NULL,
    event_type    TEXT NOT NULL,
    severity      TEXT DEFAULT 'info',
    provider      TEXT,
    model         TEXT,
    input_tokens  INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    summary       TEXT,
    payload_json  TEXT
);

CREATE INDEX IF NOT EXISTS idx_event_time ON event_log(event_time);
CREATE INDEX IF NOT EXISTS idx_agent ON event_log(agent_name, event_time);
CREATE INDEX IF NOT EXISTS idx_project ON event_log(project_id, event_time);

CREATE TABLE IF NOT EXISTS agg_agent_status (
    agent_name       TEXT PRIMARY KEY,
    status           TEXT NOT NULL DEFAULT 'idle',
    current_project  TEXT,
    current_task     TEXT,
    current_stage    TEXT,
    current_model    TEXT,
    task_start_time  TEXT,
    last_action_time TEXT,
    last_a2a_time    TEXT,
    last_5_actions   TEXT,
    updated_at       TEXT
);

CREATE TABLE IF NOT EXISTS agg_project_flow (
    project_id       TEXT PRIMARY KEY,
    base_project     TEXT,
    version          TEXT,
    project_name     TEXT,
    lifecycle        TEXT,
    current_stage    TEXT NOT NULL,
    stage_owner      TEXT,
    stage_enter_time TEXT,
    total_elapsed_min INTEGER DEFAULT 0,
    is_overtime      INTEGER DEFAULT 0,
    latest_artifact  TEXT,
    block_reason     TEXT,
    stage_history    TEXT,
    status_file      TEXT,
    artifact_root    TEXT,
    updated_at       TEXT
);

CREATE TABLE IF NOT EXISTS agg_model_usage (
    provider       TEXT,
    model          TEXT,
    period_start   TEXT,
    period_type    TEXT,
    request_count  INTEGER DEFAULT 0,
    input_tokens   INTEGER DEFAULT 0,
    output_tokens  INTEGER DEFAULT 0,
    by_agent       TEXT,
    PRIMARY KEY (provider, model, period_start, period_type)
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id     TEXT PRIMARY KEY,
    alert_time   TEXT NOT NULL,
    alert_type   TEXT NOT NULL,
    severity     TEXT NOT NULL,
    agent_name   TEXT,
    project_id   TEXT,
    message      TEXT,
    notified     TEXT,
    acknowledged INTEGER DEFAULT 0,
    resolved_at  TEXT
);

CREATE TABLE IF NOT EXISTS collector_state (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

def init_db(db_path):
    """Initialize SQLite database with schema."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_SQL)
    ensure_schema(conn)
    conn.commit()
    return conn

def ensure_schema(conn):
    """Best-effort lightweight migrations for SQLite tables."""
    expected = {
        'agg_project_flow': {
            'base_project': 'TEXT',
            'version': 'TEXT',
            'project_name': 'TEXT',
            'lifecycle': 'TEXT',
            'status_file': 'TEXT',
            'artifact_root': 'TEXT',
        }
    }
    for table, columns in expected.items():
        try:
            existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        except Exception:
            continue
        for column, sql_type in columns.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")
        conn.commit()


def normalize_base_project(project_id, fallback_name):
    value = project_id or fallback_name or ''
    for marker in ('-v', '_v'):
        idx = value.lower().rfind(marker)
        if idx > 0:
            suffix = value[idx + 2:]
            if suffix and (suffix[0].isdigit() or suffix.startswith(('main', 'dev'))):
                return value[:idx]
    return value


def parse_project_record(status_file):
    data = json.loads(status_file.read_text())
    repo_name = status_file.parent.parent.parent.name
    version = status_file.parent.name
    workflow = data.get('workflow', {})
    runtime = data.get('runtime', {})
    official = data.get('official', {})

    raw_project_id = data.get('project_id') or data.get('project') or repo_name
    project_id = raw_project_id if version in str(raw_project_id) else f"{repo_name}-{version}"
    base_project = data.get('project') or normalize_base_project(raw_project_id, repo_name) or repo_name
    current_stage = workflow.get('current_stage') or data.get('stage') or official.get('current_assessment') or 'unknown'
    blockers = runtime.get('current_blockers') or official.get('blockers') or data.get('blockers') or []
    block_reason = ', '.join(str(item) for item in blockers if item)
    if current_stage in {'deployed', 'done'} and not blockers:
        block_reason = ''

    status_dir = status_file.parent
    artifacts_base_path = data.get('artifacts_base_path')
    artifact_root = (status_file.parent.parent.parent / artifacts_base_path).resolve() if artifacts_base_path else status_dir.resolve()

    return {
        'project_id': project_id,
        'base_project': base_project,
        'version': version,
        'project_name': data.get('project_name') or data.get('project') or repo_name,
        'lifecycle': data.get('lifecycle') or workflow.get('stage_status') or data.get('type'),
        'current_stage': current_stage,
        'stage_owner': workflow.get('stage_owner') or data.get('owner'),
        'stage_enter_time': workflow.get('stage_entered_at') or workflow.get('stage_enter_time') or data.get('updated_at'),
        'total_elapsed_min': 0,
        'is_overtime': 0,
        'latest_artifact': runtime.get('latest_commit') or runtime.get('latest_artifact_update'),
        'block_reason': block_reason,
        'stage_history': json.dumps(workflow.get('stage_history') or workflow.get('history') or data.get('history', []), ensure_ascii=False),
        'status_file': str(status_file.resolve()),
        'artifact_root': str(artifact_root),
        'updated_at': official.get('updated_at') or runtime.get('last_runtime_update_at') or data.get('updated_at') or now_cst(),
    }

def event_id(*parts):
    """Generate deterministic event ID."""
    raw = '|'.join(str(p) for p in parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

def now_cst():
    return datetime.now(CST).isoformat(timespec='seconds')

# ── Data Source 1: Session Files ────────────────────────

def scan_sessions(conn, last_run):
    """Scan OpenClaw session JSONL files for agent activity."""
    events = []

    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir():
            continue
        agent_name = agent_dir.name
        agent_sessions = agent_dir / 'sessions'
        if not agent_sessions.exists():
            continue

        for session_file in sorted(agent_sessions.glob('*.jsonl')):
            mtime = os.path.getmtime(session_file)
            if mtime < last_run:
                continue

            try:
                with open(session_file) as f:
                    for line_no, line in enumerate(f, 1):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        # Extract relevant events
                        # OpenClaw JSONL: top-level has 'type', 'timestamp'
                        # For type='message', actual content is nested under 'message' key
                        ts = entry.get('ts', entry.get('timestamp', ''))
                        if not ts:
                            continue

                        entry_type = entry.get('type', '')
                        msg = entry.get('message', {})

                        # For message entries, extract from nested 'message' dict
                        role = msg.get('role', '') if isinstance(msg, dict) else ''
                        model = msg.get('model', '') if isinstance(msg, dict) else ''
                        usage = msg.get('usage', {}) if isinstance(msg, dict) else {}
                        provider = msg.get('provider', entry.get('provider')) if isinstance(msg, dict) else entry.get('provider')
                        content_raw = msg.get('content', '') if isinstance(msg, dict) else ''

                        # Extract text from content array format
                        summary = ''
                        if isinstance(content_raw, list):
                            for part in content_raw:
                                if isinstance(part, dict) and part.get('type') == 'text':
                                    summary = part.get('text', '')[:200]
                                    break
                        elif isinstance(content_raw, str):
                            summary = content_raw[:200]

                        eid = event_id(str(session_file), line_no)
                        inp = usage.get('input', 0) or usage.get('prompt_tokens', 0) or 0
                        out = usage.get('output', 0) or usage.get('completion_tokens', 0) or 0

                        events.append({
                            'event_id': eid,
                            'event_time': ts if isinstance(ts, str) else str(ts),
                            'source_type': 'session_file',
                            'agent_name': agent_name,
                            'project_id': entry.get('project_id'),
                            'event_category': 'llm' if model else 'lifecycle',
                            'event_type': entry_type or role,
                            'severity': 'info',
                            'provider': provider,
                            'model': model,
                            'input_tokens': inp,
                            'output_tokens': out,
                            'summary': summary or None,
                            'payload_json': json.dumps(entry, ensure_ascii=False)[:2000],
                        })

            except Exception as e:
                print(f"[WARN] Failed to read {session_file}: {e}")

    return events

# ── Data Source 2: status.json ──────────────────────────

def scan_status_json(conn):
    """Scan all project status.json files for project flow data."""
    projects = []
    for status_file in PROJECTS_HOME.glob('*/monitor/*/status.json'):
        if '_templates' in status_file.parts:
            continue
        try:
            projects.append(parse_project_record(status_file))

            # Upsert project flow
            conn.execute("""
                INSERT OR REPLACE INTO agg_project_flow
                (project_id, base_project, version, project_name, lifecycle,
                 current_stage, stage_owner, stage_enter_time,
                 total_elapsed_min, is_overtime, latest_artifact, block_reason,
                 stage_history, status_file, artifact_root, updated_at)
                VALUES (:project_id, :base_project, :version, :project_name, :lifecycle,
                        :current_stage, :stage_owner, :stage_enter_time,
                        :total_elapsed_min, :is_overtime, :latest_artifact, :block_reason,
                        :stage_history, :status_file, :artifact_root, :updated_at)
            """, projects[-1])

        except Exception as e:
            print(f"[WARN] Failed to read {status_file}: {e}")

    conn.commit()
    return projects

# ── Data Source 3: Agent workspace status ───────────────

def scan_agent_status(conn):
    """Determine agent status from workspace files."""
    agents = ['peter', 'guard', 'doraemon', 'atlas', 'jarvis', 'munger']

    for agent_name in agents:
        ws = OPENCLAW_HOME / 'workspaces' / agent_name
        status = 'idle'
        current_project = None
        current_task = None
        current_stage = None
        last_action = None

        # Check memory files for recent activity
        memory_dir = ws / 'memory'
        if memory_dir.exists():
            today = datetime.now(CST).strftime('%Y-%m-%d')
            today_file = memory_dir / f'{today}.md'
            if today_file.exists():
                mtime = os.path.getmtime(today_file)
                last_action = datetime.fromtimestamp(mtime, CST).isoformat(timespec='seconds')
                # If modified in last 30 min, consider active
                if time.time() - mtime < 1800:
                    status = 'running'

        # Check active tasks from status files
        for status_file in PROJECTS_HOME.glob('*/monitor/*/status.json'):
            try:
                data = json.loads(status_file.read_text())
                if data.get('workflow', {}).get('stage_owner') == agent_name:
                    current_project = data.get('project_id')
                    current_stage = data.get('workflow', {}).get('current_stage')
                    rt = data.get('runtime', {})
                    current_task = ', '.join(rt.get('active_tasks', []))
                    status = 'running'
            except:
                pass

        conn.execute("""
            INSERT OR REPLACE INTO agg_agent_status
            (agent_name, status, current_project, current_task, current_stage,
             task_start_time, last_action_time, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (agent_name, status, current_project, current_task, current_stage,
              None, last_action, now_cst()))

    conn.commit()

# ── Write Events ────────────────────────────────────────

def write_events(conn, events):
    """Batch write events to SQLite, skip duplicates."""
    written = 0
    for e in events:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO event_log
                (event_id, event_time, source_type, agent_name, project_id,
                 event_category, event_type, severity, provider, model,
                 input_tokens, output_tokens, summary, payload_json)
                VALUES (:event_id, :event_time, :source_type, :agent_name, :project_id,
                        :event_category, :event_type, :severity, :provider, :model,
                        :input_tokens, :output_tokens, :summary, :payload_json)
            """, e)
            written += 1
        except Exception as ex:
            print(f"[WARN] Write event failed: {ex}")

    conn.commit()
    return written

# ── Main ────────────────────────────────────────────────

def run_once(conn):
    """Single collection cycle."""
    t0 = time.time()

    # Get last run timestamp
    row = conn.execute("SELECT value FROM collector_state WHERE key='last_run'").fetchone()
    last_run = float(row[0]) if row else 0

    # Scan data sources
    events = scan_sessions(conn, last_run)
    event_count = write_events(conn, events)

    projects = scan_status_json(conn)
    scan_agent_status(conn)

    # Update last run
    conn.execute("INSERT OR REPLACE INTO collector_state (key, value) VALUES ('last_run', ?)",
                 (str(time.time()),))
    conn.commit()

    elapsed = time.time() - t0
    print(f"[{now_cst()}] Collected: {event_count} events, {len(projects)} projects in {elapsed:.1f}s")


def main():
    parser = argparse.ArgumentParser(description='AI Team Observability Collector')
    parser.add_argument('--db', default='data/events.db', help='SQLite database path')
    parser.add_argument('--once', action='store_true', help='Run once and exit')
    parser.add_argument('--interval', type=int, default=60, help='Collection interval in seconds')
    args = parser.parse_args()

    conn = init_db(args.db)
    print(f"[{now_cst()}] Collector started (db={args.db})")

    if args.once:
        run_once(conn)
    else:
        while True:
            try:
                run_once(conn)
            except Exception as e:
                print(f"[ERROR] Collection cycle failed: {e}")
            time.sleep(args.interval)


if __name__ == '__main__':
    main()
