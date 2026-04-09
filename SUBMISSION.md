# SUBMISSION.md — ai-team-observability V1.0

**提交者**: Peter  
**日期**: 2026-04-09 13:15  
**commit**: 67df601  
**分支**: main  

## 改动概要

### Phase 1: 数据采集 + API + Dashboard

1. **Event Collector** (`collector/collector.py`)
   - 扫描 OpenClaw session 文件、agent workspace、project status.json
   - 写入 SQLite event_log + 4张聚合表
   - 支持 `--once` 单次采集 和 持续循环模式

2. **API Server** (`api/api_server.py`)
   - `/api/agents` — 6个agent实时状态
   - `/api/projects` — 项目流转状态
   - `/api/events` — 事件流（支持按agent/category过滤）
   - `/api/stats` — 总览统计（活跃agent数、项目数、24h事件/token）
   - `/api/alerts` — 告警列表

3. **Dashboard UI** (`web/static/index.html`)
   - 深色主题，30s自动刷新
   - Agent卡片矩阵（状态/项目/任务/最后活动）
   - 项目流转列表（阶段/owner/阻塞原因）
   - 统计概览（4个指标卡）

4. **告警引擎**
   - 项目超时检测（>30min未更新）
   - Agent失联检测（>1h无活动）
   - 阻塞项检测

## 自测结果

| 测试项 | 结果 | 详情 |
|--------|------|------|
| Collector 单次采集 | ✅ | 6 agents, 4 projects |
| API /api/agents | ✅ | 返回6个agent状态 |
| API /api/projects | ✅ | 返回4个项目 |
| API /api/stats | ✅ | agents:6/3active, projects:4 |
| Dashboard 页面加载 | ✅ | HTTP 200 |

## 技术调整

- **原方案**: Go API server（mudrii/dashboard基座）
- **实际方案**: Python API server（Go未安装，后续可切换）
- **原因**: 快速交付优先，功能等价

## 已知限制

- Session文件解析暂未采集到token详情（需JSONL格式稳定后完善）
- 前端3个详情页（agents/projects/alerts）为占位页，待Phase 2完善
- 告警通知暂未接入飞书（仅写DB）
- 部署环境未配置（monitor.doramax.cn + Cloudflare Tunnel）

## 下一步

- Phase 2: 前端3个详情页完善
- 部署到 monitor.doramax.cn
- 告警接入飞书群通知
