# SRE 四层日报阶段五：合并页面、接口目录、调度和端到端验收 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付可操作的合并日报页面、项目筛选、微服务接口目录、证据下钻、A/B 状态和日报配置，并让手动与每天定时生成复用同一窗口/幂等/通知链路。

**Architecture:** 保留现有 `AnalysisReport.vue` 作为报告入口和旧报告页面，新增独立 `DailySREReport.vue` 及小型组件；API 层封装新复数路由。调度器从 daily config 读取 Asia/Shanghai 09:00 默认计划，调用同一个 Coordinator；报告生成与通知解耦，没有通知渠道也照常生成。

**Tech Stack:** Vue 3 Composition API、Vue Router、Axios、EventSource、CSS、Node `node:test`、Vite、APScheduler、FastAPI、Python `unittest`。

## Global Constraints

- 页面先显示结构化基础报告，AI 只作为独立区域，不把 AI 文本当作事实表格来源。
- 健康分和数据质量分必须并列；低质量参考分不能使用正式健康颜色误导用户。
- 所有筛选使用稳定 `project_id`，名称只展示。
- “未关联项目”始终可筛选，不能隐藏或自动归属。
- 页面所有异常、AI claim、扣分项和时间线项都必须能打开证据。
- 接口目录必须有一级入口，并可下钻指标、日志、Trace、Workload 和 Pod。
- 手动和定时生成使用同一个 Coordinator，不能维护两套统计逻辑。
- 不破坏现有运维日报、主机巡检和慢日志页面。

---

## Task 1: 扩展前端 API 和纯状态工具

**Files:**

- Modify: `frontend/src/api/index.js`
- Create: `frontend/src/utils/dailyReport.mjs`
- Create: `frontend/tests/dailyReport.test.mjs`

- [ ] **Step 1: 写状态、分数和查询参数失败测试**

覆盖：低质量显示参考分；状态顺序；project_id 数组规范化；未关联项目空 ID 转成显式筛选值 `__unmapped__`；接口查询只发送非空条件。

- [ ] **Step 2: 实现 API 方法**

```javascript
createDailyReportRun(data)
getDailyReport(id, projectId)
getDailyReportStatus(id)
getDailyReportSection(id, section, projectId)
getDailyReportInterfaces(id, filters)
getDailyReportEvidence(id, evidenceId, projectId)
getDailyReportConfig()
updateDailyReportConfig(data)
dailyReportStreamUrl(id)
```

SSE URL 返回同源 `/api/reports/daily-runs/{id}/stream`；所有 project_id 使用 `URLSearchParams` 精确编码。

- [ ] **Step 3: 实现纯展示工具并测试**

```powershell
node --test frontend/tests/dailyReport.test.mjs
git add frontend/src/api/index.js frontend/src/utils/dailyReport.mjs frontend/tests/dailyReport.test.mjs
git commit -m "feat(report-ui): add daily report API state helpers"
```

## Task 2: 新增合并日报页面骨架和路由

**Files:**

- Create: `frontend/src/views/DailySREReport.vue`
- Create: `frontend/src/components/daily-report/ReportHeader.vue`
- Create: `frontend/src/components/daily-report/ReportTimeline.vue`
- Create: `frontend/src/components/daily-report/SectionTabs.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/views/AnalysisReport.vue`

- [ ] **Step 1: 增加独立路由和入口**

路由：`/tools/report/sre-daily/:reportId?`，name=`tools-sre-daily-report`。在现有 AnalysisReport 报告类型中加入“SRE 四层日报”，点击历史记录或生成成功后导航到新页面；旧三类报告仍留在原页面。

- [ ] **Step 2: 实现顶部状态区**

展示窗口/时区、全平台或项目范围、未关联项目数、health score/formal 状态、data quality、A/B 状态、AI 执行结论摘要。`health_score_formal=false` 时显示“数据不足，无法正式评级（参考分 N）”。

- [ ] **Step 3: 实现一级章节和时间线**

章节固定：总览、基础设施、业务指标、告警、日志、数据质量。跨层时间线按 occurred_at 排序，颜色来自规则 severity，不来自 AI 文本。点击时间线项触发 evidence drawer 事件。

- [ ] **Step 4: 实现生成和 SSE 重连**

POST 创建后立即进入报告页；EventSource 收到 base_ready 时 GET 完整报告并显示；A/B 状态事件只刷新状态区；连接失败时回退每 3 秒轮询 status，终态停止。组件卸载时关闭 EventSource 和定时器。

- [ ] **Step 5: 构建并提交**

```powershell
npm --prefix frontend run build
git add frontend/src/views/DailySREReport.vue frontend/src/components/daily-report frontend/src/router/index.js frontend/src/views/AnalysisReport.vue
git commit -m "feat(report-ui): add merged SRE daily report page"
```

## Task 3: 基础设施、告警、日志和数据质量章节

**Files:**

- Create: `frontend/src/components/daily-report/InfrastructureSection.vue`
- Create: `frontend/src/components/daily-report/AlertSection.vue`
- Create: `frontend/src/components/daily-report/LogSection.vue`
- Create: `frontend/src/components/daily-report/DataQualitySection.vue`
- Modify: `frontend/src/views/DailySREReport.vue`

- [ ] **Step 1: 实现统一异常排序表**

基础设施按 K8s/服务器/ES/Redis/Kafka/Jenkins 分域；每域先展示摘要和 coverage，再展示异常/变化详情。服务器表包含 IP、主机名、OS、配置、状态、CPU、内存、负载、网络、IO、TCP、负责人、机房和分组；异常优先。

- [ ] **Step 2: 实现告警生命周期**

显示触发、首次确认、恢复、MTTA、MTTR、人工关闭；缺确认/恢复显示“未响应/未恢复”，不显示 0。高频和低频致命分区，支持 project_id/严重度/状态筛选。

- [ ] **Step 3: 实现日志摘要**

每个微服务一行摘要，高频模板/关键字单独表格；不以错误条数列表代替概括。特定接口/时间证据提供“跳转日志分析”按钮，并携带 service、route、start/end、labels。

- [ ] **Step 4: 实现数据质量详情**

展示每个 Collector 的 complete/partial/unavailable、query_count、covered/expected、coverage、耗时和脱敏错误；列出被健康分排除的实体/字段。

- [ ] **Step 5: 构建并提交**

```powershell
npm --prefix frontend run build
git add frontend/src/components/daily-report frontend/src/views/DailySREReport.vue
git commit -m "feat(report-ui): render deterministic report sections"
```

## Task 4: 微服务接口目录一级入口

**Files:**

- Create: `frontend/src/components/daily-report/BusinessSection.vue`
- Create: `frontend/src/components/daily-report/InterfaceCatalog.vue`
- Modify: `frontend/src/views/DailySREReport.vue`
- Modify: `frontend/src/router/index.js`
- Test: `frontend/tests/dailyReport.test.mjs`

- [ ] **Step 1: 实现“微服务接口目录”入口**

业务章节顶部提供显眼入口，支持服务列表与接口表两种视图。筛选项：project_id、集群、Namespace、服务、Method、Route、状态；筛选变化做 250ms debounce 并请求服务端分页。

- [ ] **Step 2: 展示完整接口字段**

项目 ID、集群、Namespace、服务、Method、Route、协议、端口、发现来源、总请求、成功、4xx、5xx、服务端失败数/率、平均/峰值 QPS、max/avg/P95、异常时段、抖动跨越次数。无接口指标服务进入“接口数据不可用”，未映射服务进入“未关联项目”。

- [ ] **Step 3: 实现五类下钻**

- 指标：打开接口趋势弹层或现有 metrics 页面并传查询范围。
- 日志：跳转日志分析，携带相同 project/service/route/window。
- Trace：跳转 SkyWalking/Trace 页面，携带服务、route 和窗口。
- Workload：跳转容器资源详情。
- Pod：跳转容器页面对应微服务日志界面。

只有报告返回了确定性目标 ID 才显示跳转，不拼接猜测名称。

- [ ] **Step 4: 扩展纯函数测试、构建并提交**

```powershell
node --test frontend/tests/dailyReport.test.mjs
npm --prefix frontend run build
git add frontend/src/components/daily-report/BusinessSection.vue frontend/src/components/daily-report/InterfaceCatalog.vue frontend/src/views/DailySREReport.vue frontend/src/router/index.js frontend/tests/dailyReport.test.mjs
git commit -m "feat(report-ui): add microservice interface catalog"
```

## Task 5: 证据抽屉和 A/B 审核面板

**Files:**

- Create: `frontend/src/components/daily-report/EvidenceDrawer.vue`
- Create: `frontend/src/components/daily-report/AIReviewPanel.vue`
- Modify: `frontend/src/views/DailySREReport.vue`

- [ ] **Step 1: 实现证据抽屉**

按需 GET evidence，显示 source、entity identity、observed/window、metric/event、value/unit、threshold/source、query、labels、collection/mapping status、raw reference 跳转。query/labels 使用可复制纯文本；不渲染 HTML。

- [ ] **Step 2: 实现 A/B claim 对照**

A claim 显示置信度、实体、时间、动作和证据按钮；B 显示 confirmed/rejected/insufficient_evidence 和 reason；disputed 使用明确标识并提示人工确认；B 失败显示“未经交叉验证”。

- [ ] **Step 3: 保证 AI 与事实视觉分离**

AI 面板位于顶部摘要下方但不替代章节表格；AI claim 不改变事件 severity、表格状态或分数颜色。

- [ ] **Step 4: 构建并提交**

```powershell
npm --prefix frontend run build
git add frontend/src/components/daily-report/EvidenceDrawer.vue frontend/src/components/daily-report/AIReviewPanel.vue frontend/src/views/DailySREReport.vue
git commit -m "feat(report-ui): add evidence and A B review panels"
```

## Task 6: 日报智能配置 UI

**Files:**

- Modify: `frontend/src/views/SettingsView.vue`
- Modify: `frontend/src/api/index.js`
- Test: `frontend/tests/dailyReport.test.mjs`

- [ ] **Step 1: 新增“SRE 日报”配置分组**

字段包含 enabled、时区、每天结束时间、数据质量门槛、健康等级边界、Collector timeout/required weights、章节/领域权重、高频告警阈值、致命规则、抖动窗口/次数、轮询间隔、A 模型 ID、B 模型 ID。

- [ ] **Step 2: 复用模型列表下拉**

调用 `listAgentModels()`，显示模型记录名称、运行模型 ID、provider；A/B 不能选同一记录。未配置模型时仍允许保存基础报告配置，但说明 AI 审核将跳过。

- [ ] **Step 3: 保存前后端双重校验**

前端立即提示非法权重/边界/同模型；后端 422 仍显示具体 detail。保存成功后重新 GET，确认服务器规范化值生效。

- [ ] **Step 4: 测试、构建并提交**

```powershell
node --test frontend/tests/dailyReport.test.mjs
npm --prefix frontend run build
git add frontend/src/views/SettingsView.vue frontend/src/api/index.js frontend/tests/dailyReport.test.mjs
git commit -m "feat(settings): configure SRE daily reports and reviewers"
```

## Task 7: 定时生成和通知解耦

**Files:**

- Modify: `backend/scheduler.py`
- Modify: `backend/main.py`
- Modify: `backend/routers/daily_reports.py`
- Modify: `backend/notifier.py`
- Test: `backend/tests/test_daily_report_scheduler.py`

- [ ] **Step 1: 写无通知渠道仍生成测试**

现有 `scheduled_report_job()` 在 `SCHEDULE_CHANNELS` 为空时直接 return；新日报任务必须先生成，再按渠道配置决定是否推送。测试默认 Asia/Shanghai 09:00、手动/定时同幂等键、重复 misfire 不重复报告。

- [ ] **Step 2: 实现独立任务**

```python
async def scheduled_sre_daily_report_job() -> None:
    config = load_daily_report_config()
    result = await create_or_reuse_run(default_request_from_config(config))
    report = await wait_for_base_ready(result.report_id, timeout=config.schedule_timeout)
    await notify_sre_report_if_configured(report, config)
```

生成不依赖 `SCHEDULE_CHANNELS`；通知失败写日志/通知状态，不改变报告 complete/base_ready。任务使用 `max_instances=1`、`coalesce=True`，CronTrigger 带 ZoneInfo 时区。

- [ ] **Step 3: 让配置更新实时重排定时任务**

实现 `configure_sre_daily_job(scheduler, config)`，启动时调用一次；将 scheduler 放入 `app.state`，`PUT /api/reports/daily-config` 保存成功后使用 `Request.app.state` 调用 `reschedule_job`。配置 disabled 时移除该 job；修改时区或时间后无需重启即可在下次计划生效。测试保存配置前后的 next_run_time 和 job 数量。

- [ ] **Step 4: 实现通知摘要**

飞书/钉钉只推报告窗口、正式/参考健康分、数据质量、P0/P1 异常、A/B 状态和报告链接；不发送全部日志/证据。低质量时文案不得写“系统正常”。

- [ ] **Step 5: 运行并提交**

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest backend.tests.test_daily_report_scheduler -v
git add backend/scheduler.py backend/main.py backend/routers/daily_reports.py backend/notifier.py backend/tests/test_daily_report_scheduler.py
git commit -m "feat(report): schedule daily SRE reports independently"
```

## Task 8: 后端端到端验收测试

**Files:**

- Create: `backend/tests/test_daily_report_e2e.py`

- [ ] **Step 1: 固定时钟和全部外部源**

用 fake clients 提供两个项目、一个 unmapped、一个 Collector 失败、一个 K8s/接口/告警/日志跨层 incident、一个 Jenkins 失败 build 和中间件 conflict。

- [ ] **Step 2: 验证完整 API 生命周期**

POST -> created/collecting -> base_ready -> A -> B -> verified/disputed；验证四章节、接口筛选、证据、质量门槛、项目筛选、幂等和旧 `/api/report/list`。

- [ ] **Step 3: 验证故障矩阵**

至少包括：Prometheus 不可用、Loki 部分结果、Alertmanager 无 endsAt、A 超时、B 超时、报告目录不可写。只有快照/契约失败允许 ReportRun failed。

- [ ] **Step 4: 运行并提交**

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest backend.tests.test_daily_report_e2e -v
git add backend/tests/test_daily_report_e2e.py
git commit -m "test(report): cover end to end daily report lifecycle"
```

## Task 9: 全量回归和真实环境验收

**Files:**

- Create: `docs/operations/daily-sre-report-runbook.md`

- [ ] **Step 1: 运行自动化回归**

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -p 'test_*.py'
node --test frontend/tests/*.test.mjs
npm --prefix frontend run build
git diff --check
```

预期：全部通过，构建无错误。

- [ ] **Step 2: 在真实只读数据源生成一次报告**

选择明确的 end_at 和一个 project_id。记录报告 ID、窗口、Collector coverage、数据质量、采集耗时和各源查询；抽查 Prometheus/Loki/Alertmanager/K8s/Jenkins 各 3 条证据可复现。

- [ ] **Step 3: 执行 UI 验收清单**

- base_ready 先于 AI 完成出现。
- 六个一级章节都能打开。
- 项目、未关联项目和接口多条件筛选正确。
- 五类接口下钻目标正确。
- 每个扣分/claim/时间线项可打开证据。
- B 失败和低数据质量文案正确。
- 旧日报、巡检、慢日志、导出和通知仍可使用。

- [ ] **Step 4: 编写运行手册**

记录配置字段、默认 09:00 窗口、手动生成、状态解释、Collector 故障排查、模型失败重试、数据质量不足处理、事件轮询监控和回滚方式；不写真实凭据。

- [ ] **Step 5: 提交最终文档**

```powershell
git add docs/operations/daily-sre-report-runbook.md
git commit -m "docs(report): add daily SRE report runbook"
```

## 阶段五最终验收

- [ ] 日报页面明确列出微服务有哪些接口，并提供指标/日志/Trace/Workload/Pod 入口。
- [ ] 全平台、单项目、多项目和未关联项目视图使用 project_id 精确过滤。
- [ ] 默认每天 Asia/Shanghai 09:00 生成结束于 09:00 的滚动 24 小时报告。
- [ ] 没有飞书/钉钉配置时报告仍定时生成。
- [ ] 手动与定时同窗触发只产生一个报告。
- [ ] 报告基础事实先可见，A/B 后更新；模型失败不阻塞。
- [ ] 数据缺失、冲突、参考分、分歧都以明确状态展示，不伪装正常。
- [ ] 全量测试、Vite 构建、真实数据抽查和旧功能回归全部通过。
- [ ] `git diff --check` 无输出。
