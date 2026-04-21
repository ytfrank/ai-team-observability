# Task: Test + Verify — Update Unit Tests for V5

## Project
- Repo: /Users/bibo/projects/ai-team-observability
- Branch: v5
- You MUST stay on v5 branch

## Goal
Update and extend tests to cover V5 changes. Run after backend changes are in place.

### Tests to add/update in tests/test_api_server.py

1. **test_alerts_api_returns_real_data** — seed alerts via collector alert engine, verify /api/alerts returns them with correct severity

2. **test_agent_detail_milestone_classification** — verify /api/agent_detail timeline items have correct `kind` classification (subagent, a2a, error, milestone, tool)

3. **test_projects_api_active_sorted_first** — seed projects with mixed stages (developing, done, testing, archived), verify /api/projects returns active stages before done/archived

4. **test_stats_includes_collector_freshness** — seed collector_state with last_run, verify /api/stats includes last_collector_run and collector_status fields

5. **test_alerts_pagination** — seed 5+ alerts, verify limit/offset params work on /api/alerts

6. **test_artifact_path_traversal_blocked** — verify /api/artifact?path=/etc/passwd returns 403

7. Update existing tests if API signatures changed (e.g., /api/agent_detail with limit param)

### Also verify
- `python3 -m unittest -q tests/test_api_server.py` all pass

## Files to modify
- `tests/test_api_server.py`

## Files NOT to modify
- `api/api_server.py`
- `collector/collector.py`
- `web/static/*.html`

## Verification
```bash
cd /Users/bibo/projects/ai-team-observability
python3 -m unittest -q tests/test_api_server.py
```

## Output
Report: test count, pass/fail results, any issues.
