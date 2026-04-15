# TECH_PLAN.md — ai-team-observability V3

- 项目: ai-team-observability
- 版本: V3
- 日期: 2026-04-15
- 负责人: Peter
- 当前分支: v3

## 一、目标

基于 V2 现有代码迭代，完成 V3 的三类核心改进：
1. 数据准确性修复，确保项目/版本状态不混淆
2. 项目页与成果物能力补齐，支持按版本查看与预览/下载
3. 补齐关键可视化与告警能力的第一版可用实现

## 二、范围

### P0 本轮优先
1. Collector 版本隔离与项目数据准确性
2. 项目列表按主项目聚合，版本分组展示
3. 成果物索引、预览、下载

### P1 本轮尽量完成
1. Agent 事件图表化第一版
2. Token 趋势图第一版
3. 告警中心从占位页改为可用页

## 三、改动文件

- `collector/collector.py`
- `api/api_server.py`
- `web/static/index.html`
- `web/static/projects.html`
- `web/static/agents.html`
- `web/static/alerts.html`
- `tests/*`（补充或更新验证）
- `monitor/v3/dev/SUBMISSION.md`

## 四、技术方案

### 1. 数据层
- 扫描 `~/projects/*/monitor/*/status.json` 时，使用 `project + version` 形成稳定 project_id
- 从 status.json 中提取当前版本路径、阶段、负责人、工件信息
- 为项目聚合增加主项目名与版本字段，避免 V1/V2/V3 混淆
- 增加成果物索引逻辑，扫描 `monitor/v3/` 下各阶段文件

### 2. API 层
- `/api/projects` 返回主项目、版本、阶段、风险、更新时间
- 新增成果物相关接口：
  - `/api/artifacts`
  - `/api/artifact?path=...`
- 为图表页补充聚合接口，支撑趋势与分组展示

### 3. 前端层
- 项目页从“建设中”改为真实项目列表
- 增加版本分组卡片、展开/收起、活跃版本高亮
- 成果物支持 Markdown 预览、图片预览、视频播放、文件下载
- Alerts 页从占位状态升级为可浏览列表

## 五、拆分与编排

- 本次是否拆分: 是
- 计划启动 subagents: 3
  - Test Writer: 先补接口/页面行为测试点
  - Backend Dev: collector + API
  - Frontend Dev: 项目页/告警页/成果物预览
- 当前主线程动作: 先补 TECH_PLAN，随后进入实现

## 六、验收标准

1. `monitor/v3/dev/` 下形成完整开发工件
2. `/api/projects` 不再混淆不同版本项目
3. 项目页可看到版本分组与活跃版本
4. 成果物可预览、可下载
5. 告警页不再是“建设中”
6. 关键改动有对应自测记录

## 七、风险

1. 现有 SQLite 聚合结构偏薄，可能需要增补字段
2. 前端当前是静态页，交互要控制复杂度
3. 成果物预览需注意路径安全与文件类型判断

## 八、预计节奏

- TECH_PLAN: 已补齐
- 第一批代码改动: 今天下午
- 第一版提测包: 今天内
