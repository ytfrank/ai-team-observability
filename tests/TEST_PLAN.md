# TEST_PLAN.md — ai-team-observability V1.0

**测试负责人**: Guard  
**日期**: 2026-04-10 04:10  
**风险等级**: medium  
**对应commit**: fd33aa7 / 67df601  
**测试矩阵**: normal（api + ui_flow + logs_config + regression）

---

## 一、测试范围

### 改动点
1. **Event Collector** (`collector/collector.py`) — 6数据源采集，写入SQLite
2. **API Server** (`api/api_server.py`) — REST API + 静态页面服务
3. **Dashboard UI** (`web/static/index.html`) — 深色主题，30s自动刷新
4. **告警规则** (`collector/alert_rules.py`) — 注：文件不存在，集成在collector.py中

### 不测
- Go版API（未完成）
- 前端详情页（占位）
- 部署到 monitor.doramax.cn（Atlas负责）

---

## 二、测试场景

### 2.1 API测试（核心）
| # | 场景 | 操作 | 校验点 |
|---|------|------|--------|
| 1 | Collector运行 | `python3 collector.py --once` | 无报错，SQLite生成，表创建正确 |
| 2 | /api/stats | GET请求 | 返回JSON，含active_agents/projects/events_24h/tokens_24h |
| 3 | /api/agents | GET请求 | 返回agent数组，每个含name/status/last_action |
| 4 | /api/projects | GET请求 | 返回项目数组，每个含id/stage/owner |
| 5 | /api/events | GET请求 | 返回事件列表 |
| 6 | /api/alerts | GET请求 | 返回告警列表 |
| 7 | API错误路径 | 访问不存在的路由 | 返回404 |

### 2.2 UI/Dashboard测试
| # | 场景 | 操作 | 校验点 |
|---|------|------|--------|
| 8 | Dashboard主页 | GET / | HTTP 200, HTML渲染 |
| 9 | 静态页面 | GET /team/agents, /team/projects, /team/alerts | HTTP 200 |
| 10 | 自动刷新 | 检查index.html源码 | 含30s定时刷新逻辑 |

### 2.3 数据有效性测试
| # | 场景 | 操作 | 校验点 |
|---|------|------|--------|
| 11 | 数据真实性 | Collector采集后检查SQLite | agent状态与实际OpenClaw状态一致 |
| 12 | 空数据处理 | 清空数据后启动API | 不崩溃，返回空数组 |

### 2.4 回归/健壮性
| # | 场景 | 操作 | 校验点 |
|---|------|------|--------|
| 13 | Collector重复运行 | --once连续跑两次 | 不报错，数据更新 |
| 14 | API无Collector | 不跑Collector直接启动API | 不崩溃 |

---

## 三、测试分工

全部由Guard亲自执行（项目规模小，Python纯标准库，编排成本>执行成本）。

## 四、测试方法

- Collector: 直接运行 `python3 collector.py --once`
- API: 启动 `python3 api_server.py`，用 `curl` 测试各端点
- UI: `curl` 检查HTTP状态码 + 关键HTML元素
- 数据: `sqlite3` 查询验证

## 五、未覆盖项

- 真实浏览器渲染（无headless browser环境）
- 告警通知通道（飞书集成未实现）
- 并发压测
- monitor.doramax.cn线上部署验证

## 六、ETA

**预计25分钟内完成**（含执行+报告输出）
