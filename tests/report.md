# 测试报告 — ai-team-observability V1.0（第二轮）

**测试负责人**: Guard  
**测试时间**: 2026-04-10 06:11 CST  
**对应commit**: 95ea363 / cc8b6b8  
**测试矩阵**: normal  
**风险等级**: medium  

---

## 测试结论：⚠️ Conditional Pass

> Collector核心功能已修复，API/Dashboard正常运行，数据采集真实有效。但存在1个P2问题（project_id为空导致无法按项目回放轨迹）和1个已知非阻塞项（未部署）。

---

## 已验证

| # | 测试项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | Collector运行 (--once) | ✅ | 6960 events collected, 4 projects, 无报错 |
| 2 | event_log数据量 | ✅ | 6960条（lifecycle: 4232, llm: 2728） |
| 3 | 多provider token统计 | ✅ | 6个provider有真实数据：glm-5.1(1906次/15.3M input)、glm-5(379次)、glm-4.7(227次)、gpt-5.4(128次)、claude-sonnet(73次)、claude-opus(8次) |
| 4 | LLM事件token完整性 | ✅ | 2728条LLM事件中2136条有input/output token数据 |
| 5 | API /api/stats | ✅ | events_24h=5334, tokens_24h.input=16.6M, tokens_24h.output=384K |
| 6 | API /api/events?category=llm | ✅ | 返回LLM事件，含真实model/token/summary |
| 7 | API /api/agents | ✅ | 6个agent，状态合理 |
| 8 | API /api/projects | ✅ | 4个项目，含ai-team-observability(testing/guard) |
| 9 | Dashboard主页 | ✅ | HTTP 200 |
| 10 | 30s自动刷新 | ✅ | setInterval(refresh, 30000) |
| 11 | Collector重复运行 | ✅ | 第二次运行无报错 |
| 12 | API 404处理 | ✅ | 不存在路由返回404 |

## 未验证 / 存在问题

### P2: project_id字段全部为空（影响验收标准#5）

**现象**: 6960条事件中，project_id全部为NULL。Collector从session JSONL中读取 `entry.get('project_id')`，但OpenClaw session文件不含此字段。

**影响**: 
- 无法按项目过滤事件、回放任务轨迹
- 验收标准#5（回放任务关键轨迹）无法完全满足
- Dashboard按项目筛选功能失效

**建议修复**: Collector需通过其他方式关联项目（如：从session文件路径/内容推断agent当前所属项目，或从status.json反向关联）。

### 非阻塞项

| # | 项目 | 状态 |
|---|------|------|
| 1 | 部署到monitor.doramax.cn | 待Atlas执行 |
| 2 | 前端详情页（agents/projects/alerts） | 占位页面，Phase 2范围 |
| 3 | Go版API | 未完成，Python版可用 |

## 验收标准对照

| # | 标准 | 状态 |
|---|------|------|
| 1 | 多provider调用和token趋势 | ✅ 6个provider有真实数据 |
| 2 | agent实时状态 | ✅ 6个agent状态正确 |
| 3 | 项目阶段/负责人/停留时长 | ✅ agg_project_flow可用 |
| 4 | 识别30min无动作/连续失败 | ⚠️ 告警表为空（collector已运行但未触发，可能阈值未达到） |
| 5 | 回放任务关键轨迹 | ❌ project_id为空，按项目回放不可用 |
| 6 | 数据与系统真实状态一致 | ✅ agent状态、项目状态已验证 |
| 7 | 部署到monitor.doramax.cn | ❌ 未部署 |

## 当前风险判断

- **核心数据采集链路**: 健康，6960条真实事件
- **API层**: 稳定，所有端点正常
- **数据完整性**: project_id缺失是唯一结构性问题，需Peter修复collector的项目关联逻辑
- **整体评估**: 已达到Conditional Pass标准，核心功能可用，项目回放需补全

---

*Guard | 2026-04-10 06:15*
