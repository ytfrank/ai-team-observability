# TECH_PLAN.md — AI团队作战监控平台 V1.0

**作者**: Peter  
**日期**: 2026-04-08  
**状态**: 待确认

---

## 一、技术调研结论

### 1.1 候选方案评估

| 维度 | mudrii/openclaw-dashboard | Opik (comet-ml/opik) | ClawMetry |
|------|--------------------------|---------------------|-----------|
| **成熟度** | ✅ 可用，12面板，单Go二进制 | ✅ 成熟，MIT开源，Comet团队维护 | ❌ 未找到公开仓库，不可用 |
| **多agent支持** | ❌ 单agent视角，无团队/项目概念 | ⚠️ 支持multi-project tracing，但非OpenClaw原生 | N/A |
| **数据真实性** | ✅ 直接读OpenClaw gateway API + session文件 | ⚠️ 需要手动埋点，数据完整性依赖接入质量 | N/A |
| **部署复杂度** | ✅ 极低（单binary，零依赖） | ❌ 高（需Python后端 + PostgreSQL/ClickHouse + 前端） | N/A |
| **覆盖需求匹配度** | ~60%（缺项目流转、团队视角、告警规则） | ~40%（LLM tracing强，但团队/项目/告警弱） | 0% |
| **二次开发成本** | 中（Go + JS，代码清晰） | 高（全栈Python，集成层复杂） | N/A |

### 1.2 推荐路线：**mudrii/openclaw-dashboard 为基座 + 自研事件层**

**理由**：

1. **mudrii/openclaw-dashboard 已覆盖需求中~60%**：gateway健康、cost/token统计、session列表、cron状态、模型分布、子agent活动 — 这些它已经做好且质量不错。
2. **Opik过重**：我们需要的是团队作战指挥台，不是通用LLM tracing平台。Opik的span/tree模型适合调试单个LLM调用链，但不适合"8个agent谁在干啥"这种高层运营视图。且部署需要数据库+后端，对monitor.doramax.cn来说过重。
3. **ClawMetry不存在**：未找到任何公开仓库或npm/pip包，排除。
4. **自研从零起步性价比低**：mudrii的基座可用，在其上扩展团队视角比从头写高效得多。

**核心策略**：
- **保留** mudrii/dashboard 的运维面板（系统健康、cost、cron、session）作为"基础设施层"
- **新增** 三个自研模块作为"团队作战层"：Agent实时状态、项目流转、告警引擎
- **新增** 事件采集管道（collector），统一写入SQLite事件表

---

## 二、架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────┐
│              monitor.doramax.cn (Web)                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │
│  │ 运维面板  │ │Agent作战 │ │项目流转  │ │ 告警   │ │
│  │(mudrii)  │ │(自研)    │ │(自研)    │ │(自研)  │ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └───┬────┘ │
│       │            │            │            │      │
│       ▼            ▼            ▼            ▼      │
│  ┌─────────────────────────────────────────────┐    │
│  │           API Gateway (Go)                   │    │
│  │  /api/ops/*    /api/team/*   /api/alerts/*   │    │
│  └──┬─────────────────┬────────────────┬───────┘    │
│     │                 │                │             │
│     ▼                 ▼                ▼             │
│  ┌──────────┐  ┌──────────────┐  ┌──────────┐      │
│  │OpenClaw  │  │ SQLite       │  │ 告警引擎  │      │
│  │Gateway   │  │ event_log    │  │ (Go)     │      │
│  │API       │  │ + agg_*      │  │          │      │
│  └──────────┘  └──────┬───────┘  └──────────┘      │
│                       │                              │
└───────────────────────┼──────────────────────────────┘
                        ▲
               ┌────────┴────────┐
               │  Event Collector │
               │  (Python/Go)     │
               │                  │
               │  6个数据源:      │
               │  1. session文件  │
               │  2. agent日志    │
               │  3. A2A消息      │
               │  4. model usage  │
               │  5. 成果物扫描   │
               │  6. status.json  │
               └─────────────────┘
```

### 2.2 事件模型（event_log）

```sql
CREATE TABLE event_log (
    event_id      TEXT PRIMARY KEY,
    event_time    DATETIME NOT NULL,
    source_type   TEXT NOT NULL,  -- session_file/agent_log/a2a_log/model_usage/artifact_scan/status_json
    agent_name    TEXT NOT NULL,
    project_id    TEXT,
    event_category TEXT NOT NULL, -- lifecycle/llm/tool/a2a/project/stage/artifact/alert
    event_type    TEXT NOT NULL,
    severity      TEXT DEFAULT 'info',  -- info/warn/error/critical
    provider      TEXT,
    model         TEXT,
    input_tokens  INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    summary       TEXT,
    payload_json  TEXT
);

CREATE INDEX idx_event_time ON event_log(event_time);
CREATE INDEX idx_agent ON event_log(agent_name, event_time);
CREATE INDEX idx_project ON event_log(project_id, event_time);
CREATE INDEX idx_category ON event_log(event_category, event_time);
```

### 2.3 聚合表

```sql
-- Agent实时状态快照（collector每30s刷新）
CREATE TABLE agg_agent_status (
    agent_name       TEXT PRIMARY KEY,
    status           TEXT NOT NULL,  -- idle/running/waiting/blocked/failed
    current_project  TEXT,
    current_task     TEXT,
    current_stage    TEXT,
    current_model    TEXT,
    task_start_time  DATETIME,
    last_action_time DATETIME,
    last_a2a_time    DATETIME,
    last_5_actions   TEXT,  -- JSON array
    updated_at       DATETIME
);

-- 项目流转快照（collector每60s刷新）
CREATE TABLE agg_project_flow (
    project_id       TEXT PRIMARY KEY,
    current_stage    TEXT NOT NULL,
    stage_owner      TEXT,
    stage_enter_time DATETIME,
    total_elapsed_min INTEGER,
    is_overtime      BOOLEAN,
    latest_artifact  TEXT,
    block_reason     TEXT,
    stage_history    TEXT,  -- JSON array
    updated_at       DATETIME
);

-- 模型用量聚合（每小时rollup）
CREATE TABLE agg_model_usage (
    provider       TEXT,
    model          TEXT,
    period_start   DATETIME,
    period_type    TEXT,  -- hourly/daily
    request_count  INTEGER,
    input_tokens   INTEGER,
    output_tokens  INTEGER,
    by_agent       TEXT,  -- JSON {agent: count}
    PRIMARY KEY (provider, model, period_start, period_type)
);

-- 告警记录
CREATE TABLE alerts (
    alert_id     TEXT PRIMARY KEY,
    alert_time   DATETIME NOT NULL,
    alert_type   TEXT NOT NULL,
    severity     TEXT NOT NULL,  -- P1/P2
    agent_name   TEXT,
    project_id   TEXT,
    message      TEXT,
    notified     TEXT,  -- JSON array of notified agents
    acknowledged BOOLEAN DEFAULT FALSE,
    resolved_at  DATETIME
);
```

### 2.4 Collector 设计

**运行方式**：cron每分钟执行一次（或作为常驻进程）

**采集逻辑**：
```
1. 扫描 ~/.openclaw/agents/*/sessions/ → 解析最新session → 提取agent状态/模型/token
2. 读取各项目 monitor/*/status.json → 更新agg_project_flow
3. 解析A2A消息 → 更新agent间通信时间
4. 聚合token数据 → 写入agg_model_usage
5. 扫描成果物目录 → 检查是否已群通知
6. 运行告警规则 → 触发告警
```

**技术选型**：Python脚本，因为：
- 需要解析JSONL session文件（Python处理文本极方便）
- 复用openclaw已有的Python生态（codexbar等）
- 轻量，无额外依赖

### 2.5 前端新增页面

在mudrii/dashboard的Go HTTP server上新增路由：

| 路由 | 页面 | 数据源 |
|------|------|-------|
| `/team/agents` | Agent作战矩阵 | `agg_agent_status` |
| `/team/projects` | 项目流转看板 | `agg_project_flow` |
| `/team/alerts` | 告警中心 | `alerts` |

前端：纯HTML/CSS/JS（与mudrii保持一致的风格），无框架。

---

## 三、任务拆分与Sub-Agent编排

### 3.1 编排包：normal

预计3个sub-agent并行 + 1个串行verify。

### 3.2 任务分工

| # | Agent | 任务 | 依赖 | 预估 |
|---|-------|------|------|------|
| 1 | **Backend Dev** | Collector脚本 + SQLite schema + API endpoints（Go） | 无 | 2h |
| 2 | **Frontend Dev** | 3个新页面（Agent作战/项目流转/告警中心） | API spec确定 | 2h |
| 3 | **Test Writer** | Collector单元测试 + API测试 + 聚合逻辑测试 | schema确定 | 1.5h |
| 4 | **Verify Runner** | 编译检查 + lint + 全量测试 | 1+2+3完成 | 0.5h |

### 3.3 执行顺序

```
Phase 1（并行）:
  ├── Test Writer: 写collector/parser/aggregation的测试
  ├── Backend Dev: collector + schema + API
  └── Frontend Dev: 页面骨架 + mock数据

Phase 2（串行）:
  └── 前后端联调 → Verify Runner → Code Review

Phase 3:
  └── 部署到 monitor.doramax.cn
```

### 3.4 开发周期

| 阶段 | 时长 | 说明 |
|------|------|------|
| Phase 1 并行开发 | 2h | 3个agent同时开工 |
| Phase 2 联调+验证 | 1h | 接口对接 + test + review |
| Phase 3 部署 | 0.5h | Atlas负责 |
| **总计** | **3.5h** | AI节奏，无人类buffer |

**注意**：这是纯AI开发节奏。如果中途需要波哥/小叮当确认设计细节，时间会延长。

---

## 四、技术风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| session JSONL格式不稳定 | collector解析失败 | 写 resilient parser，跳过格式异常的行 |
| mudrii/dashboard Go代码耦合度高 | 二次开发困难 | 先读源码评估，必要时独立部署自研部分 |
| SQLite并发写入 | 数据竞争 | 单writer模式（collector独占写） |
| 告警通知通道 | P1告警无法及时送达 | 复用飞书群 + @成员 |

---

## 五、下一步

1. 小叮当 + Guard 确认技术方案
2. 确认后 Peter 立刻启动 Phase 1 并行开发
3. Atlas 同步准备部署环境（monitor.doramax.cn + Cloudflare Tunnel）

---

*Peter | 2026-04-08*
