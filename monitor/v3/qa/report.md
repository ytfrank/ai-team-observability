# 测试报告 — ai-team-observability V3-A

- **测试时间**: 2026-04-20 10:06 ~ 10:18
- **测试负责人**: Guard
- **对应commit**: dc11786 + 77eea7d
- **风险等级**: medium

---

## 测试结论: ✅ **Conditional Pass**

---

## 已验证

### API 测试 (7/7 通过)

| # | 测试项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | GET /api/stats | ✅ | agents=6(active=1), projects=6(blocked=1), events_24h=3570, tokens_24h 有值 |
| 2 | GET /api/projects | ✅ | 返回6条记录，V3 含 base_project/version 元数据 |
| 3 | GET /api/projects?grouped=1 | ✅ | ai-team-observability 2版本聚合, voice-bridge 3版本聚合, active_version 正确 |
| 4 | GET /api/artifacts?project_id=ai-team-observability-v3 | ✅ | 返回成果物列表，含 preview_type(download_url/preview_url) |
| 5 | GET /api/artifact (MD文件) | ✅ | SUBMISSION.md 内容正常返回 |
| 6 | GET /api/artifact (path traversal /etc/passwd) | ✅ | 返回 403 {"error":"forbidden path"} |
| 7 | GET /api/alerts | ✅ | HTTP 200，返回 []（无活跃告警，符合预期） |

### UI 测试 (4/4 通过)

| # | 测试项 | 结果 | 证据 |
|---|--------|------|------|
| 8 | GET / (dashboard) | ✅ HTTP 200 | HTML 返回完整，含 </html> 闭合 |
| 9 | GET /team/projects | ✅ HTTP 200 | 项目页面正常 |
| 10 | GET /team/alerts | ✅ HTTP 200 | 告警页面正常 |
| 11 | GET /nonexistent | ✅ HTTP 404 | 正确返回 404 |

### 数据准确性 (2/2 通过)

| # | 测试项 | 结果 | 证据 |
|---|--------|------|------|
| 12 | 版本隔离 | ✅ | V1(deployed) 与 V3(testing) 数据独立，base_project 聚合正确 |
| 13 | 单元测试 6/6 | ✅ | 全部通过（0.035s） |

### 回归测试 (2/2 通过)

| # | 测试项 | 结果 | 证据 |
|---|--------|------|------|
| 14 | Collector --once 运行 | ✅ | 采集 1234 events, 3 projects, RC=0 |
| 15 | API 依赖 DB 已有数据 | ✅ | 启动后所有端点正常 |

---

## 未验证

| 项 | 原因 | 风险 |
|----|------|------|
| 成果物图片/MP4预览 | 需真实文件 + 浏览器 | 低（代码逻辑与MD相同路径） |
| 浏览器真实渲染 | 无 headless browser 环境 | 中（需线上验收） |
| /team/agents 详情页 | 页面显示"建设中" | 已知（V3-A 不含） |
| Collector 定时刷新 | 未配置 cron | 低（手动 --once 正常） |

---

## 发现的问题

### P2（不阻塞）
1. **V1 记录 lifecycle=None, project_name=null**: 老版本 status.json 缺少新版字段，前端需 fallback 处理（当前已正常）
2. **空项目记录（base_project=""）**: DB 中存在一条空记录，可能是 collector 采集异常数据

---

## 风险评估

- **核心功能（P0-1/2/3）**: 全部通过，数据隔离准确，分组正确，成果物可访问
- **安全性**: path traversal 防护有效
- **回归**: 无新增 break
- **数据新鲜度**: Collector 需手动触发或配置定时，当前不影响功能正确性

## 放行建议

**Conditional Pass** — V3-A 核心功能验证通过，可推进验收。建议：
1. 小叮当线上验收时确认浏览器端渲染
2. Atlas 部署后确认公网访问
3. P2 问题（空记录、V1字段缺失）后续迭代修复

---

*Guard | 2026-04-20 10:18*
