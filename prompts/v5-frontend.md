# Task: Frontend — Agent Timeline + Project List + Alerts + Freshness

## Project
- Repo: /Users/bibo/projects/ai-team-observability
- Branch: v5
- You MUST stay on v5 branch

## Goal
Implement 4 frontend changes:

### 1. Agent Timeline Enhancement (agents.html)
Enhance the existing timeline to support:
- Milestone classification icons/colors: stage_enter(green), stage_exit(blue), artifact_commit(purple), subagent_spawn(orange), a2a_send/a2a_receive(cyan), error(red), warning(yellow), default(gray)
- Each timeline item clickable to expand/collapse full detail
- Current stage highlighted with a banner at top of detail view
- Default 7 days, support today/30d via existing range selector
- The API /api/agent_detail already returns timeline with `kind` and `detail` fields

### 2. Project List Fix (projects.html + index.html)
- Sort projects: active first (stages: developing, testing, planned, draft), then blocked, then done/archived at bottom
- Done/archived projects: default collapsed (use <details> without `open`), show count badge like "3 已完成版本"
- Dashboard index.html project section: same sort order

### 3. Alerts Page (alerts.html)
Redesign from placeholder to working page:
- Alert list with severity badges (critical=red, warning=yellow)
- Click alert → show detail panel with: alert_type, message, agent_name, project_id, alert_time, severity
- Alert statistics bar at top: total, critical count, warning count
- "Mark as acknowledged" button per alert (calls PUT /api/alerts/{id}/ack)
- Empty state when no alerts

### 4. Data Freshness Indicator
- Add a small banner at top of index.html showing "数据更新于: {time}" from /api/stats.last_collector_run
- If data > 10 min old, show in red with "⚠️ 数据可能过期"

## Files to modify
- `web/static/agents.html`
- `web/static/projects.html`
- `web/static/index.html`
- `web/static/alerts.html`

## Files NOT to modify
- `api/api_server.py`
- `collector/collector.py`
- `tests/test_api_server.py`

## Verification
Check that all pages load without JS errors by verifying:
- All API endpoints referenced exist (/api/agent_detail, /api/stats, /api/alerts, /api/projects)
- No broken HTML structure

## Output
Report: which files changed, what sections added, any issues found.
