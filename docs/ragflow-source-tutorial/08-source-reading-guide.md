# 08. 五级源码阅读路线

这条学习梯度的目标是从“知道目录”进阶到“能基于证据解释和排障一条完整 AIOps 调用链”。每一级都包含掌握标准、练习和自检。

## Level 1：完全入门者

### 要理解什么

理解平台连接哪些数据源，Web、CLI、FastAPI、Agent 各自扮演什么角色。

### 掌握标准

能用两分钟解释：用户在日志页面发起查询后，请求如何到 Loki，又如何返回页面。

### 关键概念

- Router、Service、Client；
- JSON 与 SSE；
- 日志、指标、链路、拓扑；
- 同步请求与后台任务。

### 里程碑

独立画出本教程 `01` 的简化架构图。

### 练习

依次阅读：

1. 根 [`README.md`](../../README.md)；
2. [`backend/main.py`](../../backend/main.py) 的应用组装区；
3. [`frontend/src/App.vue`](../../frontend/src/App.vue)；
4. [`docker-compose.yml`](../../docker-compose.yml)。

### 常见错误

- 按文件名逐个阅读，没有问题导向；
- 把页面、接口和外部系统混成一层；
- 看到 AI 就跳过普通数据链路。

### 自检问题

为什么 Loki、Prometheus 和 SkyWalking 不直接由浏览器访问？

## Level 2：基础理解者

### 要理解什么

理解 FastAPI 组合根、认证/RBAC、多存储和 Vue API 层。

### 掌握标准

给出一个 `/api/*` URL，能定位到 Router、后端依赖和前端调用者。

### 关键概念

- `include_router` 与 APIRouter prefix；
- 中间件、`Depends`、模块权限、资源范围；
- SQLAlchemy session；
- `data/`、`reports/`、Redis、Neo4j、Milvus 的分工；
- Router meta 与前端守卫。

### 里程碑

追踪一次登录和一次受管理员保护的连接器请求。

### 练习

从 `frontend/src/stores/auth.js` 开始，追踪：

```text
login -> api/index.js -> auth/router.py -> auth/service.py -> auth/session.py
```

再比较一个 `Depends(require_admin)` 的 Router。

### 常见错误

- 把前端按钮隐藏当作权限控制；
- 默认所有数据都在 SQLite；
- 忽略反向代理的 Cookie 与 header 行为。

### 自检问题

一个非管理员用户直接调用 Redis 删除 Key 接口时，哪几层应阻止它？

## Level 3：实践使用者

### 要理解什么

能完整追踪一条日志/报告链和一条 Agent 工具链。

### 掌握标准

能指出每一步输入、输出、持久化状态、SSE 事件和失败分支。

### 关键概念

- LogQL 与 Loki label；
- 慢日志远程读取与 parser；
- 报告分阶段可见性；
- LangGraph ReAct 循环；
- tool schema、风险和确认模式；
- conversation checkpoint。

### 里程碑

完成两张时序图：

1. `LogAnalysis.vue -> Loki -> AI SSE`；
2. `Agent UI -> LLM -> Tool -> External System -> SSE`。

### 练习 A：日志分析

```text
LogAnalysis.vue
  -> api/index.js
  -> routers/logs.py
  -> loki_client.py
  -> ai_analyzer.py
```

记录最终 LogQL、时间窗、返回条数和 SSE 完成条件。

### 练习 B：Agent

```text
routers/agent.py
  -> build_graph()
  -> _get_llm().bind_tools()
  -> guarded tools node
  -> tool_modules/logs.py 或 prometheus.py
```

记录 mode、executor、confirm_mode、模型 wire API 和工具事件。

### 常见错误

- 只跟 happy path，不看 empty/error/done；
- 只记录函数名，不记录关键字段；
- 把工具未调用归因于模型，不检查可见工具列表；
- 把 AI 未结束当作基础数据未生成。

### 自检问题

如何用日志证明一次 Agent 请求到底停在“模型选择工具前”“工具执行中”还是“最终回答流式输出中”？

## Level 4：问题解决者

### 要理解什么

能够处理跨日志、指标、链路、拓扑、权限和异步状态的问题。

### 掌握标准

面对故障时能提出可验证假设，并为每个假设指定证据位置。

### 关键概念

- 数据源健康与查询失败降级；
- 多信号时间对齐；
- 异步竞态与 stale response；
- 多存储最终一致性；
- Webhook 安全、审计和资源范围；
- 图谱新鲜度与 RCA 置信度。

### 里程碑

写一份“报告生成一直转圈”或“RCA 结论无证据”的排障树。

### 练习

分析场景：“告警页面能看到故障，但 RCA 找不到相关日志”。至少验证：

1. 告警 normalized label 与服务标识；
2. 告警时间、Loki 时间和浏览器时区；
3. 知识图谱 service/pod/host 映射；
4. Loki label 名和值；
5. 查询失败是否被降级为空数组；
6. evidence 是否记录原始查询条件；
7. 当前用户的数据范围权限。

### 常见错误

- 一开始就修改阈值或 prompt；
- 只看 HTTP 200；
- 把“无数据”和“数据源异常”混为一谈；
- 用过期图谱推断实时依赖；
- 忽略页面旧请求覆盖新状态。

### 自检问题

怎样区分“RCA 没有候选对象”“候选对象没有证据”“证据足够但模型总结失败”？

## Level 5：自信实践者

### 要理解什么

能够评估架构变更影响面，为安全、兼容、观测和回滚设计验证方案。

### 掌握标准

能对一个 Router 拆分、工具新增、存储迁移或 Agent executor 变更做源码级设计评审。

### 关键概念

- HTTP/SSE 行为契约；
- 工具风险注册与最小权限；
- 幂等、重试、取消与 checkpoint；
- 结构化证据和可解释 RCA；
- 数据库/文件/向量库一致性；
- 组件级测试与端到端测试分工。

### 里程碑

选择一个模块，产出一份包含调用图、风险、测试矩阵和回滚步骤的 ADR。

### 练习

为“新增一个可写 Redis Agent 工具”做评审：

1. 工具放在哪个 `tool_modules`；
2. 如何定义参数 schema；
3. risk registry 如何标记；
4. `ask` 模式是否对模型可见；
5. 执行前如何二次确认目标集群与 Key；
6. RBAC 和资源范围如何校验；
7. 如何脱敏日志；
8. 如何审计与回滚；
9. 需要哪些单元/契约/端到端测试。

### 常见错误

- 只在 prompt 中写“请小心”；
- 只有端到端测试，没有风险函数和 schema 的单元测试；
- 新增存储却没有失败补偿和数据迁移；
- SSE 只验证文本，不验证事件顺序与结束语义。

### 自检问题

怎样证明一个新的 Agent 写工具在 UI、Router、模型可见性、执行保护、审计和测试六个层面都安全闭环？

## 推荐源码阅读顺序

```text
1. README.md / docker-compose.yml
2. backend/main.py / backend/state.py / backend/db.py
3. backend/auth/middleware.py / deps.py / service.py
4. frontend/src/main.js / App.vue / router/index.js / api/index.js
5. backend/routers/logs.py / loki_client.py
6. frontend/src/views/LogAnalysis.vue
7. backend/routers/reports.py / report_builder.py / report_store.py
8. backend/routers/agent.py / agent/graph.py / agent/tools.py
9. backend/agent/tool_modules/
10. backend/services/rca_localizer.py / rca_engine.py / evidence.py
11. backend/services/knowledge_graph.py
12. backend/routers/kubernetes.py / observability.py
13. cli/index.mjs
14. backend/tests/ 中对应测试
```

## 源码阅读记录模板

```markdown
# 功能/问题

## 用户入口
- 页面/CLI/Webhook/Scheduler：
- 触发动作：

## API 契约
- Method + Path：
- 请求字段：
- 登录、模块权限、资源范围：
- JSON/SSE/文件响应：

## 调用链
1.
2.
3.

## 外部依赖
- Loki/Prometheus/SkyWalking/K8s/...：
- 查询语句或目标资源：

## 状态变化
- DB：
- Redis：
- data/reports：
- Neo4j/Milvus：
- 页面本地状态：

## 失败与恢复
- 超时/重试：
- 取消：
- 幂等：
- 审计：
- 降级行为：

## 验证证据
- 日志：
- 测试：
- 实际响应：
```

## 下一步

推荐从 Level 3 开始：选择“日志 AI 分析”或“Agent 查询 Prometheus”中的一条链，在不修改源码的前提下，用模板完成一次端到端源码复述。

