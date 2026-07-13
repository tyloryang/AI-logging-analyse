# SRE 四层日报阶段三：确定性关联、评分和四份基础报告 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Collector 输出转成确定性实体关系、唯一 IncidentChain、可解释健康分和数据质量分，并在不等待 AI 的情况下保存基础设施、业务、告警、日志四份子报告和合并基础报告。

**Architecture:** `DailyReportCoordinator` 创建幂等 ReportRun，执行 CollectorRegistry，冻结快照，然后按“映射 → 规则评估 → 事件关联 → 评分 → 四章节构建 → 证据索引”流水线生成 `base_ready`。API 只读不可变事实，按稳定 `project_id` 过滤；SSE/状态轮询只传状态事件，不重新采集。

**Tech Stack:** Python、Pydantic、FastAPI、SQLAlchemy AsyncIO、AsyncIO task、现有报告 JSON/SQLite 存储、Python `unittest`。

## Global Constraints

- IncidentChain 只有确定性规则命中时才能合并；无法证明关联的指标、告警和日志保持独立。
- 同一个 IncidentChain 只扣一次分，supporting evidence 不重复扣分。
- 评分阈值优先级固定为服务 SLO/告警规则 > 平台默认阈值 > 无阈值只展示。
- 健康分和数据质量分完全分开；缺失实体不进入健康分分母。
- 每个项目先独立计算四章节分，全平台再按项目重要性聚合。
- `base_ready` 前必须完成快照、评分、四章节、接口目录和证据索引的原子保存。
- 本阶段不调用 AI；AI 字段保持 pending。

---

## Task 1: 确定性实体关系图

**Files:**

- Create: `backend/services/daily_report/entity_graph.py`
- Test: `backend/tests/test_daily_report_entity_graph.py`

- [ ] **Step 1: 写 K8s/CMDB/配置关系测试**

覆盖 Service selector -> Pod、ownerReference -> Workload、Pod -> Node、CMDB project/host/service/middleware 依赖、显式 Jenkins Job 关系；断言名称相似但无确定关系时没有边。

- [ ] **Step 2: 实现稳定节点和边**

```python
class EntityGraph:
    def add_identity(self, identity: EntityIdentity) -> str: ...
    def add_edge(self, source: str, target: str, relation: str, evidence_id: str) -> None: ...
    def neighbors(self, entity_id: str, relations: set[str] | None = None) -> list[str]: ...
```

每条边必须保存 `mapping_source` 和 `evidence_id`；允许的 relation 使用白名单，防止任意字符串造成不可审计关联。

- [ ] **Step 3: 运行并提交**

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest backend.tests.test_daily_report_entity_graph -v
git add backend/services/daily_report/entity_graph.py backend/tests/test_daily_report_entity_graph.py
git commit -m "feat(report): build deterministic entity graph"
```

## Task 2: 抖动、Pod 漂移、告警频率和日志频率规则

**Files:**

- Create: `backend/services/daily_report/rules.py`
- Test: `backend/tests/test_daily_report_rules.py`

- [ ] **Step 1: 写边界测试**

测试默认 30 分钟内正常/异常跨越 3 次才是抖动；同 workload 的新 Pod 跨 Node 才是漂移；rollout/eviction/node failure 必须有对应事件证据，否则原因 unknown；同稳定告警指纹 3 次为高频，1–2 次且 critical/P1 或命中 fatal 清单为低频致命；日志先按模板归一化再计频。

- [ ] **Step 2: 实现纯规则函数**

```python
def detect_jitter(samples: list[StateSample], rule: JitterRule) -> RuleFinding | None: ...
def detect_pod_drift(placements: list[PodPlacement], events: list[EvidenceRecord]) -> list[RuleFinding]: ...
def classify_alert_frequency(events: list[AlertLifecycle], config: DailyReportConfig) -> list[RuleFinding]: ...
def rank_log_templates(templates: list[LogTemplate]) -> list[RuleFinding]: ...
```

结果包含 exact time ranges、entity identity、severity、threshold、threshold_source 和 evidence_ids，不直接计算扣分。

- [ ] **Step 3: 运行并提交**

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest backend.tests.test_daily_report_rules -v
git add backend/services/daily_report/rules.py backend/tests/test_daily_report_rules.py
git commit -m "feat(report): evaluate deterministic SRE findings"
```

## Task 3: IncidentChain 关联和单次扣分边界

**Files:**

- Create: `backend/services/daily_report/correlation.py`
- Test: `backend/tests/test_daily_report_correlation.py`

- [ ] **Step 1: 写可合并和不可合并测试**

可合并示例：同项目、同 Service selector 指向的 Pod，在重叠时间内出现接口 5xx、Pod OOMKilled 和对应告警。不可合并示例：同名服务但不同 project_id、没有实体图边、时间不重叠、只有 AI 文本描述。

- [ ] **Step 2: 实现白名单关联规则**

关联键必须包含项目 ID 或明确 unmapped 边界、稳定实体图路径、时间重叠和规则 ID。`primary_evidence_id` 由严重级别/直接故障事件确定，其他只进入 `supporting_evidence_ids`。每条链保存 `correlation_rule`，便于审计。

- [ ] **Step 3: 运行并提交**

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest backend.tests.test_daily_report_correlation -v
git add backend/services/daily_report/correlation.py backend/tests/test_daily_report_correlation.py
git commit -m "feat(report): correlate evidence into unique incidents"
```

## Task 4: 数据质量和健康评分引擎

**Files:**

- Create: `backend/services/daily_report/scoring.py`
- Test: `backend/tests/test_daily_report_scoring.py`

- [ ] **Step 1: 写公式和门槛测试**

覆盖：

```text
data_quality = available_required_weight / total_required_weight * 100
penalty = base_penalty(severity) * duration_factor * scope_factor * criticality_weight
entity_score = max(0, 100 - capped_unique_incident_penalties)
```

测试 partial 按 coverage_ratio 计，unavailable 为 0；无评分规则不扣分；同 IncidentChain 不重复扣分；有效领域/章节等权回退；质量 69.99 时 `health_score_formal=false`，70 时可正式评级。

- [ ] **Step 2: 实现评分结果明细**

每次扣分输出 rule_id、incident_id、公式输入、未封顶值、封顶值和配置来源。领域、章节、项目和全平台每层都输出参与实体数、因缺失排除实体数、权重及最终值。

- [ ] **Step 3: 实现可配置等级**

默认 90–100 健康、75–89 关注、60–74 警告、<60 严重；质量不足时总体展示状态固定为“数据不足，无法正式评级”，但保留 reference health_score。

- [ ] **Step 4: 运行并提交**

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest backend.tests.test_daily_report_scoring -v
git add backend/services/daily_report/scoring.py backend/tests/test_daily_report_scoring.py
git commit -m "feat(report): score health separately from data quality"
```

## Task 5: 构建四份基础报告

**Files:**

- Create: `backend/services/daily_report/sections/__init__.py`
- Create: `backend/services/daily_report/sections/infrastructure.py`
- Create: `backend/services/daily_report/sections/business.py`
- Create: `backend/services/daily_report/sections/alerts.py`
- Create: `backend/services/daily_report/sections/logs.py`
- Create: `backend/services/daily_report/base_report.py`
- Test: `backend/tests/test_daily_report_sections.py`

- [ ] **Step 1: 写每章节最小完整输出测试**

基础设施覆盖 K8s、服务器、中间件、Jenkins；业务覆盖服务和接口目录；告警覆盖 startsAt/acknowledged_at/endsAt、MTTA/MTTR、高频和低频致命；日志覆盖每服务一句话、高频模板、关键字和特定接口时间证据。

- [ ] **Step 2: 实现异常优先和完整摘要**

全对象保留摘要，异常/变化对象才展开详情。排序统一为 severity、持续时间、影响范围、对象重要性降序，再按稳定实体 ID，保证重复生成顺序一致。

- [ ] **Step 3: 构建跨层时间线和合并报告**

合并结果包含窗口、范围、项目列表、未关联项目数量、health/data quality、四章节分数、跨层时间线、collector statuses、incident chains、evidence index、AI pending 状态。每条时间线项引用 evidence/incident ID。

- [ ] **Step 4: 运行并提交**

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest backend.tests.test_daily_report_sections -v
git add backend/services/daily_report/sections backend/services/daily_report/base_report.py backend/tests/test_daily_report_sections.py
git commit -m "feat(report): build four deterministic report sections"
```

## Task 6: 实现幂等 Coordinator 和 `base_ready`

**Files:**

- Create: `backend/services/daily_report/coordinator.py`
- Test: `backend/tests/test_daily_report_coordinator.py`

- [ ] **Step 1: 写并发重复触发和失败测试**

同时触发两个相同请求，只允许一次采集；Collector 部分失败仍到 base_ready；快照校验或写盘失败进入 failed；base_ready 后文件、report_meta 和 evidence index 都存在。

- [ ] **Step 2: 实现协调流程**

```python
async def create_or_reuse_run(request: DailyReportRunRequest) -> CreateRunResult: ...
async def build_base_report(report_id: str) -> None: ...
```

流程固定：规范窗口/范围 -> 查询幂等键 -> 创建 created -> collecting -> Collectors -> 冻结 raw snapshot hash -> 规则/关联/评分/章节 -> 原子写完整 JSON -> 替换 evidence index -> upsert report_meta -> base_ready。先完成所有持久化，再广播 `base_ready`。

- [ ] **Step 3: 移除旧日报不可靠估算**

修改 `backend/report_builder.py:collect_daily_data()`：总日志数必须来自 Loki 服务器端精确统计，活跃告警数必须来自 Alertmanager/alert_dedup；获取不到时用 unavailable/null，不再用 `total_error_count * 8` 和 `len(error_counts)`。更新旧日报测试保证回归。

- [ ] **Step 4: 运行并提交**

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest backend.tests.test_daily_report_coordinator backend.tests.test_report_builder_daily -v
git add backend/services/daily_report/coordinator.py backend/report_builder.py backend/tests/test_daily_report_coordinator.py backend/tests/test_report_builder_daily.py
git commit -m "feat(report): publish base report before AI review"
```

## Task 7: 新增兼容 API 和状态流

**Files:**

- Create: `backend/routers/daily_reports.py`
- Modify: `backend/main.py`
- Modify: `backend/routers/reports.py`
- Test: `backend/tests/test_daily_report_api.py`

- [ ] **Step 1: 写 API 失败测试**

覆盖 202 创建、相同窗口 reused、无效项目范围 422、状态查询、四章节、接口筛选、证据不存在 404、未关联项目过滤、旧 `/api/report/list` 仍能列出 `daily_sre` 元数据。

- [ ] **Step 2: 实现请求契约和端点**

```python
class DailyReportRunRequest(BaseModel):
    timezone: str = "Asia/Shanghai"
    end_at: datetime | None = None
    scope_type: Literal["all_platform", "projects"] = "all_platform"
    project_ids: list[str] = Field(default_factory=list)

POST /api/reports/daily-runs
GET  /api/reports/daily-runs/{report_id}
GET  /api/reports/daily-runs/{report_id}/status
GET  /api/reports/daily-runs/{report_id}/stream
GET  /api/reports/daily-runs/{report_id}/sections/{section}
GET  /api/reports/daily-runs/{report_id}/interfaces
GET  /api/reports/daily-runs/{report_id}/evidence/{evidence_id}
GET  /api/reports/daily-config
PUT  /api/reports/daily-config
```

POST 返回 `report_id/status/reused/window`，后台 `asyncio.create_task(build_base_report())`。SSE 事件 JSON 格式固定为 `{event, report_id, status, occurred_at, payload}`；断线重连先发送当前状态。章节、接口、证据支持 `project_id` 精确过滤。应用启动时扫描超出配置时限仍处于 created/collecting 的运行，依据是否已有合法 base snapshot 继续发布或标记 failed，不能永久卡住。

- [ ] **Step 3: 保持旧列表兼容**

旧 `list_report_meta()` 返回新字段但旧前端可忽略；不删除 `/api/report/generate` 等现有接口。新 Router 使用复数 `/api/reports`，避免和旧单数路由冲突。

- [ ] **Step 4: 运行并提交**

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest backend.tests.test_daily_report_api -v
git add backend/routers/daily_reports.py backend/main.py backend/routers/reports.py backend/tests/test_daily_report_api.py
git commit -m "feat(report): expose daily SRE report APIs"
```

## Task 8: 阶段三集成回归

**Files:**

- Create: `backend/tests/test_daily_report_base_integration.py`

- [ ] **Step 1: 构造固定多源快照**

包含两个项目、一个未映射服务、一个 partial Collector、一个确定性跨层 IncidentChain 和一个无关联异常。

- [ ] **Step 2: 断言完整闭环**

断言项目独立分数、全平台聚合、数据质量、单次扣分、接口目录、四章节、时间线、证据下钻和 base_ready；检查 AI 仍为 pending。

- [ ] **Step 3: 运行阶段三回归并提交**

```powershell
$env:PYTHONPATH='backend'
$tests = @(
  'backend.tests.test_daily_report_entity_graph'
  'backend.tests.test_daily_report_rules'
  'backend.tests.test_daily_report_correlation'
  'backend.tests.test_daily_report_scoring'
  'backend.tests.test_daily_report_sections'
  'backend.tests.test_daily_report_coordinator'
  'backend.tests.test_daily_report_api'
  'backend.tests.test_daily_report_base_integration'
)
.\.venv\Scripts\python.exe -m unittest $tests -v
git add backend/tests/test_daily_report_base_integration.py
git commit -m "test(report): verify deterministic base report pipeline"
```

## 阶段三验收

- [ ] API 触发后，不配置 AI 也能打开四份子报告和合并基础报告。
- [ ] 相同窗口重复触发返回相同 report_id，不重新采集、不重复扣分。
- [ ] 每个展示数值可打开 EvidenceRecord，看到来源、查询、时间窗、阈值和公式。
- [ ] 数据质量低于 70% 时页面/API 明确 `health_score_formal=false`。
- [ ] 同一 IncidentChain 只扣一次分，无确定关系的异常没有被合并。
- [ ] 旧日报中已不存在总日志和活跃告警估算逻辑。
- [ ] `git diff --check` 无输出。
