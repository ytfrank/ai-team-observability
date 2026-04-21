# TEST_PLAN.md — ai-team-observability V4

- 测试时间：2026-04-20 21:05+
- 提测 commit：9de996ec7f0179d337172e3554860be7797ecc19
- 风险等级：**中**（3个P0功能新增 + 安全回归）
- 测试矩阵：**normal**

---

## 测试范围

### P0-1: Agent详情页（/team/agents）
- Agent列表加载（/api/agents 返回数据）
- 点击Agent → 详情展示：timeline / sub-agents / A2A / heatmap
- 时间范围筛选（today / 7d / custom）
- 热力图数据正确（7×24=168个bucket）

### P0-2: Dashboard跳转（index.html）
- agents卡片 → /team/agents
- projects卡片 → /team/projects
- events卡片 → /team/agents#recent-events
- blocked卡片 → /team/projects?filter=blocked
- 趋势指标展示（up/down/flat）

### P0-3: 成果物独立页面（/team/artifacts）
- 独立页面加载
- 按阶段分组（requirements → dev → qa → acceptance → deploy → handoffs）
- 组内时间倒序
- 搜索筛选
- 预览（inline）
- 下载

### 回归：Path Traversal
- `/api/artifact?path=/etc/passwd` → 403
- 合法路径 → 200

## 测试策略

本轮为 **API + 静态页面 + 安全回归** 测试。

线上服务当前530（可能tunnel未连或本地服务未启），优先：
1. **API单元测试**（已有11个，确认通过）
2. **本地服务启动 + API集成测试**（curl验证所有端点）
3. **浏览器E2E**（如服务可启，截图验证页面渲染）
4. **Path traversal回归**

### 测试分工

| 测试项 | 执行者 | 状态 |
|--------|--------|------|
| API单元测试 | Guard主线程 | ✅ 11/11通过 |
| API集成测试（curl） | Guard主线程 | 🟡 进行中 |
| Path Traversal回归 | Guard主线程 | 🟡 待执行 |
| 浏览器E2E页面渲染 | 降级/视服务状态 | 🟡 待评估 |

### ETA
- T+10: 测试方案（本文件）
- T+25: API集成测试完成
- T+30: 第一轮结果

---

*Guard | 2026-04-20 21:10*
