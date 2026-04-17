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

## 三、计划改动文件

- `collector/collector.py`
- `api/api_server.py`
- `web/static/index.html`
- `web/static/projects.html`
- `web/static/agents.html`
- `web/static/alerts.html`
- `tests/*`（补充或更新验证）

## 四、当前实际进展（2026-04-16 11:20 更新）

### 已落地代码
- `api/api_server.py`
- `web/static/alerts.html`
- `tests/test_api_server.py`

### 尚未落地
- `collector/collector.py` 的版本隔离收口
- `web/static/projects.html` 的版本分组
- 成果物预览/下载相关接口与页面

### 计划 vs 实际偏差
- `TECH_PLAN` 规划了 3 个 sub-agent 并行推进
- 实际未形成可审计的 sub-agent 启动/结束留痕
- 当前实际推进方式是主线程直接收口了 alerts API、alerts 页面和局部单测
- 因此当前阶段尚未达到原计划的并行开发效果，也未满足提测条件

## 五、技术方案

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

## 六、拆分与编排

- 本次是否拆分: 是
- 原计划启动 subagents: 3
  - Test Writer: 先补接口/页面行为测试点
  - Backend Dev: collector + API
  - Frontend Dev: 项目页/告警页/成果物预览
- 实际已启动 subagents: 0
- 当前活跃 subagents: 0
- 当前判断: 原方案在任务结构上仍然成立，当前问题是执行未落地，不应把“未执行编排”直接等同于“无需编排”
- 流程问题:
  1. 已产出 TECH_PLAN，但未触发真实 sub-agent，方案停留在文档层
  2. 主线程在未做方案变更留痕的情况下，直接推进局部实现，造成执行方式与技术方案不一致
  3. `SUBMISSION.md` 曾以骨架形式提前出现，后又删除，说明阶段门槛控制失效，易误导 PMO / 心跳系统对提测成熟度的判断
  4. `status.json` 的官方摘要、runtime 记录与仓库事实未完全同步，导致 developing 状态下出现“已恢复推进”与“无真实开发执行证据”并存的失真
  5. 缺少 sub-agent 启动、结束、产出、失败原因等可审计留痕，导致异常只能在事后通过仓库事实倒查
- 修正动作:
  1. 先补流程校正，不直接推翻原编排方案；如需改为缩编排或主线程收口，必须先更新 TECH_PLAN 并写明变更理由
  2. 在继续开发前，明确本轮是否维持 3-agent 并行，或调整为更小的编排包，并同步留痕到本文件
  3. 未满足提测条件前，不创建或保留 `SUBMISSION.md`
  4. 后续任何实现开始前，必须先记录 sub-agent 启动时间、职责、输入范围、验收标准；结束时记录产出与验证结果
  5. 将“方案已写但未执行”“成果物提前创建”“状态源未同步”视为流程异常，而非普通开发延迟

## 七、验收标准

1. `monitor/v3/dev/` 下形成完整开发工件
2. `/api/projects` 不再混淆不同版本项目
3. 项目页可看到版本分组与活跃版本
4. 成果物可预览、可下载
5. 告警页不再是“建设中”
6. 关键改动有对应自测记录

## 八、风险

1. 现有 SQLite 聚合结构偏薄，可能需要增补字段
2. 前端当前是静态页，交互要控制复杂度
3. 成果物预览需注意路径安全与文件类型判断

## 九、预计节奏

- TECH_PLAN: 已补齐
- 第一批代码改动: 今天下午
- 第一版提测包: 今天内
