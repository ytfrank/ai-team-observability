#!/usr/bin/env python3
"""
AI Team Observability - Alert Engine

Checks 3 alerts:
  1. developing_30m_no_output      - stage=developing 30min+ without real output
  2. claimed_subagent_but_not_found - runtime claims sub-agent but no system record
  3. runtime_status_stale_or_inconsistent - runtime says in_progress but no event update in 30min

Usage: python3 alert_engine.py [--db PATH] [--once]
"""

import json
import os
import sys
import time
import sqlite3
import hashlib
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

OPENCLAW_HOME = Path(os.environ.get('OPENCLAW_HOME', os.path.expanduser('~/.openclaw')))
PROJECTS_HOME = Path(os.environ.get('PROJECTS_HOME', os.path.expanduser('~/projects')))
CST = timezone(timedelta(hours=8))

def now_cst():
    return datetime.now(CST).isoformat(timespec='seconds')

def parse_time(ts_str):
    """Parse ISO time string to datetime."""
    if not ts_str:
        return None
    try:
        # Handle various formats
        ts_str = ts_str.replace('+08:00', '').replace('+0800', '')
        return datetime.fromisoformat(ts_str).replace(tzinfo=CST)
    except:
        return None

def alert_id(alert_type, project_id, agent_name=""):
    raw = f"{alert_type}|{project_id}|{agent_name}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

def check_developing_30m_no_output(conn):
    """
    Alert: stage=developing/testing/reviewing/deploying for 30+ min
    AND last_real_output_time is null or older than 30 min.
    """
    alerts = []
    cutoff = datetime.now(CST) - timedelta(minutes=30)

    for status_file in PROJECTS_HOME.glob('*/monitor/*/status.json'):
        try:
            data = json.loads(status_file.read_text())
            if data.get('lifecycle') != 'active':
                continue

            wf = data.get('workflow', {})
            stage = wf.get('current_stage', '')
            if stage not in ('developing', 'testing', 'reviewing', 'deploying'):
                continue

            # Find when this stage was entered
            stage_entered = None
            for entry in wf.get('stage_history', []):
                if entry.get('stage') == stage:
                    stage_entered = parse_time(entry.get('entered_at'))
                    # Use the latest entry for this stage
                    exited = entry.get('exited_at')
                    if not exited:
                        break

            if not stage_entered:
                continue

            project_id = data.get('project_id', status_file.parent.parent.parent.name)

            # Check last_real_output_time
            rt = data.get('runtime', {})
            last_output = rt.get('last_real_output_time')
            last_output_dt = parse_time(last_output) if last_output else None

            # If no output time or output time is before cutoff
            no_recent_output = (last_output_dt is None or last_output_dt < cutoff)

            # Check if stage has been active for 30+ min
            elapsed = datetime.now(CST) - stage_entered
            if elapsed >= timedelta(minutes=30) and no_recent_output:
                alerts.append({
                    'alert_id': alert_id('developing_30m_no_output', project_id),
                    'alert_type': 'developing_30m_no_output',
                    'severity': 'warning',
                    'agent_name': wf.get('stage_owner'),
                    'project_id': project_id,
                    'message': f"[{project_id}] 阶段 {stage} 已持续 {int(elapsed.total_seconds()/60)} 分钟，"
                               f"最近30分钟无真实产出。stage_owner={wf.get('stage_owner')}",
                })

        except Exception as e:
            print(f"[WARN] check_developing_30m_no_output: {e}")

    return alerts


def check_claimed_subagent_not_found(conn):
    """
    Alert: runtime claims sub-agent activity but no matching session found.
    """
    alerts = []

    # Get all agents' recent active tasks mentioning sub-agent
    for status_file in PROJECTS_HOME.glob('*/monitor/*/status.json'):
        try:
            data = json.loads(status_file.read_text())
            if data.get('lifecycle') != 'active':
                continue

            rt = data.get('runtime', {})
            project_id = data.get('project_id', status_file.parent.parent.parent.name)
            wf = data.get('workflow', {})
            agent_name = wf.get('stage_owner', '')

            # Check false_claim_flag
            if rt.get('false_claim_flag'):
                alerts.append({
                    'alert_id': alert_id('claimed_subagent_but_not_found', project_id, agent_name),
                    'alert_type': 'claimed_subagent_but_not_found',
                    'severity': 'high',
                    'agent_name': agent_name,
                    'project_id': project_id,
                    'message': f"[{project_id}] {agent_name} 声称已启动sub-agent但系统查无记录",
                })

            # Also auto-detect: if active_tasks mention sub-agent, check event_log
            active_tasks = rt.get('active_tasks', [])
            claims_subagent = any('sub-agent' in str(t).lower() or 'subagent' in str(t).lower()
                                 for t in active_tasks)

            if claims_subagent and agent_name:
                # Check if there's any recent sub-agent event in event_log
                row = conn.execute("""
                    SELECT COUNT(*) FROM event_log
                    WHERE agent_name = ? AND event_time > ?
                    AND (summary LIKE '%sub-agent%' OR summary LIKE '%subagent%'
                         OR payload_json LIKE '%sub-agent%' OR payload_json LIKE '%subagent%')
                """, (agent_name, (datetime.now(CST) - timedelta(hours=1)).isoformat())).fetchone()

                if row[0] == 0:
                    alerts.append({
                        'alert_id': alert_id('claimed_subagent_but_not_found', project_id, agent_name),
                        'alert_type': 'claimed_subagent_but_not_found',
                        'severity': 'high',
                        'agent_name': agent_name,
                        'project_id': project_id,
                        'message': f"[{project_id}] {agent_name} active_tasks提及sub-agent但近1小时事件日志无记录",
                    })

        except Exception as e:
            print(f"[WARN] check_claimed_subagent_not_found: {e}")

    return alerts


def check_runtime_stale_or_inconsistent(conn):
    """
    Alert: runtime/status shows in_progress but no event update in 30+ min.
    """
    alerts = []
    cutoff = (datetime.now(CST) - timedelta(minutes=30)).isoformat()

    for status_file in PROJECTS_HOME.glob('*/monitor/*/status.json'):
        try:
            data = json.loads(status_file.read_text())
            if data.get('lifecycle') != 'active':
                continue

            wf = data.get('workflow', {})
            if wf.get('stage_status') != 'in_progress':
                continue

            project_id = data.get('project_id', status_file.parent.parent.parent.name)
            rt = data.get('runtime', {})
            agent_name = wf.get('stage_owner', rt.get('active_role', ''))

            # Check last_runtime_update_at
            last_update = rt.get('last_runtime_update_at')
            if last_update:
                last_dt = parse_time(last_update)
                if last_dt and last_dt < datetime.now(CST) - timedelta(minutes=30):
                    # Runtime says in_progress but hasn't been updated in 30+ min
                    alerts.append({
                        'alert_id': alert_id('runtime_status_stale_or_inconsistent', project_id, agent_name),
                        'alert_type': 'runtime_status_stale_or_inconsistent',
                        'severity': 'warning',
                        'agent_name': agent_name,
                        'project_id': project_id,
                        'message': f"[{project_id}] runtime显示in_progress但已{int((datetime.now(CST)-last_dt).total_seconds()/60)}分钟未更新",
                    })

            # Also check: progress_verified should be true for active stages
            if rt.get('progress_verified') == False:
                alerts.append({
                    'alert_id': alert_id('runtime_status_stale_or_inconsistent', project_id, agent_name) + '_pv',
                    'alert_type': 'runtime_status_stale_or_inconsistent',
                    'severity': 'info',
                    'agent_name': agent_name,
                    'project_id': project_id,
                    'message': f"[{project_id}] progress_verified=false，进展无证据支撑",
                })

        except Exception as e:
            print(f"[WARN] check_runtime_stale_or_inconsistent: {e}")

    return alerts


def write_alerts(conn, alerts):
    """Write alerts to DB, skip if already active (not resolved)."""
    written = 0
    now = now_cst()
    for a in alerts:
        try:
            # Check if this alert is already active (not resolved)
            row = conn.execute(
                "SELECT alert_id FROM alerts WHERE alert_id = ? AND resolved_at IS NULL",
                (a['alert_id'],)).fetchone()
            if row:
                continue  # Already active, don't duplicate

            conn.execute("""
                INSERT OR IGNORE INTO alerts
                (alert_id, alert_time, alert_type, severity, agent_name, project_id, message)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (a['alert_id'], now, a['alert_type'], a['severity'],
                  a.get('agent_name'), a.get('project_id'), a.get('message')))
            written += 1
            print(f"  [ALERT] {a['alert_type']}: {a['message'][:80]}")
        except Exception as e:
            print(f"[WARN] Write alert failed: {e}")

    conn.commit()
    return written


def run_once(conn):
    """Run all alert checks once."""
    t0 = time.time()
    print(f"\n[{now_cst()}] Alert engine running...")

    all_alerts = []
    all_alerts.extend(check_developing_30m_no_output(conn))
    all_alerts.extend(check_claimed_subagent_not_found(conn))
    all_alerts.extend(check_runtime_stale_or_inconsistent(conn))

    written = write_alerts(conn, all_alerts)
    elapsed = time.time() - t0
    print(f"[{now_cst()}] Alert engine: {len(all_alerts)} checks, {written} new alerts in {elapsed:.1f}s")
    return written


def main():
    parser = argparse.ArgumentParser(description='AI Team Alert Engine')
    parser.add_argument('--db', default='data/events.db', help='SQLite database path')
    parser.add_argument('--once', action='store_true', help='Run once and exit')
    parser.add_argument('--interval', type=int, default=120, help='Check interval in seconds')
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)

    if args.once:
        run_once(conn)
    else:
        print(f"[{now_cst()}] Alert engine started (db={args.db}, interval={args.interval}s)")
        while True:
            try:
                run_once(conn)
            except Exception as e:
                print(f"[ERROR] Alert cycle failed: {e}")
            time.sleep(args.interval)


if __name__ == '__main__':
    main()
