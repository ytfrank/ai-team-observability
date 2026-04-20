# TEST_PLAN.md — ai-team-observability V3-A

**测试负责人**: Guard  
**日期**: 2026-04-20  
**风险等级**: medium（PMO rescue 代码，schema 修复型变更）  
**测试矩阵**: normal（api + ui_flow + regression）  
**对应commit**: dc11786 / 77eea7d  
**进入测试时间**: 2026-04-20 09:45

---

## 一、测试范围

### V3-A 改动点
1. **P0-1**: Collector 版本隔离（base_project + version 字段）
2. **P0-2**: 项目列表版本分组（grouped=1）
3. **P0-3**: 成果物预览与下载（MD/图片/视频/二进制）
4. **P1-3**: 告警中心（alerts API + 页面）
5. **Bug fix**: ensure_schema 自动补列，DB migration 修复

### 不测
- P1-1（Agent事件图表化）— 未纳入 V3-A
- P1-2（Token趋势图）— 未纳入 V3-A
- 公网部署（Atlas 负责）
- Collector 定时刷新机制

---

## 二、测试场景

### 2.1 API 测试（7项）
| # | 场景 | 校验点 |
|---|------|--------|
| 1 | /api/stats | 返回 agents/projects/events_24h/tokens_24h |
| 2 | /api/projects | 版本元数据完整（base_project, version） |
| 3 | /api/projects?grouped=1 | 按 base_project 聚合，active_version 正确 |
| 4 | /api/artifacts | 成果物列表含 preview_type |
| 5 | /api/artifact (MD) | Markdown 内容正常返回 |
| 6 | /api/artifact (path traversal) | 返回 403 |
| 7 | /api/alerts | 返回告警列表（可为空） |

### 2.2 UI 测试（4项）
| # | 场景 | 校验点 |
|---|------|--------|
| 8 | GET / | HTTP 200，dashboard 渲染 |
| 9 | GET /team/projects | HTTP 200，版本分组展示 |
| 10 | GET /team/alerts | HTTP 200，告警页面 |
| 11 | GET /nonexistent | HTTP 404 |

### 2.3 数据准确性（2项）
| # | 场景 | 校验点 |
|---|------|--------|
| 12 | 版本隔离 | V1/V3 数据不混淆 |
| 13 | 单元测试 | 6/6 通过 |

### 2.4 回归（2项）
| # | 场景 | 校验点 |
|---|------|--------|
| 14 | Collector 重复运行 | --once 连续两次不报错 |
| 15 | API 无 Collector 状态 | 不崩溃（DB 已有数据） |

---

## 三、测试分工

全部由 Guard 亲自执行（API + curl 测试，规模可控）。

## 四、ETA

25 分钟（截至 10:30）

## 五、未覆盖项

- 真实浏览器渲染（无 headless browser）
- 成果物图片/视频预览（需真实文件）
- Collector 定时刷新间隔
- 公网部署验证
- P1-1/P1-2（不在 V3-A 范围）
