# REQUIREMENTS.md — AI团队作战监控平台 V1.0

## 项目信息

- **项目名**：ai-team-observability
- **版本**：V1.0
- **发起人**：波哥
- **需求Owner**：小叮当
- **实施Owner**：Atlas
- **数据接入Owner**：Peter
- **规则与验收Owner**：Guard
- **创建时间**：2026-04-08 19:16
- **状态**：需求确认中

---

## 一、背景

当前AI团队（8个agent）的运行状态基本是黑盒：
- 不知道各agent在干什么、干了多久、卡在哪
- 不知道模型额度还剩多少、什么时候会爆
- 不知道项目卡在哪个阶段、谁在等谁
- 不知道哪些SOP/skill在反复出问题

**缺乏数据 → 无法分析 → 无法改进。** 这是当前团队效率提升的最大瓶颈之一。

之前尝试过 tugcantopaloglu/openclaw-dashboard，但该方案对多agent team支持不足，数据不真实。需要重新规划。

---

## 二、项目目标

构建「AI团队作战指挥台」，不是传统运维大盘。

核心回答4个问题：
1. **资源够不够用？** — 额度/调用趋势
2. **谁在干啥、卡没卡？** — agent实时状态
3. **项目卡在哪、为什么慢？** — 流转监控
4. **哪里可以优化？** — 审计与归因

**核心原则**：
- 从"财务视角"切换到"运营视角+作战视角+审计视角"
- 数据必须真实有效，宁可不展示也不要虚假数据
- 第一版追求"有用"，不追求"完美"

---

## 三、第一版范围（3个核心视图 + 基础告警）

### 视图1：模型额度与调用量

参考智谱"用量统计"页面风格。

**每个Provider一张卡片**（OpenAI / Claude / 智谱 / 本地模型）：
- 5小时额度使用百分比 + 重置时间
- 周额度使用百分比 + 重置时间
- 最近24小时请求数和token数
- 最近7天/30天趋势柱状图
- 按agent分布、按项目分布
- rate limit / context overflow 事件标记
- 健康状态：正常 / 关注 / 紧张 / 需切换

### 视图2：Agent实时作战

**Agent列表**，每个agent显示：
- 当前状态（idle / running / waiting / blocked / failed）
- 当前项目、任务、阶段
- 当前使用模型
- 任务开始时间 + 已持续时长
- 最近一次动作时间
- 最近一次A2A收发时间
- 最近5条动作摘要

**颜色标记**：
- 🟢 正常推进
- 🟡 长时间无新动作（>30min）
- 🔴 报错/超时/阻塞
- 🔵 等待下游/等人确认

**可点击**进入agent详情页，查看session轨迹。

### 视图3：项目流转

**项目列表**，每个项目显示：
- 当前阶段（需求→开发→测试→验收→部署→完成）
- 当前负责人agent
- 当前阶段停留时长 + 总耗时
- 是否超时（红线：超12h警告，超24h升级）
- 最新成果物
- 当前阻塞原因

**可点击**查看阶段时间线：
- 每个阶段的进入/离开时间、负责人、产物
- 是否被打回、打回原因、重试次数

### 告警规则（第一版）

**P1（必须尽快处理）**：
| 告警 | 触发条件 | 通知对象 |
|------|---------|---------|
| Agent长时间无动作 | status=running 且超30min无新event | 小叮当、Atlas |
| 项目阶段超SLA | 某阶段停留超规范时限 | 小叮当、当前owner |
| 模型连续rate limit | 10min内同provider连续≥3次rate limit | Atlas、小叮当 |
| 必备成果物缺失 | 阶段切换时required artifact不齐 | Guard、当前owner |

**P2（需要关注）**：
| 告警 | 触发条件 | 通知对象 |
|------|---------|---------|
| Agent连续重试 | 同任务retry≥3 | Atlas、Peter |
| 工具调用失败率高 | 某tool/skill 1h失败率>30% | Peter、Atlas |
| 成果物未群通知 | 成果物创建后10min未发群通知 | Guard、owner |

---

## 四、数据采集方案

采用「事件流 + 聚合表」架构，不直接从session文件硬拼页面。

### 统一事件模型（event_log）

| 字段 | 说明 |
|------|------|
| event_id | 唯一ID |
| event_time | 事件时间 |
| source_type | 来源（session_file / agent_log / a2a_log / skill_log / artifact_scan） |
| agent_name | 触发agent |
| project_id | 所属项目 |
| event_category | 大类（lifecycle / llm / tool / a2a / project / stage / artifact / alert） |
| event_type | 具体类型 |
| severity | 严重度 |
| provider / model | 模型信息 |
| input_tokens / output_tokens | token信息 |
| summary | 摘要 |
| payload_json | 扩展字段 |

### 第一版采集6类数据源

1. `~/.openclaw/agents/*/sessions` — session记录
2. agent运行日志
3. A2A消息记录
4. 模型调用usage/error信息
5. 成果物目录扫描
6. 项目status.json

---

## 五、技术路线（待Peter调研确认）

**优先级排序**：
1. **ClawMetry** — OpenClaw原生观测工具，号称零配置、自动检测多agent、覆盖token/cost/cron/sub-agent/session。优先验证。
2. **Opik + opik-openclaw** — 强tracing能力（LLM spans / sub-agent spans / tool spans），适合长期observability主线。
3. **mudrii/openclaw-dashboard** — 轻量备选。
4. 前三个都不满足时，再考虑自研。

**Peter需调研并输出**：
- 各方案的适配度评估（多agent支持、数据真实性、部署复杂度）
- 推荐技术路线
- 架构设计
- 任务分工和sub-agent编排
- 开发周期估计（AI节奏，不要按人类节奏估buffer）

---

## 六、项目分工

| 角色 | 成员 | 职责 |
|------|------|------|
| 需求owner + 最终验收 | 小叮当 | 定需求、定验收标准、核证交付 |
| 实施owner | Atlas | 平台架构、数据采集、页面、告警、部署 |
| 数据接入owner | Peter | session/A2A/skill埋点、collector、parser |
| 规则与验收owner | Guard | 验收标准、成果物规则、审计规则、告警阈值 |

---

## 七、验收标准（第一版）

1. ✅ 能看到多provider最近5h/7d调用和token趋势
2. ✅ 能实时看到每个agent当前状态、任务、最近动作
3. ✅ 能看到项目当前阶段、负责人、停留时长
4. ✅ 能识别出"30分钟无动作"和"连续失败"
5. ✅ 能回放一个任务的关键轨迹（谁接的→做了什么→何时交接）
6. ✅ 所有展示数据必须与系统真实状态一致
7. ✅ 部署到 monitor.doramax.cn，波哥可线上确认

---

## 八、部署信息

- 域名：monitor.doramax.cn
- 已有Cloudflare Tunnel配置（token已提供）
- 需清理过期的localhost:3001等服务

---

## 九、非目标（第一版不做）

- 伪精确cost计算（展示token和调用量即可）
- 复杂的权限管理
- 完整的配置中心页面
- Skill成功率深度分析（P3阶段再做）
- Spec/SOP卡点自动归因（P3阶段再做）

---

*创建时间：2026-04-08 19:16 | 需求Owner：小叮当*
