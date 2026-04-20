# SUBMISSION.md — ai-team-observability V3

- 项目: ai-team-observability
- 版本: V3
- 当前阶段: developing（收口中，尚未正式提测）
- 负责人: Peter
- 当前分支: v3
- 最新开发 commit: `8eead33b8ae04c4b282ffeefc3c2c2d4228e0008`
- 更新时间: 2026-04-18 00:46 +0800

## 1. 本轮已完成

### P0-1 Collector 版本隔离与数据准确性
- 修正 collector 的 `status.json` 扫描与 project/version 归一化逻辑
- 为 `agg_project_flow` 增补 `base_project` / `version` / `artifact_root` 等字段
- `/api/projects` 已能返回版本维度元数据，避免 V1/V2/V3 混淆

### P0-2 项目列表版本分组
- 首页与项目页已支持按主项目聚合版本
- 活跃版本置顶/高亮，归档版本灰显
- `/team/projects` 页面已接入成果物侧栏主框架

### 已完成的 P1 子项
- 告警中心页面 `/team/alerts` 已从占位页改为真实列表页
- `/api/alerts` 已接通，支持按时间倒序展示最近告警

## 2. 当前进行中

### P0-3 成果物预览与下载
- `/api/artifacts` 与 `/api/artifact` 已接通
- Markdown / 图片 / 视频 / 文本预览框架已落地
- 正在做真实项目数据联调与细节收口，确保不同文件类型、路径安全、下载行为都稳定

### 剩余 P1
- Agent 事件图表化
- Token 使用趋势图

## 3. 自测记录

已完成：
- `python3 -m unittest -q tests/test_api_server.py` ✅
- 接口级联调抽查：
  - `/api/projects?grouped=1` ✅
  - `/api/artifacts?project_id=ai-team-observability-v3` ✅
  - `/api/alerts?limit=10` ✅

未完成：
- 基于真实仓库数据的完整页面回归
- P0-3 全链路手工冒烟
- P1 图表功能自测

## 4. 当前风险

- 成果物预览需继续验证多文件类型与边界路径
- P1 图表功能尚未开始收口，当前还不能提测 V3 全量范围
- `TECH_PLAN.md` 仍有未提交更新，需要与后续开发事实一起落盘

## 5. 测试重点（后续正式提测时）

1. `/api/projects` 是否彻底消除不同版本数据混淆
2. `/team/projects` 分组、活跃版本高亮、归档版本灰显是否正确
3. 成果物 Markdown / 图片 / MP4 / 下载行为是否稳定
4. 告警中心列表、级别统计、空状态展示是否正常
5. 后续补齐的事件图与 Token 趋势图是否与 collector 数据一致

## 6. 结论

- 当前已形成有效开发基线，但**尚未达到正式提测门槛**
- 待 P0-3 收口完成，并补足剩余 P1 功能与完整自测后，再更新为正式提测版本并移交 Guard
