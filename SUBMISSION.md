# SUBMISSION.md — ai-team-observability V1.0

**提交者**: Peter  
**日期**: 2026-04-09 13:35  
**commit**: 67df601  
**分支**: main  
**GitHub**: https://github.com/ytfrank/ai-team-observability  

## 改动概要

### Phase 1: 数据采集 + API + Dashboard UI

**1. Event Collector** (`collector/collector.py`)
- 采集6个数据源：OpenClaw sessions、agent状态、项目status.json
- 写入SQLite：event_log + agg_agent_status + agg_project_flow + agg_model_usage + alerts
- 支持 `--once` 单次运行 和 常驻循环模式（默认60s间隔）

**2. API Server** (`api/api_server.py`)
- REST API：/api/agents, /api/projects, /api/events, /api/stats, /api/alerts
- 静态页面服务：/, /team/agents, /team/projects, /team/alerts
- 零依赖，纯Python标准库

**3. Dashboard UI** (`web/static/index.html`)
- 深色主题，30秒自动刷新
- Agent实时状态卡片（6个agent）
- 项目流转看板
- 统计概览（活跃agent数、项目数、24h事件/token数）

**4. 告警引擎** (`collector/alert_rules.py`)
- 3条规则：项目超时检测、Agent失联检测、阶段停滞检测

## 自测结果

| 测试项 | 结果 | 详情 |
|--------|------|------|
| Collector 单次运行 | ✅ | 采集6 agents, 4 projects |
| API /api/stats | ✅ | 返回正确统计数据 |
| API /api/agents | ✅ | 6个agent状态 |
| API /api/projects | ✅ | 4个项目信息 |
| Dashboard 页面 | ✅ | HTTP 200, 自动刷新正常 |
| GitHub push | ✅ | main分支已推送 |

## 改动文件

| 文件 | 说明 |
|------|------|
| collector/collector.py | 事件采集器（核心） |
| collector/alert_rules.py | 告警规则引擎 |
| api/api_server.py | REST API + 静态页面服务 |
| api/main.go | Go版API（未完成，Go未安装） |
| web/static/index.html | Dashboard主页 |
| web/static/agents.html | Agent详情页（占位） |
| web/static/projects.html | 项目详情页（占位） |
| web/static/alerts.html | 告警页（占位） |

## 风险

- Go未安装，API暂用Python实现（性能可接受）
- Collector 采集 session 文件目前为空（需配置OpenClaw session路径）
- 前端详情页尚未开发（Phase 2）
- 尚未部署到 monitor.doramax.cn

## 测试重点

1. Collector 是否正确采集 agent 和项目数据
2. API 返回数据是否准确
3. Dashboard 是否正常渲染
4. 告警规则是否触发

## 部署要求

- Python 3.10+
- 无额外依赖（纯标准库）
- SQLite 数据库自动创建
