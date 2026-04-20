# SUBMISSION.md — ai-team-observability V3 (PMO Rescue)

- 项目: ai-team-observability
- 版本: V3
- 当前阶段: developing → 准备提测
- 负责人: 小叮当（PMO rescue 接手）
- 当前分支: v3
- 最新开发 commit: `dc11786`（2026-04-20）
- 上一个 commit: `d48c213`（2026-04-18）

## 1. Rescue 背景

Peter 开发阶段连续55h+无新commit，PMO根据rescue规则接手。经review发现：
- P0-1、P0-2、P0-3 代码实际已基本完成
- 核心问题是 DB schema 缺少6个列导致 API 500 错误，前端无法正常展示
- 修复 schema 后全部功能恢复

## 2. 本轮已完成

### P0-1 Collector 版本隔离与数据准确性 ✅
- collector 按 `repo_name + version` 归一化 project_id
- base_project 提取逻辑，支持 `-v`/`_v` 后缀识别
- `/api/projects` 返回版本维度元数据

### P0-2 项目列表版本分组 ✅
- `/api/projects?grouped=1` 返回按 base_project 聚合的数据
- 前端 projects.html 实现版本卡片、活跃版本高亮、归档灰显
- 版本排序：活跃 > 归档，按更新时间倒序

### P0-3 成果物预览与下载 ✅
- `/api/artifacts` 自动索引 monitor 子目录下所有文件
- `/api/artifact` 路径安全校验（限制在 PROJECTS_HOME 内）
- 前端支持 Markdown 渲染、图片查看、MP4 播放、文本展示、二进制下载
- 空状态、加载态、错误态处理完整

### Bug 修复
- **ensure_schema 自动补列**：添加 try/except + 显式 commit，防止以后 DB 迁移遗漏
- 手动补齐 6 个缺失列：base_project, version, project_name, lifecycle, status_file, artifact_root

## 3. 自测记录

### 单元测试
```
python3 -m unittest discover -s tests -v
6/6 全部通过 ✅
- test_projects_api_flat_records_include_version_metadata ✅
- test_projects_api_supports_grouped_versions ✅
- test_artifacts_api_indexes_previewable_files ✅
- test_artifact_api_streams_file_inline ✅
- test_alerts_api_respects_limit_and_order ✅
- test_alerts_page_serves_live_dashboard_markup ✅
```

### API 冒烟
- `GET /api/stats` → ✅ agents/projects/events/tokens 统计正常
- `GET /api/projects` → ✅ 6个项目记录，含版本元数据
- `GET /api/projects?grouped=1` → ✅ 按 base_project 分组
- `GET /api/artifacts?project_id=ai-team-observability-v3` → ✅ 返回成果物列表
- `GET /api/artifact?path=...` → ✅ Markdown 文件内容正常返回
- `GET /team/projects` → ✅ 前端页面正常渲染
- `GET /api/alerts` → ✅ 告警列表

### 数据验证
- Collector 采集: 16255 events, 6 projects
- 版本分组: ai-team-observability (v1 + v3), voice-bridge (v1.6 + v1.7)

## 4. 当前风险

- 老版本 status.json 格式不同，部分字段为 null（base_project 未填充），前端 fallback 正常
- monitor.doramax.cn 公网部署尚未执行（需 Atlas）
- P1（Agent事件图表、Token趋势图）未纳入本轮，待 V3-A 提测通过后推进

## 5. 测试重点

1. `/api/projects` 版本隔离是否彻底（不同版本不混淆）
2. `/team/projects` 分组、活跃高亮、归档灰显是否正确
3. 成果物 Markdown / 图片 / 文本预览是否正常
4. 成果物下载是否正常
5. 非法路径访问是否被拒绝（403）
6. 告警中心列表展示
7. `/api/stats` 统计数据准确性

## 6. 提测结论

**V3-A 可提测。** P0-1/P0-2/P0-3 已完成，6/6 单测通过，API 全部冒烟通过。
