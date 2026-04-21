# SUBMISSION Round 2 — ai-team-observability V5

**提交人**: Peter
**日期**: 2026-04-21
**Commit**: f45d274
**对应提测轮次**: 第二轮

---

## 一、修复内容

### P0-1: `_classify_event()` 事件分类不全
- **问题**: 只返回 5 种 kind（tool, error, timeline, a2a, subagent），前端定义了 8 种 milestone 图标/颜色
- **修复**: 扩展 `_classify_event()` 支持 `stage_enter`, `stage_exit`, `artifact_commit`, `a2a_send`, `a2a_receive`, `subagent_spawn`, `subagent_return`, `warning` 等细粒度分类
- **改动文件**: `api/api_server.py`

### P0-2: `_stage_priority()` 不识别新阶段格式
- **问题**: 只识别 `developing`/`testing`/`deploying` 等长格式，不识别 `develop`/`test`/`deploy`/`dev`/`qa`/`acceptance`/`requirements` 等短格式和别名
- **修复**: 增加 `_stage_priority()` 对所有短格式和别名的映射，确保排序逻辑与新格式兼容
- **改动文件**: `api/api_server.py`

### P0-3: Agent detail 缺少 `current_stage` 字段
- **问题**: `_api_agent_detail()` 返回的 agent 信息中没有 `current_stage`，导致前端阶段高亮 banner 异常
- **修复**: 在 agent detail 响应中补充 `current_stage` 字段，并通过 `_normalize_stage()` 统一为新短格式
- **改动文件**: `api/api_server.py`

---

## 二、自测结果

```
Ran 158 tests in 0.314s — OK
```

- `tests/test_api_server.py`: 全部通过
- `tests/test_v5_features.py`: 全部通过
- 涵盖 `_classify_event` 分类测试、`_stage_priority` 别名映射测试、agent detail `current_stage` 字段测试

---

## 三、改动文件清单

| 文件 | 改动说明 |
|------|---------|
| `api/api_server.py` | 修复 3 个 P0：_classify_event、_stage_priority、current_stage |
| `collector/collector.py` | 数据层适配 |
| `tests/test_api_server.py` | 补充基础测试 |
| `tests/test_v5_features.py` | 新增 P0 对应的专项测试用例 |

---

## 四、测试重点（Guard 请关注）

1. **事件分类**: 前端 milestone 图标/颜色是否正确显示（8 种类型）
2. **项目排序**: 不同阶段格式的项目是否按优先级正确排序
3. **Agent 阶段高亮**: Agent detail 页的阶段 banner 是否正常显示
4. **回归**: 原有功能未受影响

---

## 五、风险

- 暂无已知新增风险
- `_classify_event` 分类基于 `event_category` 字段，若上游数据缺失该字段，会 fallback 到通用分类

---

*由 Peter 于 2026-04-21 提交*
