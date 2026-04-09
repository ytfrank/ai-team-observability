# 测试报告 — ai-team-observability V1.0

**测试人**: Guard  
**测试时间**: 2026-04-10 04:10 ~ 04:15  
**对应commit**: fd33aa7 / 67df601  
**风险等级**: medium  
**测试矩阵**: normal（api + ui_flow + logs_config）

---

## 测试结论: ⚠️ Conditional Pass

**核心功能可用，API和Dashboard正常运行，但存在数据采集不完整和代码质量问题。**

---

## 已验证 ✅

| # | 测试项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | Collector `--once` 运行 | ✅ 无报错 | 采集6 agents, 4 projects, 0.0s |
| 2 | SQLite schema 正确 | ✅ 6张表+索引 | event_log, agg_agent_status, agg_project_flow, agg_model_usage, alerts, collector_state |
| 3 | /api/stats | ✅ 返回正确JSON | agents:6/active:3, projects:4, events_24h:0 |
| 4 | /api/agents | ✅ 6个agent状态 | 含name/status/project/task |
| 5 | /api/projects | ✅ 4个项目信息 | 含stage/owner/artifact |
| 6 | /api/events | ✅ 返回空数组 | event_log为0条，符合预期 |
| 7 | /api/alerts | ✅ 返回1条告警 | developing_30m_no_output (peter) |
| 8 | Dashboard / | ✅ HTTP 200 | HTML渲染正常 |
| 9 | /team/agents | ✅ HTTP 200 | 占位页 |
| 10 | /team/projects | ✅ HTTP 200 | 占位页 |
| 11 | /team/alerts | ✅ HTTP 200 | 占位页 |
| 12 | 404处理 | ✅ 不存在路由返回404 | |
| 13 | 30s自动刷新 | ✅ setInterval(refresh, 30000) | index.html 含刷新逻辑 |
| 14 | Collector重复运行 | ✅ 连续跑两次无报错 | 数据更新正常 |
| 15 | 空数据处理 | ✅ events为空时API返回[] | 不崩溃 |

---

## 未验证 ⚠️

| # | 项 | 原因 | 风险 |
|---|-----|------|------|
| 1 | 浏览器真实渲染 | 无headless browser | 低（HTML结构正确） |
| 2 | 30s刷新数据更新 | 需长时间运行验证 | 低 |
| 3 | 告警通知通道 | 飞书集成未实现 | 中（P1告警无法送达） |
| 4 | 并发压测 | 非V1重点 | 低 |
| 5 | monitor.doramax.cn线上 | 未部署 | 高（验收标准第7条） |
| 6 | 前端详情页 | 占位未开发 | 中 |

---

## 发现问题 🔍

### P2 - 数据采集不完整
- **event_log 采集0条事件**：Collector只成功采集了agent状态和项目流转，但核心事件流为空
- **原因**：Collector的session解析逻辑可能未正确读取 `~/.openclaw/agents/*/sessions/` 下的JSONL文件
- **影响**：无法回放任务轨迹（违反验收标准第5条），token统计为0（违反验收标准第1条）
- **建议**：Peter需排查collector对session文件的解析逻辑

### P3 - 数据准确性问题
- **agent状态数据来源是status.json的runtime字段**，非真实session解析
- **guard显示current_task="Phase 1已完成，已提测"**：这是过时数据，当前实际在执行测试
- **影响**：数据非实时，与需求文档要求"数据必须真实有效"有差距

### P3 - 代码质量问题
- `api/main.go` 存在但未完成（Go未安装），保留未使用代码
- `collector/alert_rules.py` 在SUBMISSION中提到但实际不存在（集成在collector.py中）

### P3 - 验收标准未完全达成
- 验收标准第5条"回放任务关键轨迹"：❌ event_log为空
- 验收标准第7条"部署到monitor.doramax.cn"：❌ 未部署
- 验收标准第1条"多provider调用和token趋势"：⚠️ 数据为0

---

## 风险评估

| 风险 | 等级 | 说明 |
|------|------|------|
| 核心事件数据为空 | 中 | 需修复collector session解析 |
| 未部署线上 | 高 | 波哥无法线上确认 |
| 前端详情页未开发 | 低 | Phase 2范围 |
| Go版API废弃代码 | 低 | 可清理 |

---

## 放行建议

**⚠️ Conditional Pass — 基础框架可用，但核心数据采集需修复后才能进入验收**

**前提条件**：
1. Peter修复Collector的session解析，使event_log有真实数据
2. Atlas完成部署到 monitor.doramax.cn
3. 部署后做一轮线上冒烟验证

---

*Guard | 2026-04-10 04:15*
