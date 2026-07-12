# AI 分析能力升级 — 借鉴 sxdevops 的落地与差距分析

> 参考项目：https://github.com/aiyiyi121/sxdevops （AIOps 2.1 指标证据包 + MCP/Skill 双阶段应答）

## 本次已落地

### 1. 指标证据包（证据链核心，`services/evidence.py`）
- 后端**模板化**生成受预算约束的查询计划（主机 / 服务 RED / K8s 运行态 / 集群），
  不让模型自由生成 PromQL。
- 查询预算：最多 8 条 PromQL、默认 60 分钟窗口、步长 60s。
- 结果压缩为 `latest / baseline / peak / trend / status / weight`，完整时序不给模型。
- 证据不足显式输出 `gaps`（无数据 ≠ 正常）。
- 接入 RCA：`collect_context` 并行采集证据包 → 异常项直接给对应假设类别加权
  → `_build_result_markdown` 新增「## 指标证据链」章节。

### 2. AI 助手场景化诊断工具
- **容器场景**：`diagnose_k8s_pod`（一次拿状态+容器重启原因+Warning事件+崩溃日志）、
  `get_k8s_events`（OOM/镜像拉取/调度失败）。
- **CMDB 服务器场景**：`find_cmdb_host`（定位）、`diagnose_cmdb_host`（指标证据包 + SSH 实时快照）。
- **Java 诊断优化**：`run_java_diagnostics` 自动 SSH 发现 Java 进程 PID（取内存最高），
  再跑 Arthas（thread/jvm/memory/死锁），免去手填 PID。

### 3. 内嵌知识图谱（`services/knowledge_graph.py` + `/api/kg/*`）
- **不引 neo4j**：sxdevops 实际也未用 neo4j，本平台已全栈 SQLite，用 `kg_nodes/kg_edges`
  两表实现属性图，零额外运维。
- 数据源：CMDB 主机 + K8s（集群/节点/Pod/Service + RUNS_ON/SCHEDULED_ON/OWNS/SAME_MACHINE 边）
  + SkyWalking 服务调用拓扑（CALLS 边）。
- 支持邻居查询与两跳影响面遍历；agent 工具 `query_knowledge_graph` / `rebuild_knowledge_graph`。

### 4. 证据链纪律注入提示词（`agent/graph.py`）
- RCA/chat 系统提示词加入：只基于工具实际证据下结论、无数据≠正常要指出缺口、
  结构化证据优先、每条结论附证据来源。

## 仍欠缺 / 后续可补（按优先级）

### P0（提升可信度）
1. **证据包第二阶段扩展**：当前只做第一阶段模板。sxdevops 设计里错误率+延迟同时异常时
   应扩展依赖/入口/下游指标，CPU/内存异常扩展 throttling/limit。可在 `evidence.py`
   加 `expand_stage2(pack)`。
2. **图谱增量更新 + 定时重建**：目前是手动/按需全量 build。应挂到 `cron_ticker`
   每 10~30 分钟增量刷新，并在告警 webhook 触发时更新受影响子图。
3. **RCA 结论回填图谱**：把确认的根因作为 `INCIDENT` 节点连到受影响实体，
   形成「故障传播历史」，下次同类告警可沿图召回。

### P1（体验与闭环）
4. **前端知识图谱可视化**：`/api/kg/neighbors` 已就绪，缺一个力导向图页面
   （可复用 K8sTopologyView 的渲染）。
5. **证据包前端展示**：RCA 详情页把 `context.metric_evidence.pack` 渲染成
   「异常/正常/缺口」三色证据卡，而不只是 markdown。
6. **双阶段 LLM 应答整形**：sxdevops 的「一阶段规划工具 + 代码兜底草稿 + 二阶段整形」
   本平台是单阶段 LangGraph。可在 `_stream_graph` 后加一个兜底草稿层，
   保证工具证据不因模型最后自由发挥而丢失。

### P2（规模化）
7. **指标模板后台可配置**：目前模板硬编码在 `evidence.py`，可迁到 `data/` JSON 供运营配置。
8. **图谱高基数保护**：大集群 Pod 已限 400，但边可能爆炸，需加节点度数上限与采样。
9. **中间件/DB/网关证据模板**：evidence 目前覆盖主机/服务/K8s，缺 MySQL/Redis/Kafka/Nginx 场景模板。

## 与 sxdevops 的差异说明
- **不照搬 neo4j / Django ORM**：本平台是 FastAPI + SQLite 全栈，图谱用 SQLite 属性图更契合，
  避免为单一功能引入图数据库运维成本。
- **证据链思想一致**：后端可控查询计划 + 结果压缩 + 缺口显式化 + 模型只解释不臆造，
  这是本次采纳的核心。
