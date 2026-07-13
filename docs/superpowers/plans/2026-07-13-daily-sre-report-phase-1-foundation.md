# SRE 四层日报阶段一：契约、状态机和持久化基础 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立滚动 24 小时日报的统一数据契约、稳定项目维度、幂等运行状态、配置存储、SQLite 索引、JSON 快照和敏感信息脱敏，为后续 Collector 提供不可变边界。

**Architecture:** 新增 `services.daily_report` 包承载纯领域契约和窗口逻辑；扩展现有 `report_meta`，新增 `event_record` 与 `report_evidence_index`；继续使用 `reports/{report_id}.json` 保存完整正文。SQLite 只保存快速查询字段和证据索引，原始日志与完整指标序列不复制进报告。

**Tech Stack:** Python 3.11、Pydantic、SQLAlchemy AsyncIO、SQLite、ZoneInfo、FastAPI 现有 JSON 文件工具、Python `unittest`。

## Global Constraints

- 先写失败测试，再写最小实现；每个任务完成后运行任务指定测试。
- `ReportRun` 的时间窗口和项目范围一旦创建不可修改；只有生成状态、模型状态和结果路径可更新。
- 同一时区、窗口、范围和排序后项目 ID 必须命中同一个幂等键。
- `scope_type=all_platform` 时 `project_ids=[]`；`scope_type=projects` 时至少包含一个非空稳定 ID。
- `health_score` 允许保存参考分；必须用 `health_score_formal` 明确是否可正式评级。
- 失败消息和查询引用先脱敏再持久化。
- 不改变旧 `daily`、`inspect`、`slowlog` 报告的读取和列表行为。

---

## Task 1: 定义统一契约和状态枚举

**Files:**

- Create: `backend/services/daily_report/__init__.py`
- Create: `backend/services/daily_report/contracts.py`
- Test: `backend/tests/test_daily_report_contracts.py`

- [ ] **Step 1: 写失败测试覆盖必填字段和不变量**

测试至少覆盖：

```python
def test_project_scope_requires_project_ids(): ...
def test_all_platform_scope_rejects_project_ids(): ...
def test_collector_partial_requires_coverage_between_zero_and_one(): ...
def test_evidence_keeps_unmapped_project_empty(): ...
def test_model_verdict_rejects_unknown_value(): ...
```

运行：

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest backend.tests.test_daily_report_contracts -v
```

预期：因 `services.daily_report.contracts` 不存在而失败。

- [ ] **Step 2: 实现精确契约**

在 `contracts.py` 定义：

```python
class EntityIdentity(BaseModel):
    project_id: str = ""
    project_name: str = ""
    cluster_id: str = ""
    namespace: str = ""
    resource_kind: str = ""
    resource_name: str = ""
    resource_uid: str = ""
    workload_kind: str = ""
    workload_name: str = ""
    pod_name: str = ""
    container_name: str = ""
    node_name: str = ""
    host_ip: str = ""
    service_name: str = ""
    http_method: str = ""
    route: str = ""
    middleware_type: str = ""
    middleware_instance: str = ""
    jenkins_instance_id: str = ""
    jenkins_job: str = ""
    owner: str = ""
    datacenter: str = ""
    mapping_status: Literal["mapped", "unmapped", "conflict"]
    mapping_source: str = ""
```

同时定义 `ReportRun`、`CollectorStatus`、`EvidenceRecord`、`IncidentChain`、`CollectorResult`、`SectionReport`、`AIClaim` 和 `AIVerification`。字段必须与设计第 6、13、14 章一致。`status` 使用：`created | collecting | base_ready | model_a_running | a_ready | model_b_running | verified | disputed | complete_unverified | failed`。

- [ ] **Step 3: 运行测试并提交**

预期：契约测试全部通过。

```powershell
git add backend/services/daily_report/__init__.py backend/services/daily_report/contracts.py backend/tests/test_daily_report_contracts.py
git commit -m "feat(report): define daily SRE report contracts"
```

## Task 2: 实现统一滚动窗口和幂等键

**Files:**

- Create: `backend/services/daily_report/window.py`
- Test: `backend/tests/test_daily_report_window.py`

- [ ] **Step 1: 写时区、DST、排序和重复触发测试**

固定时钟测试 `Asia/Shanghai` 默认 09:00、显式 `end_at`、项目 ID 去重排序，以及同一输入产生相同 SHA-256 幂等键。

- [ ] **Step 2: 实现两个纯函数**

```python
def resolve_report_window(
    *, timezone_name: str, end_at: datetime | None, default_end_time: time
) -> tuple[datetime, datetime]: ...

def build_idempotency_key(
    *, timezone_name: str, window_start: datetime, window_end: datetime,
    scope_type: str, project_ids: list[str]
) -> str: ...
```

要求：窗口恰好 24 小时；保存为带时区 ISO 字符串；哈希输入使用规范 JSON 和排序后的唯一项目 ID；无效 IANA 时区明确报错。

- [ ] **Step 3: 运行并提交**

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest backend.tests.test_daily_report_window -v
git add backend/services/daily_report/window.py backend/tests/test_daily_report_window.py
git commit -m "feat(report): add deterministic report windows"
```

## Task 3: 建立配置契约和持久化

**Files:**

- Create: `backend/services/daily_report/config.py`
- Create: `backend/data/daily_report_config.example.json`
- Test: `backend/tests/test_daily_report_config.py`

- [ ] **Step 1: 写默认值、非法权重和 A/B 同模型测试**

默认值必须包括：`timezone=Asia/Shanghai`、`schedule_time=09:00`、`data_quality_threshold=70`、健康边界 90/75/60、抖动 30 分钟内 3 次跨越、24 小时高频告警阈值 3、四章节/有效领域等权回退，以及 K8s Events 15 秒和 Jenkins 状态 60 秒轮询间隔。

- [ ] **Step 2: 实现 `DailyReportConfig` 和原子读写**

配置包含 `collector_timeouts`、`required_observations`、`thresholds`、`scoring_rules`、`section_weights`、`domain_weights`、`project_criticality`、`fatal_alert_rules`、`project_mapping`、`model_a_id`、`model_b_id`。A/B 均配置时必须不同；权重不能为负；API 输出不得包含模型密钥。

使用 `json_snapshot_store.read_json_file/write_json_file`，运行时文件为 `data/daily_report_config.json`，只提交示例文件。

- [ ] **Step 3: 运行并提交**

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest backend.tests.test_daily_report_config -v
git add backend/services/daily_report/config.py backend/data/daily_report_config.example.json backend/tests/test_daily_report_config.py
git commit -m "feat(report): add validated daily report configuration"
```

## Task 4: 扩展数据库模型和幂等迁移

**Files:**

- Modify: `backend/report_store.py`
- Modify: `backend/main.py`
- Modify: `backend/tests/test_database_migration.py`
- Create: `backend/tests/test_daily_report_store.py`

- [ ] **Step 1: 扩充迁移失败测试**

在内存 SQLite 创建旧版 `report_meta`，连续运行 `_migrate_add_columns()` 两次，断言新增列存在且唯一索引存在；另测新表 upsert 和证据分页。

- [ ] **Step 2: 扩展 `ReportRecord`**

新增列：

```text
idempotency_key, timezone, window_start, window_end, scope_type,
project_ids_json, generation_status, health_level, health_score_formal,
data_quality_score, section_scores_json, collector_statuses_json,
model_a_status, model_b_status, verification_status, base_ready_at
```

`idempotency_key` 建唯一索引；旧记录使用空字符串和兼容默认值。更新 `save_report_meta()`、`list_report_meta()`、`sync_from_files()`，同时保留所有旧字段。

- [ ] **Step 3: 新增 `EventRecord` 和 `ReportEvidenceIndex`**

`event_record` 保存 `source_type`、`source_event_id`、`event_type`、`fingerprint`、`project_id`、实体身份 JSON、`occurred_at`、`ended_at`、`observed_at`、脱敏后的 payload JSON；`source_type + source_event_id` 唯一。

`report_evidence_index` 保存 `report_id + evidence_id` 主键、`project_id`、`source_type`、实体身份 JSON、时间范围和 JSON 文件内 `raw_reference`。

提供：

```python
async def get_report_by_idempotency_key(key: str) -> dict | None: ...
async def upsert_event_record(event: dict) -> None: ...
async def query_event_records(*, start: str, end: str, source_types: list[str]) -> list[dict]: ...
async def replace_evidence_index(report_id: str, records: list[dict]) -> None: ...
async def get_evidence_index(report_id: str, evidence_id: str) -> dict | None: ...
```

- [ ] **Step 4: 注册模型、运行迁移测试并提交**

确保 `Base.metadata.create_all` 前已经导入模型；迁移对旧 SQLite 可重复执行。

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest backend.tests.test_database_migration backend.tests.test_daily_report_store -v
git add backend/report_store.py backend/main.py backend/tests/test_database_migration.py backend/tests/test_daily_report_store.py
git commit -m "feat(report): persist report runs events and evidence"
```

## Task 5: 实现状态机、原子快照和脱敏

**Files:**

- Create: `backend/services/daily_report/state_machine.py`
- Create: `backend/services/daily_report/snapshot.py`
- Create: `backend/services/daily_report/redaction.py`
- Test: `backend/tests/test_daily_report_state_machine.py`
- Test: `backend/tests/test_daily_report_redaction.py`

- [ ] **Step 1: 写非法跳转、快照不可变和密钥泄漏测试**

覆盖 `created -> base_ready` 非法、`base_ready -> model_a_running` 合法、B 失败进入 `complete_unverified`、快照写入后计算 SHA-256、异常文本中的 Bearer/Basic/API key/URL 密码被脱敏。

- [ ] **Step 2: 实现显式状态图**

```python
ALLOWED_TRANSITIONS = {
    "created": {"collecting", "failed"},
    "collecting": {"base_ready", "failed"},
    "base_ready": {"model_a_running", "complete_unverified"},
    "model_a_running": {"a_ready", "complete_unverified"},
    "a_ready": {"model_b_running", "complete_unverified"},
    "model_b_running": {"verified", "disputed", "complete_unverified"},
}
```

状态更新必须带 `expected_current_status`，防止并发任务覆盖较新状态。

- [ ] **Step 3: 实现原子快照 API**

```python
def write_report_snapshot(report: ReportRun, reports_dir: Path) -> Path: ...
def read_report_snapshot(report_id: str, reports_dir: Path) -> ReportRun: ...
def snapshot_sha256(report: ReportRun) -> str: ...
```

报告 JSON 将 `base_snapshot` 与可更新的 `analysis_state` 分开；SHA-256 只覆盖 `base_snapshot`。保存前递归脱敏；AI 阶段只读取并复核该 base snapshot hash，写回 A/B 状态时不得改变 `base_snapshot`，也不得重新采集。

- [ ] **Step 4: 运行阶段一回归并提交**

```powershell
$env:PYTHONPATH='backend'
$tests = @(
  'backend.tests.test_daily_report_contracts'
  'backend.tests.test_daily_report_window'
  'backend.tests.test_daily_report_config'
  'backend.tests.test_database_migration'
  'backend.tests.test_daily_report_store'
  'backend.tests.test_daily_report_state_machine'
  'backend.tests.test_daily_report_redaction'
)
.\.venv\Scripts\python.exe -m unittest $tests -v
git add backend/services/daily_report backend/tests/test_daily_report_state_machine.py backend/tests/test_daily_report_redaction.py
git commit -m "feat(report): enforce report state and snapshot safety"
```

## 阶段一验收

- [ ] 同一窗口和范围重复创建时只得到一个 `report_id`。
- [ ] 所有契约拒绝未定义字段值和非法状态。
- [ ] 旧版 SQLite 连续迁移两次无错误，旧报告列表内容不丢失。
- [ ] 事件和证据索引可按项目 ID 和时间窗口查询。
- [ ] 报告 JSON 和 SQLite 抽样扫描不包含测试 Token、密码或 Cookie。
- [ ] `git diff --check` 无输出。
