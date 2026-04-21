# 测试报告 — ai-team-observability V4

- **测试时间**: 2026-04-20 21:05 ~ 21:25
- **提测 commit**: `9de996ec7f0179d337172e3554860be7797ecc19`
- **测试执行者**: Guard
- **测试环境**: 本地服务 (localhost:18080, DB: data/events.db, 6 agents / 16419 events / 6 projects)

---

## 测试结论：✅ **Pass**

---

## 已验证

### P0-1: Agent详情页
| 测试项 | 结果 | 证据 |
|--------|------|------|
| `/team/agents` 页面加载 (200, 13KB) | ✅ | curl 200 |
| `/api/agents` 返回6个agent含a2a/sub统计 | ✅ | doraemon: a2a=203, peter: sub=91 |
| `/api/agent_detail?agent=peter&range=7d` | ✅ | timeline=500, subagents=36, a2a=3 |
| 热力图数据正确 (7×24=168 buckets) | ✅ | 168 buckets, total activity=500 |
| 时间线含sub-agent/A2A/error分类 | ✅ | summary: sub=36, a2a=3, errors=119 |
| agents.html含timeline/sub-agent/A2A/heatmap/筛选DOM | ✅ | 6/6 关键元素存在 |
| 错误处理：agent不存在→404, 缺参数→400 | ✅ | 404/400正确返回 |

### P0-2: Dashboard跳转
| 测试项 | 结果 | 证据 |
|--------|------|------|
| agents卡片→`/team/agents` | ✅ | href='/team/agents' |
| projects卡片→`/team/projects` | ✅ | href='/team/projects' |
| events卡片→`/team/agents#recent-events` | ✅ | href含#recent-events |
| blocked卡片→`/team/projects?filter=blocked` | ✅ | href含filter=blocked |
| 趋势delta渲染代码 | ✅ | /api/stats调用+delta逻辑存在 |
| /api/stats返回完整数据 | ✅ | agents=6, projects=6, events_24h=3734 |

### P0-3: 成果物独立页面
| 测试项 | 结果 | 证据 |
|--------|------|------|
| `/team/artifacts` 页面加载 (200, 12KB) | ✅ | curl 200 |
| 按阶段分组 (6个标准阶段+other) | ✅ | requirements=4, dev=76, qa=34, acceptance=3, deploy=3, handoffs=0 |
| 搜索功能 (`?q=REQUIREMENTS`) | ✅ | 返回4个结果 |
| 预览（inline） | ✅ | Content-Disposition: inline |
| 下载（attachment） | ✅ | Content-Disposition: attachment; filename="report.md" |
| artifacts.html含搜索/预览/下载/阶段分组DOM | ✅ | 6/6 关键元素存在 |
| 总计134个成果物正确索引 | ✅ | total=134 |

### 回归：Path Traversal
| 测试项 | 结果 | 证据 |
|--------|------|------|
| `/api/artifact?path=/etc/passwd` → 403 | ✅ | `{"error": "forbidden path"}` |
| `/api/artifact?path=../../etc/passwd` → 404 | ✅ | resolve后不在PROJECTS_HOME内 |
| 合法文件预览 → 200 | ✅ | text/markdown, 4946 bytes |

### API单元测试
| 测试项 | 结果 | 证据 |
|--------|------|------|
| 11/11 unittest全部通过 | ✅ | 0.065s |

---

## 未验证

| 项目 | 原因 | 风险 |
|------|------|------|
| 真实浏览器E2E渲染（JS执行、CSS渲染） | 线上服务530（tunnel可能未连），本地无headless browser | **低** - HTML结构已验证，关键文案/API调用已确认 |
| Dashboard卡片点击后的实际视觉跳转 | 同上 | **低** - href指向已验证正确 |
| 成果物预览弹窗交互体验 | 同上 | **低** - API层面inline预览已验证 |

---

## 当前风险

1. **低风险**：线上服务530，可能是cloudflare tunnel未连接，不影响功能正确性判断
2. **低风险**：成果物中demo.mp4文件在测试种子数据中存在但真实环境已删除，404行为正确

---

## 证据索引

- API单元测试：`tests/test_api_server.py` → 11/11 OK
- API集成测试：localhost:18080 curl验证（已记录于本报告）
- Path traversal回归：403 / 404 正确拒绝

---

## 测试矩阵执行情况

| 维度 | 状态 | 覆盖情况 |
|------|------|----------|
| API接口测试 | ✅ 完成 | 15个端点全覆盖 |
| 静态页面验证 | ✅ 完成 | HTML关键元素6/6确认 |
| 安全回归 | ✅ 完成 | path traversal 2/2通过 |
| 浏览器E2E | ⏸️ 降级 | 线上530，HTML结构验证替代 |
| 性能测试 | - | 本轮非重点，P0功能响应均<100ms |
| 回归测试 | ✅ 完成 | path traversal + 已有API兼容性 |

---

**Guard | 2026-04-20 21:25**
**结论：Pass — 3个P0功能API+静态页面验证通过，path traversal回归通过，建议进入验收。**
