# TECH_PLAN.md — ai-team-observability V3 Restart

- 项目: ai-team-observability
- 版本: V3
- 日期: 2026-04-19
- 负责人: Peter
- 当前分支: v3
- 状态: 重启执行方案（旧执行作废，既有 commit 仅作参考，不作为本轮提测基线）

## 一、重启结论

本轮 V3 不是需求方向错误，而是工程拆解和执行编排失败。

### 失败根因
1. 需求范围一次性覆盖数据修复、成果物系统、告警中心、事件图表、Token 趋势图、多个 P2 优化，超出单轮稳定交付范围。
2. 原技术方案写了 3 个开发 sub-agent，但实际 0 个启动，计划与执行失真。
3. 中途改为主线程收口后，没有同步重定义交付边界，导致提交物、状态、仓库事实不同步。
4. 在 P0 未形成稳定提测基线前，同时推进 P1 图表与告警，收口路径被拖散。

### 本次决策
1. 保留 V3 需求目标，不保留原执行方案。
2. 旧 commit 作为参考实现，可择优吸收；本轮从新技术方案重新组织开发与提测。
3. 先建立可验证、可提测、可审计的最小有效交付路径，再逐批扩展。

## 二、重启后的交付分层

### V3-A（本轮正式提测范围，必须完成）
1. **P0-1 Collector 版本隔离与数据准确性**
2. **P0-2 项目列表版本分组**
3. **P0-3 成果物预览与下载**

### V3-B（V3-A 提测通过后立即进入）
1. **P1-3 告警中心实际工作**

### V3-C（第三批）
1. **P1-1 Agent 事件按项目维度图表化**
2. **P1-2 Token 使用趋势图**

### 暂不纳入本轮承诺
- 全部 P2 优化项
- 任何超出 V3-A/B/C 的额外体验增强

## 三、本轮目标

本轮只承诺交付 **V3-A 可提测版本**。

### 目标结果
1. `/api/projects` 数据与各版本 `status.json` 一致，不混淆 V1/V2/V3。
2. `/team/projects` 支持主项目聚合、版本分组、活跃版本高亮、归档版本弱化。
3. `/api/artifacts` 与 `/api/artifact` 稳定可用。
4. Markdown / 图片 / MP4 / 文本支持在线预览，所有文件支持下载。
5. `TECH_PLAN.md`、代码改动、测试记录、`SUBMISSION.md` 保持一致。

## 四、技术方案

### 4.1 Backend / Collector
涉及文件：
- `collector/collector.py`
- `api/api_server.py`
- `tests/test_api_server.py`

实施要点：
1. 统一以 `repo_name + version` 作为稳定 `project_id`。
2. 从 `status.json` 中提取：
   - `project`
   - `version`
   - `workflow.current_stage`
   - `official.updated_at`
   - `artifacts_base_path`
3. 增补项目聚合字段：
   - `base_project`
   - `version`
   - `artifact_root`
   - `updated_at`
4. `/api/projects` 返回可直接驱动前端分组的数据结构。
5. `/api/artifacts` 实现成果物自动索引，覆盖 `requirements / dev / qa / acceptance / deploy / handoffs`。
6. `/api/artifact` 做路径安全校验，仅允许访问项目成果物根目录内文件。
7. 明确内容类型，支持 Markdown / image / mp4 / text / binary。

### 4.2 Frontend
涉及文件：
- `web/static/projects.html`
- 如有必要补充少量共享脚本或样式文件

实施要点：
1. 项目页按 `base_project` 分组渲染版本卡片。
2. 活跃版本置顶显示，归档版本灰显。
3. 点击版本后加载成果物列表。
4. 预览区支持：
   - Markdown 渲染
   - 图片查看
   - MP4 播放
   - 文本展示
   - 二进制文件下载提示
5. 失败态、空状态、加载态明确可见。

### 4.3 Test / Verify
涉及文件：
- `tests/test_api_server.py`
- 必要时增加针对 artifacts 的补充测试

必须覆盖：
1. `/api/projects` 版本隔离与 grouped 返回结构
2. `/api/artifacts` 的列表结果与时间排序
3. `/api/artifact` 对 Markdown / 图片 / 视频 / 非法路径的处理
4. 关键页面静态资源加载与接口联调最小冒烟

## 五、Agent 编排（重排后）

### 本次是否拆分
- 是，必须拆分

### 计划启动 4 个执行单元
1. **Test Writer**
   - 目标：先锁定 V3-A 验收测试边界
   - 输出：API/行为测试

2. **Backend Dev**
   - 目标：collector + API + artifacts 索引与安全
   - 输出：后端实现与后端自测通过

3. **Frontend Dev**
   - 目标：项目页分组 + 成果物预览/下载 UI
   - 输出：前端页面实现

4. **Verify / Review**
   - 目标：统一执行验证、检查需求覆盖、阻止假提测
   - 输出：验证结论 + 风险清单

### 为什么不是 3 个
因为这次失败点不只是“开发”，而是缺少独立的收口与验收守门。若仍然只有 3 个，最终很容易再次出现“实现有了，但提测基线不成立”的问题。

## 六、执行顺序

### Phase 0：基线重置
1. 读取当前仓库事实
2. 明确旧 commit 只作参考，不直接作为提测基线
3. 以 V3-A 为唯一交付承诺

### Phase 1：测试先行 + 前后端并行
1. Test Writer 先补 API / artifacts / grouped projects 的行为测试
2. Backend Dev 与 Frontend Dev 并行开发

### Phase 2：联调收口
1. 后端接口对接前端页面
2. 修复类型判断、路径安全、异常态展示问题

### Phase 3：验证与评审
1. 跑单测
2. 跑最小手工冒烟
3. Reviewer 检查需求覆盖、风险、遗漏项

### Phase 4：提测
1. 生成新 `SUBMISSION.md`
2. 保证 commit、测试记录、提测文档一致
3. 发群并通知 Guard

## 七、验收标准（仅针对 V3-A）

### P0-1
- `/api/projects` 不混淆不同版本项目
- `current_stage`、更新时间、owner 等信息与 `status.json` 一致

### P0-2
- 项目页按主项目分组
- 活跃版本突出显示
- 归档版本弱化显示

### P0-3
- Markdown 文件可在线渲染
- 图片可查看
- MP4 可播放
- 全部成果物可下载
- 非法路径访问被拒绝

### 工程验收
- 单测通过
- 最小手工冒烟通过
- `SUBMISSION.md` 使用最新 commit
- 工件与代码事实一致

## 八、风险与约束

1. 旧实现中可能已有部分可复用逻辑，但必须重新以 V3-A 边界审视，不能直接视作完成。
2. 成果物预览的类型判断与路径安全是最高风险点，优先保守实现。
3. 前端为 Vanilla JS，不做重型交互设计，避免再次扩散范围。
4. 若发现告警中心逻辑与 V3-A 共用数据模型产生强耦合，本轮只做兼容预留，不把告警并入本轮承诺。

## 九、计划 / 实际（重启版）

- 本次是否拆分: 是
- planned_dev_subagents: 4
- started_dev_subagents: 待启动
- 当前活跃 subagents: 0
- 当前最新 commit: `d48c21355a074a70e5f40d8301e90f9ca1092f21`（仅参考，不作为本轮提测基线）
- 当前最新成果物更新时间: 2026-04-19 15:42 +0800（本 TECH_PLAN）
- 偏差原因: 原方案大而散，且未真实启动编排
- 修正动作: 缩承诺范围到 V3-A，采用 4 单元编排重新开始

## 十、预计节奏

- T+15 分钟：完成新方案同步 + 开发编排启动
- T+45 分钟：测试边界锁定，前后端并行开始产出
- T+120 分钟：完成 V3-A 主体联调
- T+180 分钟：给出“可提测 / 不可提测”明确结论

## 十一、群内同步口径

建议对外口径：

1. V3 不再沿用旧执行方案，按新技术方案重启。
2. 本轮只承诺 V3-A（3个P0），先交付稳定提测基线。
3. 告警中心与图表能力拆到后续批次，避免再次拖散主路径。
4. 本轮计划 4 个执行单元并行，确保测试、实现、验证三层都有人负责。

---

**结论**：这次不是简单补做，而是正式重启。先把 V3-A 做成一个真实可提测版本，再推进 V3-B / V3-C。