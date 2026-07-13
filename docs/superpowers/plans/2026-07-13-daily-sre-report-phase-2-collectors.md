# SRE 四层日报阶段二：全数据源 Collector 与易失事件采集 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在同一个滚动 24 小时窗口内采集 K8s、服务器、中间件、Jenkins、Alertmanager、业务接口和 Loki 日志数据，并持续保存会在日报生成前消失的 K8s Events、告警生命周期和 Jenkins 构建状态变化。

**Architecture:** 每个数据源实现相同 `Collector` 协议，返回事实、EvidenceRecord 和 CollectorStatus；注册表并发执行并隔离失败。查询窗口型数据在生成时从 Prometheus/Loki/原生 API 拉取，易失事件通过现有 webhook 或独立轮询任务增量 upsert 到 `event_record`。

**Tech Stack:** Python AsyncIO、Kubernetes Python Client、Prometheus/Loki HTTP API、httpx、Elasticsearch/Redis/Kafka/Jenkins 现有客户端、APScheduler、Python `unittest`。

## Global Constraints

- 所有查询必须使用 `CollectorContext.window_start/window_end`，不能在 Collector 内再次调用“当前时间”生成另一个窗口。
- `complete | partial | unavailable` 是数据覆盖状态，不是健康状态。
- 每个数值事实必须带查询、标签、阈值来源和原始引用；无阈值时只展示，不判异常。
- 任何单一 Collector 失败都不能取消其他 Collector；错误写入脱敏后的 CollectorStatus。
- Prometheus 是业务接口请求量、状态码、QPS 和延迟的唯一计数源；Trace/Loki 仅补证据，不累加请求数。
- K8s、Jenkins 和中间件对象关系只使用确定性配置；不得按名称相似度关联。
- Collector 不执行评分，也不调用 AI。

---

## Task 1: Collector 协议、上下文和并发注册表

**Files:**

- Create: `backend/services/daily_report/collectors/__init__.py`
- Create: `backend/services/daily_report/collectors/base.py`
- Create: `backend/services/daily_report/collectors/registry.py`
- Test: `backend/tests/test_daily_report_collector_registry.py`

- [ ] **Step 1: 写并发、超时和部分失败测试**

构造 complete、抛异常和超时三个假 Collector，断言全部都产生 CollectorStatus，成功结果保留，超时错误脱敏，`query_count` 和 elapsed_ms 有值。

- [ ] **Step 2: 实现协议**

```python
@dataclass(frozen=True)
class CollectorContext:
    report_id: str
    timezone: str
    window_start: datetime
    window_end: datetime
    scope_type: str
    project_ids: tuple[str, ...]
    config: DailyReportConfig

class Collector(Protocol):
    name: str
    async def collect(self, context: CollectorContext) -> CollectorResult: ...
```

`CollectorRegistry.collect_all()` 使用 `asyncio.gather(return_exceptions=True)` 和每源配置超时；输出按 Collector 名称稳定排序，便于快照哈希稳定。

- [ ] **Step 3: 运行并提交**

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest backend.tests.test_daily_report_collector_registry -v
git add backend/services/daily_report/collectors backend/tests/test_daily_report_collector_registry.py
git commit -m "feat(report): add isolated collector registry"
```

## Task 2: 项目 ID 和统一实体身份映射

**Files:**

- Create: `backend/services/daily_report/project_mapping.py`
- Modify: `backend/services/cmdb_store.py`
- Test: `backend/tests/test_daily_report_project_mapping.py`

- [ ] **Step 1: 写来源优先级和冲突测试**

覆盖 CMDB、显式 Label、Annotation、平台映射、无映射、两个确定性来源给出不同 ID 的 conflict；验证同名 Namespace/服务不会自动归属。

- [ ] **Step 2: 实现 `ProjectResolver`**

```python
class ProjectResolver:
    def resolve(self, identity: EntityIdentity, metadata: MappingInput) -> EntityIdentity: ...
```

优先级严格为 CMDB > 显式 Label/Annotation > 平台配置；同一级冲突返回 `project_id=""`、`mapping_status="conflict"` 并保留来源列表。给 `cmdb_store` 增加只读查询 `find_entity_mapping(kind, stable_id)`，返回 project_id、owner、datacenter、criticality 和显式依赖，不返回凭据。

- [ ] **Step 3: 运行并提交**

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest backend.tests.test_daily_report_project_mapping -v
git add backend/services/daily_report/project_mapping.py backend/services/cmdb_store.py backend/tests/test_daily_report_project_mapping.py
git commit -m "feat(report): resolve deterministic project identities"
```

## Task 3: Kubernetes 事实和 Events Collector

**Files:**

- Modify: `backend/routers/kubernetes.py`
- Create: `backend/services/daily_report/collectors/kubernetes.py`
- Create: `backend/services/daily_report/event_pollers.py`
- Test: `backend/tests/test_daily_report_kubernetes_collector.py`
- Test: `backend/tests/test_daily_report_event_pollers.py`

- [ ] **Step 1: 为现有 K8s 读取逻辑增加可测试公共快照函数**

在 `backend/routers/kubernetes.py` 复用现有 `_build_overview_payload()`、`_serialize_event_items()`、`_get_pod_placement_index()`，增加不依赖 FastAPI Request 的只读函数：

```python
async def collect_cluster_inventory(cluster_id: str, namespace: str = "") -> dict: ...
async def collect_cluster_events(cluster_id: str, since: datetime | None = None) -> list[dict]: ...
```

不要复制认证、客户端创建或序列化代码；原有 `/api/k8s/*` 路由继续调用原逻辑。

- [ ] **Step 2: 写 Collector 失败测试**

使用伪快照验证 Namespace/Pod、容器重启时间、Deployment/DaemonSet/StatefulSet/Job/CronJob/Service/ConfigMap/Node 摘要、Pod 资源指标和 Events 都进入事实；缺 metrics-server 时状态为 partial 而非 normal。

- [ ] **Step 3: 实现窗口统计和证据**

K8s Collector 只保存 ConfigMap 的名称、引用、resourceVersion 和内容哈希，不复制配置值。重启数使用窗口内增量；Pod 漂移先保存放置事件，不在本阶段判根因。每个 cluster/namespace 生成独立 coverage。

- [ ] **Step 4: 实现增量 K8s Event 轮询**

`poll_kubernetes_events()` 每 15 秒执行，按 cluster 保存 resourceVersion/事件 UID 游标，使用 `source_type=kubernetes_event`、事件 UID + count/lastTimestamp 作为幂等来源 ID upsert。410 Gone 时重新列举并依赖唯一键去重。

- [ ] **Step 5: 运行并提交**

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest backend.tests.test_daily_report_kubernetes_collector backend.tests.test_daily_report_event_pollers -v
git add backend/routers/kubernetes.py backend/services/daily_report/collectors/kubernetes.py backend/services/daily_report/event_pollers.py backend/tests/test_daily_report_kubernetes_collector.py backend/tests/test_daily_report_event_pollers.py
git commit -m "feat(report): collect Kubernetes inventory and events"
```

## Task 4: 服务器指标 Collector

**Files:**

- Create: `backend/services/daily_report/collectors/hosts.py`
- Test: `backend/tests/test_daily_report_host_collector.py`

- [ ] **Step 1: 写精确 PromQL 和缺指标测试**

覆盖主机 IP/主机名/OS/CPU 核/内存/磁盘配置、运行状态，以及 CPU、内存、负载、网络、IO、TCP 总数和连接状态。断言每个窗口指标使用 range query 或窗口聚合，不把瞬时值伪装成 P95。

- [ ] **Step 2: 实现批量查询**

复用 `prom.discover_hosts()`，用批量 PromQL 获取 current/avg/max/P95 和阈值超限区间。窗口内无序列的统计字段返回 `None` 并标记 unavailable；只在明确阈值存在时生成 abnormal evidence。

- [ ] **Step 3: 运行并提交**

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest backend.tests.test_daily_report_host_collector -v
git add backend/services/daily_report/collectors/hosts.py backend/tests/test_daily_report_host_collector.py
git commit -m "feat(report): collect host window metrics"
```

## Task 5: Elasticsearch、Redis 和 Kafka Collector

**Files:**

- Modify: `backend/routers/elasticsearch.py`
- Modify: `backend/routers/redis_clusters.py`
- Modify: `backend/routers/kafka_clusters.py`
- Create: `backend/services/daily_report/collectors/middleware.py`
- Test: `backend/tests/test_daily_report_middleware_collector.py`

- [ ] **Step 1: 提取三个可复用只读快照入口**

分别增加：

```python
async def collect_elasticsearch_snapshot(cluster_id: str) -> dict: ...
async def collect_redis_snapshot(cluster_id: str, slowlog_count: int = 128) -> dict: ...
async def collect_kafka_snapshot(cluster_id: str) -> dict: ...
```

它们复用现有 `_load_overview`、cluster overview、topic/group 等函数，输出前移除密码、ACL、TLS 私钥和连接字符串中的凭据。

- [ ] **Step 2: 写 native/exporter 冲突测试**

验证 ES 集群/节点/索引/分片，Redis 集群/连接/QPS/命中率/慢日志，Kafka 集群/topic/分区/消费组；当原生状态与 exporter 矛盾时两份证据都保留并标记 `conflict`。

- [ ] **Step 3: 实现 Collector**

原生 API 表示当前拓扑和状态，Prometheus 表示窗口趋势；禁止让 AI 或 Collector 自行选择其中一个为真。未配置某类中间件时返回 complete 且 expected_entities=0；配置存在但全部不可达时 unavailable。

- [ ] **Step 4: 运行并提交**

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest backend.tests.test_daily_report_middleware_collector -v
git add backend/routers/elasticsearch.py backend/routers/redis_clusters.py backend/routers/kafka_clusters.py backend/services/daily_report/collectors/middleware.py backend/tests/test_daily_report_middleware_collector.py
git commit -m "feat(report): collect middleware health evidence"
```

## Task 6: Jenkins Collector 和构建变化持久化

**Files:**

- Modify: `backend/jenkins_client.py`
- Create: `backend/services/daily_report/collectors/jenkins.py`
- Modify: `backend/services/daily_report/event_pollers.py`
- Test: `backend/tests/test_daily_report_jenkins_collector.py`

- [ ] **Step 1: 写全 Job 和异常日志尾部测试**

断言全部 Job 有状态汇总；窗口内 build 有开始、结束、结果和耗时；仅 FAILURE/UNSTABLE/ABORTED/超时保存错误阶段、默认 200 行日志尾部和完整日志链接；SUCCESS 不复制控制台日志。

- [ ] **Step 2: 为客户端增加批量快照方法**

```python
async def get_report_snapshot(self, start_ms: int, end_ms: int, log_tail_lines: int = 200) -> dict: ...
```

复用 `get_all_jobs()`、`get_recent_builds()`、`get_build_info()` 和 `get_build_logs()`，限制并发数，单 Job 失败进入 partial。

- [ ] **Step 3: 实现轮询 upsert**

每 60 秒采集各 Jenkins 实例最新 build 编号和结果，以 `instance_id/job/build_number` 为 source_event_id upsert `jenkins_build`；运行中到完成是同一记录更新，避免日报生成时历史 build 已从“最近构建”列表消失。

- [ ] **Step 4: 运行并提交**

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest backend.tests.test_daily_report_jenkins_collector -v
git add backend/jenkins_client.py backend/services/daily_report/collectors/jenkins.py backend/services/daily_report/event_pollers.py backend/tests/test_daily_report_jenkins_collector.py
git commit -m "feat(report): collect and persist Jenkins build changes"
```

## Task 7: Alertmanager 生命周期 Collector

**Files:**

- Modify: `backend/services/alert_dedup.py`
- Modify: `backend/routers/alerts.py`
- Create: `backend/services/daily_report/collectors/alerts.py`
- Test: `backend/tests/test_daily_report_alert_collector.py`
- Modify: `backend/tests/test_alert_batch_status.py`

- [ ] **Step 1: 写 startsAt、acknowledged_at 和 endsAt 测试**

验证触发时间取 Alertmanager `startsAt`，恢复时间取 resolved payload 的 `endsAt`；首次人工从 new 切到 grouped/analyzing 时记录 `acknowledged_at/by`；批量 suppressed/resolved 不伪造确认时间；无确认/恢复显示 null 而非 0。

- [ ] **Step 2: 扩展 webhook 持久化**

`ingest_alerts()` 每次接收 firing/resolved 时同时 upsert `event_record`，保留稳定指纹、原始开始/结束时间和必要标签。修改 `_handle_resolved()` 使用 `endsAt`，无 endsAt 时才记录 unavailable，不用接收时间冒充恢复时间。

- [ ] **Step 3: 记录人工确认身份**

给单条状态 API 增加 `current_user`，将首次人工确认写入 `acknowledged_at` 和 `acknowledged_by`。保留现有状态名称和批量操作兼容性。

- [ ] **Step 4: 实现告警 Collector**

从 event_record 读取窗口内生命周期，计算 MTTA/MTTR 所需原始字段；按 project_id、alertname、cluster、namespace、稳定对象身份和 severity 构造稳定指纹。高频/低频致命分类留给阶段三规则引擎。

- [ ] **Step 5: 运行并提交**

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest backend.tests.test_daily_report_alert_collector backend.tests.test_alert_batch_status -v
git add backend/services/alert_dedup.py backend/routers/alerts.py backend/services/daily_report/collectors/alerts.py backend/tests/test_daily_report_alert_collector.py backend/tests/test_alert_batch_status.py
git commit -m "feat(report): preserve Alertmanager lifecycle evidence"
```

## Task 8: 业务接口和微服务接口目录 Collector

**Files:**

- Create: `backend/services/daily_report/collectors/business.py`
- Test: `backend/tests/test_daily_report_business_collector.py`

- [ ] **Step 1: 写 HTTP 口径和窗口 P95 测试**

断言 2xx/3xx 为成功、4xx 单列、5xx/timeout/connection failure 为服务端失败；验证请求数、成功数、4xx、5xx、失败率、平均/峰值 QPS、max/avg/P95 延迟、异常区间和抖动原始状态。

- [ ] **Step 2: 实现稳定接口键**

接口键为 `project_id/cluster_id/namespace/service_name/http_method/route`。只有 Prometheus 指标明确含服务和 Method/Route，或平台显式接口配置存在时进入目录。Trace/Loki 只能给已有接口补证据。

- [ ] **Step 3: 修正旧日报窗口 P95**

将 `backend/report_builder.py:collect_interface_status()` 的 P95 查询改为与报告窗口一致的区间聚合，不再使用报告结束时刻的 `rate(bucket[5m])` 冒充 24 小时 P95；扩展 `backend/tests/test_report_builder_daily.py` 防回归。

- [ ] **Step 4: 运行并提交**

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest backend.tests.test_daily_report_business_collector backend.tests.test_report_builder_daily -v
git add backend/services/daily_report/collectors/business.py backend/report_builder.py backend/tests/test_daily_report_business_collector.py backend/tests/test_report_builder_daily.py
git commit -m "feat(report): collect exact interface window metrics"
```

## Task 9: Loki 日志模板和高频关键字 Collector

**Files:**

- Create: `backend/services/daily_report/log_fingerprint.py`
- Create: `backend/services/daily_report/collectors/logs.py`
- Test: `backend/tests/test_daily_report_log_collector.py`

- [ ] **Step 1: 写模板归一化和 Loki 计数测试**

归一化动态时间戳、UUID、trace_id、IP、端口和数字，但保留异常类、HTTP route 和业务错误关键词；相同模板跨 Pod 聚合，服务/项目归属仍保留。

- [ ] **Step 2: 实现 Loki 服务器端统计优先策略**

使用 Loki metric query 统计窗口总量和候选模板频次，分页拉取有限代表样本。若 Loki 不支持所需查询，Collector 明确 partial 并记录采样边界；不根据下载的前 N 条日志推断全量条数。

- [ ] **Step 3: 生成日志证据引用**

EvidenceRecord 保存可复现 LogQL、时间窗、labels 和日志中心跳转参数，不把完整日志集合复制进报告。每个微服务错误摘要仍保持一句话，不展示无意义的错误条数排名。

- [ ] **Step 4: 运行并提交**

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest backend.tests.test_daily_report_log_collector -v
git add backend/services/daily_report/log_fingerprint.py backend/services/daily_report/collectors/logs.py backend/tests/test_daily_report_log_collector.py
git commit -m "feat(report): collect Loki templates without count estimates"
```

## Task 10: 注册真实 Collector 和启动易失事件任务

**Files:**

- Modify: `backend/services/daily_report/collectors/registry.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_daily_report_collector_integration.py`

- [ ] **Step 1: 写注册顺序和调度生命周期测试**

断言七类 Collector 名称稳定；应用启动时注册两个轮询 job，应用停止时取消；轮询配置关闭时不注册。

- [ ] **Step 2: 注册 Collector**

固定名称：`kubernetes`、`hosts`、`middleware`、`jenkins`、`alerts`、`business_interfaces`、`logs`。同一 Collector 内按实体细分 coverage，不为每个 cluster 建任意新名称。

- [ ] **Step 3: 添加 APScheduler 轮询 job**

在现有 scheduler 中加入 `daily_report_k8s_events` 和 `daily_report_jenkins_events`，`max_instances=1`、`coalesce=True`、显式 misfire grace time。调整 lifespan 顺序，确保 `Base.metadata.create_all` 和迁移成功后才启动 scheduler，避免轮询任务抢先访问不存在的 `event_record` 表。轮询失败只记录日志和 Collector 状态，不停止应用。

- [ ] **Step 4: 运行阶段二回归并提交**

```powershell
$env:PYTHONPATH='backend'
$tests = @(
  'backend.tests.test_daily_report_collector_registry'
  'backend.tests.test_daily_report_project_mapping'
  'backend.tests.test_daily_report_kubernetes_collector'
  'backend.tests.test_daily_report_event_pollers'
  'backend.tests.test_daily_report_host_collector'
  'backend.tests.test_daily_report_middleware_collector'
  'backend.tests.test_daily_report_jenkins_collector'
  'backend.tests.test_daily_report_alert_collector'
  'backend.tests.test_daily_report_business_collector'
  'backend.tests.test_daily_report_log_collector'
  'backend.tests.test_daily_report_collector_integration'
)
.\.venv\Scripts\python.exe -m unittest $tests -v
git add backend/services/daily_report backend/main.py backend/tests/test_daily_report_collector_integration.py
git commit -m "feat(report): register full daily report collection pipeline"
```

## 阶段二真实数据验收

- [ ] 选一个真实项目 ID、一个未映射对象和一个故意配置冲突对象，映射结果与来源一致。
- [ ] 对 Prometheus、Loki、Alertmanager 各抽查 3 个数值，使用报告保存的查询和窗口可复现。
- [ ] 暂停 metrics-server、Loki 或一个中间件源，报告采集仍结束且对应状态为 partial/unavailable。
- [ ] 等待 K8s Event 消失或 Jenkins 新 build 覆盖旧 build 后，event_record 仍可按窗口查到。
- [ ] 报告采集输出中没有总日志估算、告警数替代或瞬时值冒充窗口 P95。
- [ ] `git diff --check` 无输出。
