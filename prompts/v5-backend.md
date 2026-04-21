# Task: Backend — Alert Engine + Collector Enhancement + API Performance

## Project
- Repo: /Users/bibo/projects/ai-team-observability
- Branch: v5
- You MUST stay on v5 branch

## Goal
Implement 3 backend changes:

### 1. Alert Rule Engine in collector.py
Add a `run_alert_checks(conn)` function called at end of `run_once()`. Implement 5 rules:

1. **agent_stalled**: For each agent in agg_agent_status, if last_action_time > 30 min ago AND status='running', insert alert (severity=warning)
2. **project_overtime_12h**: For each project in agg_project_flow where current_stage NOT IN ('done','deployed','archived','cancelled'), if stage_enter_time > 12h ago, insert alert (severity=warning)
3. **project_overtime_24h**: Same but > 24h, severity=critical
4. **project_overtime_48h**: Same but > 48h, severity=critical
5. **consecutive_stalled**: Check agg_project_flow where block_reason is not empty, if updated_at > 1h ago with same block_reason, severity=critical

Alert schema: use existing `alerts` table. Generate deterministic alert_id from rule_type+entity. Use INSERT OR IGNORE to avoid duplicates on re-run. Set acknowledged=0.

Also update `collector_state` with key='last_alert_run' and value=timestamp.

### 2. Enhance Event Classification in collector.py
In the session scanner, improve classification by checking summary/payload_json for:
- `sessions_spawn` or `subagent` → event_category='subagent'
- `sessions_send` or `A2A` → event_category='a2a'
- `error` or `failed` in summary → severity='error'
- `stage_enter` or `stage_exit' or 'developing' or 'testing' → event_category='milestone'

### 3. API Performance in api_server.py
- Add DB indexes in init_db() for: event_log(event_time DESC), event_log(agent_name, event_time DESC)
- Add `limit` parameter (default 100, max 500) to /api/agent_detail timeline query
- Add pagination (limit/offset) to /api/alerts
- Add `last_collector_run` and `collector_status` fields to /api/stats response (read from collector_state table)

## Files to modify
- `collector/collector.py`
- `api/api_server.py`

## Files NOT to modify
- `web/static/*.html`
- `tests/test_api_server.py`

## Verification
After changes, run:
```bash
cd /Users/bibo/projects/ai-team-observability
python3 -c "from collector.collector import init_db, run_alert_checks; conn=init_db('data/events.db'); run_alert_checks(conn); print('alerts:', conn.execute('SELECT COUNT(*) FROM alerts').fetchone()[0])"
python3 -m unittest -q tests/test_api_server.py
```

## Output
Report: which files changed, what functions added, verification results.
