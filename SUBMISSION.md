# SUBMISSION.md — ai-team-observability V1.0 (验收打回修复)

**提交人**: Peter  
**提交时间**: 2026-04-10 05:15  
**commit**: cc8b6b8  
**类型**: bugfix (验收打回修复)

---

## 修复内容

### P1-1: event_log 采集 0 条（核心功能）

**根因**: `collector.py` 的 `scan_sessions()` 函数有两处 bug：

1. **死代码导致 early return**: 函数开头检查 `~/.openclaw/sessions/` 是否存在，该目录不存在导致函数直接返回空列表，**永远不会扫描** `~/.openclaw/agents/*/sessions/*.jsonl`
2. **字段提取错误**: OpenClaw 的 JSONL 格式中，`role`/`model`/`usage`/`content` 都嵌套在 `message` 字段下，而代码在顶层提取，全部为空

**修复**:
- 移除对 `~/.openclaw/sessions/` 的检查（死代码）
- 修复字段提取：从 `entry['message']` 嵌套结构中读取 role/model/usage/provider/content
- 修复 token 字段名：使用 `input`/`output` 而非 `prompt_tokens`/`completion_tokens`
- 修复 content 解析：处理 `[{type: 'text', text: '...'}]` 数组格式

**修复后效果**:
```
总事件数: 6776
  LLM 事件: 2659（含真实 token 数据）
  生命周期事件: 4117

模型使用（跨6个agent）:
  zai/glm-5.1:       1,837 calls, 15.2M input, 286K output
  zai/glm--5:          379 calls, 807K input, 83K output
  zai/glm-4.7:         227 calls, 1.87M input, 89K output
  openai-codex/gpt-5.4: 128 calls, 1.84M input, 32K output
  anthropic/claude-sonnet-4-6: 73 calls, 57 input, 21K output
  anthropic/claude-opus-4-6:   8 calls
```

### P1-2: 未部署到 monitor.doramax.cn

不在本次修复范围，需 Atlas 部署。

---

## 自测结果

- ✅ `python3 collector/collector.py --once` → 6776 events collected
- ✅ API `/api/events` 返回真实数据
- ✅ API `/api/stats` 返回真实 token 统计
- ✅ 各 agent 均有事件数据（doraemon/atlas/peter/guard/main/dasheng）

## 测试重点

1. `GET /api/events?category=llm` → 应返回 2659+ 条 LLM 事件
2. `GET /api/stats` → tokens_24h 应有非零值
3. Dashboard 页面 event_log 列表应显示真实数据
4. 验收标准 #1（多 provider 调用和 token 趋势）和 #5（回放任务关键轨迹）

## 注意事项

- DB 已重建（`data/events.db`），需确认 API server 指向正确路径
- 部署仍需 Atlas 执行（验收标准 #7）
