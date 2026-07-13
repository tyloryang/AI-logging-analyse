# SRE 四层日报实施计划索引

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将已批准的全平台滚动 24 小时 SRE 四层日报设计，拆成五个按依赖顺序执行、每阶段均可独立测试和验收的实施计划。

**Architecture:** 保留现有 SQLite 元数据和 JSON 正文模式；先建立统一契约、状态机和易失事件存储，再接入七类 Collector，随后用确定性关联与规则引擎生成四份基础报告，最后异步执行 A/B 模型复核并交付合并页面、接口目录、证据下钻和调度。

**Tech Stack:** Python 3.11、FastAPI、Pydantic、SQLAlchemy AsyncIO、APScheduler、Kubernetes Python Client、Prometheus HTTP API、Loki HTTP API、Vue 3、Vue Router、Axios、Python `unittest`、Node `node:test`。

## Global Constraints

- 设计基线：[2026-07-13-daily-sre-four-layer-report-design.md](../specs/2026-07-13-daily-sre-four-layer-report-design.md)。实施时若发现冲突，先修改并重新批准设计，不在代码中默默改变口径。
- 所有 Collector 必须使用同一个 `window_start`、`window_end` 和 `timezone`；默认是 Asia/Shanghai、结束于当天 09:00 的滚动 24 小时窗口。
- `project_id` 只能来自 CMDB、显式 Label/Annotation 或平台映射配置。名称相似、Namespace 同名和 AI 推断都不能建立项目归属。
- 不能再使用 `total_error_count * 8` 估算总日志数，也不能用有错误的服务数代替 Alertmanager 活跃告警数。
- 数据缺失只能降低数据质量分，不能按健康或异常参与健康分；数据质量低于默认 70% 时只显示参考分。
- 四份基础报告和规则评分必须先保存并可查看；A/B 模型失败不能使基础报告不可用。
- A/B 模型只能解释不可变快照，不能改写确定性事实、EvidenceRecord、IncidentChain 或规则评分。
- 每个正式 AI 结论必须引用有效 `evidence_ids`；无证据内容只能进入待验证项。
- 完整报告和数据库不得保存明文密码、Token、Cookie、Secret 或完整认证头。
- 保持 `/api/report/*` 现有运维日报、主机巡检、慢日志、PDF/HTML/Excel 导出和通知接口可用。
- 不修改或提交当前工作区中与本功能无关的 Loki、日志分析、K8s 和文档变更。

## 实施顺序

1. [阶段一：契约、状态机和持久化基础](2026-07-13-daily-sre-report-phase-1-foundation.md)
2. [阶段二：全数据源 Collector 与易失事件采集](2026-07-13-daily-sre-report-phase-2-collectors.md)
3. [阶段三：确定性关联、评分和四份基础报告](2026-07-13-daily-sre-report-phase-3-scoring-and-base-reports.md)
4. [阶段四：A/B 模型异步初检和交叉验证](2026-07-13-daily-sre-report-phase-4-ai-review.md)
5. [阶段五：合并页面、接口目录、调度和端到端验收](2026-07-13-daily-sre-report-phase-5-ui-scheduler-e2e.md)

## 阶段门禁

| 阶段 | 必须产出 | 进入下一阶段的条件 |
|---|---|---|
| 1 | 契约、时间窗口、幂等键、状态机、配置、数据库迁移、脱敏 | 单元测试和迁移测试通过；旧报告列表仍可读 |
| 2 | K8s、主机、中间件、Jenkins、告警、业务、日志 Collector | 每类 Collector 有 complete/partial/unavailable 测试；真实源抽样无估算数据 |
| 3 | 确定性映射、IncidentChain、评分、四份基础报告、API | `base_ready` 在 AI 前可见；所有数值可下钻到证据；质量门槛生效 |
| 4 | A 初检、B 复核、分歧和失败降级 | 无证据结论被隔离；B 失败不影响基础报告；A/B 使用不同模型 ID |
| 5 | 合并日报、接口目录、证据抽屉、配置页、定时任务 | 手动/定时同窗幂等；UI 构建通过；端到端验收清单全部通过 |

## 全量回归命令

在仓库根目录执行：

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -p 'test_*.py'
node --test frontend/tests/*.test.mjs
npm --prefix frontend run build
git diff --check
```

预期：Python 和 Node 测试均为 0 失败，Vite 构建成功，`git diff --check` 无输出。
