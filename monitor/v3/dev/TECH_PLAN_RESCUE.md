# TECH_PLAN_RESCUE.md — 小叮当接手V3开发方案

- 项目: ai-team-observability
- 版本: V3
- 日期: 2026-04-20
- 负责人: 小叮当（PMO rescue 接手）
- 当前分支: v3
- 基线 commit: d48c213

## 一、接手决策

**继续开发，不推翻重来。**

理由：
1. collector.py（441行）+ api_server.py（350行）代码质量可用，结构清晰
2. P0-1（版本隔离）和 P0-2（项目分组）已实现并自测通过
3. P0-3（成果物预览）API 框架已有，缺前端联调收口
4. 推翻重来只会浪费时间，无质量收益

## 二、交付范围（V3-A，不扩大）

| # | 任务 | 状态 | 预估 |
|---|------|------|------|
| P0-1 | Collector 版本隔离 | ✅ 已完成 | 0 |
| P0-2 | 项目列表版本分组 | ✅ 已完成 | 0 |
| P0-3 | 成果物预览与下载 | 🔧 进行中（80%） | 30min |
| 自测 | unit test + 冒烟 | ❌ 待补 | 15min |
| SUBMISSION | 提测文档 | ❌ 待写 | 10min |

**总预估：55分钟内完成V3-A提测**

## 三、P0-3 具体工作清单

### 后端（已完成部分，需验证）
- `/api/artifacts` — 成果物列表索引 ✅
- `/api/artifact` — 单文件预览/下载，含路径安全 ✅
- 支持类型：Markdown/image/MP4/text/binary ✅

### 前端（需收口）
1. projects.html — 点击版本后加载成果物列表（JS fetch → /api/artifacts）
2. 成果物预览区 — Markdown渲染 / 图片查看 / MP4播放 / 文本展示 / 下载按钮
3. 空状态、加载态、错误态处理

### 验证
1. `python3 -m unittest tests/test_api_server.py` 通过
2. 手工冒烟：打开 /team/projects → 点击版本 → 看到成果物列表 → 预览MD/图片

## 四、执行方式

小叮当直接用 coding-agent 执行，不拆 sub-agent（范围小，直接主线程收口更快）。

## 五、P1 后续批次

V3-A 提测通过后再启动：
- V3-B: 告警中心实际工作
- V3-C: Agent 事件图表化 + Token 使用趋势图
