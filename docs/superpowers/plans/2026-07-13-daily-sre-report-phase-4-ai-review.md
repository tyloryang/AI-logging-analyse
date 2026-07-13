# SRE 四层日报阶段四：A/B 模型异步初检和交叉验证 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在基础报告已可见后，让 A 模型基于同一不可变快照输出带证据的初检结论，再由不同模型 ID 的 B 模型逐条复核，并完整保留确认、拒绝、证据不足和分歧状态。

**Architecture:** 从现有智能配置模型注册表读取两个运行时模型配置，显式实例化两个 provider；AIReviewService 只读取 snapshot hash 对应的精简事实视图。所有模型输出先做结构校验和 evidence_id 白名单校验，再写回报告 AI 区域；任何模型失败都不修改基础事实和评分。

**Tech Stack:** 现有 `AIAnalyzer` provider、OpenAI-compatible/Anthropic 流式接口、Pydantic、AsyncIO、JSON、Python `unittest`。

## Global Constraints

- A/B 必须配置不同的模型记录 ID；不允许仅名称不同但 ID 相同。
- 两个模型读取同一个 snapshot SHA-256；重试不得重新采集。
- 模型输入不包含密码、Token、Cookie、Secret、完整认证头或不受限原始日志。
- 模型输出不得修改 `facts`、`collector_statuses`、`incident_chains`、`score_breakdown` 或 `evidence_records`。
- 只有引用当前报告有效 evidence_id 的 claim 才能进入正式结论。
- B 失败进入 `complete_unverified`，基础报告和 A 的有效结论继续可见并标记“未经交叉验证”。
- 不调用第三模型投票。

---

## Task 1: 提供按模型 ID 获取运行时配置的安全注册表

**Files:**

- Create: `backend/services/ai_model_registry.py`
- Modify: `backend/routers/agent_config.py`
- Test: `backend/tests/test_ai_model_registry.py`

- [ ] **Step 1: 写存在、缺失、密钥遮罩和同模型测试**

公共列表只能返回 masked key；内部运行时函数可返回 provider/base_url/model/api_key/wire_api，但不得被 API 序列化；不存在或未配置运行模型时报明确错误。

- [ ] **Step 2: 把模型文件读取集中到服务层**

```python
@dataclass(frozen=True)
class ModelRuntimeConfig:
    record_id: str
    provider: Literal["openai", "anthropic"]
    model: str
    base_url: str
    api_key: str
    wire_api: Literal["chat", "responses"]

def get_model_runtime_config(model_id: str) -> ModelRuntimeConfig: ...
def list_model_public_configs() -> list[dict]: ...
```

让 `routers/agent_config.py` 复用该服务，避免日报服务导入 Router 私有 `_load()`。保持现有 Agent Config API 输出兼容。

- [ ] **Step 3: 运行并提交**

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest backend.tests.test_ai_model_registry -v
git add backend/services/ai_model_registry.py backend/routers/agent_config.py backend/tests/test_ai_model_registry.py
git commit -m "refactor(ai): expose safe model runtime registry"
```

## Task 2: 让 AI provider 支持显式模型配置

**Files:**

- Modify: `backend/ai_analyzer.py`
- Test: `backend/tests/test_daily_report_ai_provider.py`

- [ ] **Step 1: 写全局兼容和双实例隔离测试**

断言 `AIAnalyzer()` 继续使用现有环境变量；`AIAnalyzer(runtime_config=A)` 和 B 使用各自模型、base URL 和 wire API；创建 B 不会覆盖全局环境或 A provider。

- [ ] **Step 2: 修改 provider 工厂**

```python
def create_provider(runtime_config: ModelRuntimeConfig | None = None) -> BaseAIProvider: ...

class AIAnalyzer:
    def __init__(self, runtime_config: ModelRuntimeConfig | None = None): ...
```

保留 `analyze_logs_stream()`、旧 `generate_daily_report()` 和现有调用签名；新增实例级 provider 缓存，不写 `os.environ`。

- [ ] **Step 3: 运行并提交**

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest backend.tests.test_daily_report_ai_provider backend.tests.test_ai_model_discovery -v
git add backend/ai_analyzer.py backend/tests/test_daily_report_ai_provider.py
git commit -m "feat(ai): support isolated report review models"
```

## Task 3: 构建精简、可审计的 AI 输入

**Files:**

- Create: `backend/services/daily_report/ai_input.py`
- Test: `backend/tests/test_daily_report_ai_input.py`

- [ ] **Step 1: 写输入白名单和低质量约束测试**

输入只包含窗口/范围、确定性摘要、评分明细、IncidentChain、Evidence 索引、collector statuses 和缺失项；不含 raw secret、完整日志、模型先前猜测。质量不足时 prompt 明确禁止输出“系统正常”。

- [ ] **Step 2: 实现快照精简视图**

```python
def build_ai_fact_view(report: ReportRun, *, max_evidence: int = 300) -> dict: ...
def build_model_a_prompt(fact_view: dict) -> str: ...
def build_model_b_prompt(fact_view: dict, claims: list[AIClaim]) -> str: ...
```

超限证据按 severity、incident 直接证据、时间新旧排序，始终保留 collector 缺失项和所有参与扣分 evidence。prompt 写入十年一线 SRE 角色、不猜测、所有结论有依据的约束。

- [ ] **Step 3: 运行并提交**

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest backend.tests.test_daily_report_ai_input -v
git add backend/services/daily_report/ai_input.py backend/tests/test_daily_report_ai_input.py
git commit -m "feat(report): build evidence-bound AI review input"
```

## Task 4: A 模型结构化初检和证据校验

**Files:**

- Create: `backend/services/daily_report/ai_review.py`
- Test: `backend/tests/test_daily_report_model_a.py`

- [ ] **Step 1: 写有效、无证据、未知证据和非 JSON 输出测试**

有效 claim 包含 `claim_id/claim/affected_entities/time_range/evidence_ids/confidence/recommended_action`；无 evidence 或引用别的报告 ID 的结论进入 `pending_validation`；无法解析时 A 状态失败但基础报告不变。

- [ ] **Step 2: 实现结构化流解析**

优先要求模型输出单个 JSON 对象：

```json
{"claims": [], "pending_validation": [], "executive_summary": ""}
```

流内容只在完整接收后解析；不从自然语言中用脆弱正则拼 JSON。校验 confidence 范围 0–1、time_range 在报告窗口内、affected_entities 存在、evidence_ids 属于当前快照。

- [ ] **Step 3: 原子写入 A 结果**

状态顺序 `base_ready -> model_a_running -> a_ready`；写回前再次检查 snapshot hash。保存 `model_id`、started/finished/elapsed、valid claims、pending validation 和脱敏 error。

- [ ] **Step 4: 运行并提交**

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest backend.tests.test_daily_report_model_a -v
git add backend/services/daily_report/ai_review.py backend/tests/test_daily_report_model_a.py
git commit -m "feat(report): validate model A evidence claims"
```

## Task 5: B 模型逐条复核和分歧状态

**Files:**

- Modify: `backend/services/daily_report/ai_review.py`
- Test: `backend/tests/test_daily_report_model_b.py`

- [ ] **Step 1: 写 confirmed/rejected/insufficient/disputed 测试**

B 每条结果必须包含相同 claim_id、verdict、evidence_ids、reason；缺少 claim 的复核视为 insufficient_evidence；B 引用未知 evidence 时该复核无效；B 不允许新增正式 claim。

- [ ] **Step 2: 实现合并规则**

```python
def merge_verification(
    claims: list[AIClaim], verifications: list[AIVerification]
) -> VerificationSummary: ...
```

全部 confirmed 为 `verified`；任一 rejected 且其余已验证为 `disputed`；insufficient 保留并要求人工确认；B 不可用为 `complete_unverified`。报告保留 A 原文、B 原文和结构化差异，不覆盖 A claim。

- [ ] **Step 3: 运行并提交**

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest backend.tests.test_daily_report_model_b -v
git add backend/services/daily_report/ai_review.py backend/tests/test_daily_report_model_b.py
git commit -m "feat(report): cross-check claims with model B"
```

## Task 6: 在 base_ready 后异步启动 A/B 审核

**Files:**

- Modify: `backend/services/daily_report/coordinator.py`
- Modify: `backend/routers/daily_reports.py`
- Test: `backend/tests/test_daily_report_ai_workflow.py`

- [ ] **Step 1: 写时序和降级集成测试**

覆盖 A/B 都成功、A 成功 B 失败、A 失败、A/B 分歧、两个模型 ID 相同、未配置模型。每个场景都先观察到 base_ready，且基础 facts/score 哈希始终不变。

- [ ] **Step 2: 启动独立后台审核 task**

Coordinator 在广播 base_ready 后创建 `run_ai_review(report_id)`。若模型配置缺失或相同，直接写 `complete_unverified` 和清晰原因，不把报告置 failed。进程重启时扫描 base_ready/model_running 的报告，按 snapshot hash 安全恢复或标记可重试。

- [ ] **Step 3: 扩展 SSE 状态事件**

发送 `base_ready`、`model_a_running`、`a_ready`、`model_b_running`、`verified|disputed|complete_unverified`。payload 只带小型状态摘要；前端需要完整内容时重新 GET 报告。

- [ ] **Step 4: 运行并提交**

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest backend.tests.test_daily_report_ai_workflow backend.tests.test_daily_report_api -v
git add backend/services/daily_report/coordinator.py backend/routers/daily_reports.py backend/tests/test_daily_report_ai_workflow.py
git commit -m "feat(report): run asynchronous A B report review"
```

## Task 7: 阶段四安全与回归验收

**Files:**

- Create: `backend/tests/test_daily_report_ai_security.py`

- [ ] **Step 1: 注入恶意日志和模型输出**

样本包含“忽略系统提示”、伪 evidence_id、Bearer token、数据库 URL 密码和要求改分内容；断言 prompt 将日志视为数据，secret 被脱敏，未知 evidence 被拒绝，评分不变。

- [ ] **Step 2: 运行阶段四回归**

```powershell
$env:PYTHONPATH='backend'
$tests = @(
  'backend.tests.test_ai_model_registry'
  'backend.tests.test_daily_report_ai_provider'
  'backend.tests.test_daily_report_ai_input'
  'backend.tests.test_daily_report_model_a'
  'backend.tests.test_daily_report_model_b'
  'backend.tests.test_daily_report_ai_workflow'
  'backend.tests.test_daily_report_ai_security'
)
.\.venv\Scripts\python.exe -m unittest $tests -v
```

- [ ] **Step 3: 提交**

```powershell
git add backend/tests/test_daily_report_ai_security.py
git commit -m "test(report): protect AI review facts and secrets"
```

## 阶段四验收

- [ ] 基础报告在模型开始前可打开，模型断网时仍可用。
- [ ] A/B 配置为相同 ID 时拒绝启动审核并显示明确配置错误。
- [ ] 每个正式 claim 都能打开至少一条当前报告 EvidenceRecord。
- [ ] B 的 confirmed/rejected/insufficient_evidence 逐条对应 A claim。
- [ ] 分歧完整保留并标记 disputed，不自动调用第三模型。
- [ ] A/B 运行前后事实、评分和 snapshot hash 完全相同。
- [ ] 报告文件和 API 响应不泄露模型密钥。
- [ ] `git diff --check` 无输出。
