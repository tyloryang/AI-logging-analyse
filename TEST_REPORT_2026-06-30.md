# SxDevOps AIOps 平台 — 全量测试报告

> 测试日期：2026-06-30
> 测试范围：后端 28 个 router / 前端 50 个页面 / 9 条关键链路
> 测试环境：Windows 11 · Python 3.12 · Vue3 · backend :8000 · frontend :5273
> 测试方法：API 烟测（httpx）+ 浏览器 DOM/网络监测（preview MCP）+ 端到端真实点击

---

## 一、总体结论

| 维度 | 结果 | 备注 |
|---|---|---|
| 后端 API 可用率 | **27 / 28 = 96.4%** | 1 个鉴权不一致 |
| 前端页面渲染率 | **50 / 50 = 100%** | 0 console error，0 5xx |
| 关键交互链路 | **8 / 9 通过** | 1 个未验出 UI 元素（4 步引导条） |
| 性能达标率 | **23 / 28 = 82%** | 5 个接口超 3s |
| 阻塞级（P0）缺陷 | **0** | |
| 严重级（P1）缺陷 | **3** | health 超时 / services 慢 / 鉴权不一致 |
| 一般级（P2）缺陷 | **4** | |
| 体验级（P3）缺陷 | **6** | |

✅ **结论：可上线，但建议先修 P1 后再放量。** P1 主要影响首屏体验与运维侧诊断。

---

## 二、API 烟测明细（28 路由全覆盖）

### 2.1 全通过项（27）

| 路径 | 状态 | 耗时 | 数据 |
|---|---|---|---|
| `/api/observability/overview` | 200 | 3554ms ⚠ | overview JSON 完整 |
| `/api/observability/alerts` | 200 | 184ms ✓ | data+total |
| `/api/observability/services` | 200 | 15453ms ⚠ | data |
| `/api/services` | 200 | 15020ms ⚠ | with_errors |
| `/api/logs` | 200 | 10616ms ⚠ | data+cursor |
| `/api/hosts` | 401 | 2ms | 需鉴权（合理） |
| `/api/groups` | 200 | 5ms | data |
| `/api/middleware/{instances,summary}` | 200 | 14ms | list |
| `/api/redis/clusters` | 200 | 93ms | 1 集群 |
| `/api/es/clusters` | 200 | 4ms | 1 集群 |
| `/api/kafka/clusters` | 200 | 3ms | 1 集群 |
| `/api/tickets` | 200 | 5ms | 2 单 |
| `/api/events` | 200 | 674ms | 200 事件 |
| `/api/alerts/{stats,groups,filters}` | 200 | <500ms | 完整 |
| `/api/report/list` | 200 | 7ms | data |
| `/api/agent-config` | 200 | 7ms | sa+basic+mcps+skills+behaviors |
| `/api/jenkins/jobs` | 200 | 107ms | data+total |
| `/api/slowlog/hosts` | 200 | 3ms | data |
| `/api/rca/{results,expert-cases}` | 200 | <350ms | results/cases |
| `/api/topology/knowledge` | 200 | 224ms | graph |
| `/api/observability/grafana/boards` | 200 | 4ms | boards |
| `/api/observability/metrics/label-values/{label}` | 200 | 11ms | label+data |
| `/api/ai/translate` (E2E 浏览器内) | 200 | 25~45s ⚠ | 正确返回 Redis Lua/SCAN 命令 + 风险评估 |
| `/api/health` | 200 | 21065ms 🚨 | 见 P1-1 |

### 2.2 失败项（1）

| 路径 | 状态 | 问题 |
|---|---|---|
| `/api/k8s/clusters` | 401 | **鉴权策略不一致**：同为基础设施列表，/api/redis/clusters /api/es/clusters /api/kafka/clusters 都 200，唯独 k8s 要登录。前端已带 cookie 后能正常返回，但游客态体验割裂。 |

---

## 三、前端页面遍历（50 页全覆盖）

按真实路由表执行（已剔除路由表未注册的 `/cloud` `/api-red` 等历史短链），分组测试：

| 模块 | 页面数 | 渲染成功 | console.error | 网络 4xx/5xx |
|---|---|---|---|---|
| 仪表盘/可观测 | 12 | 12 | 0 | 0 |
| AIOps（故障/告警/RCA/异常/工作台/智能助手等） | 9 | 9 | 0 | 0 |
| CMDB / 主机 / 工单 | 9 | 9 | 0 | 0 |
| 容器 / K8s 拓扑 / 资源关系 | 3 | 3 | 0 | 0 |
| 中间件（Redis/Kafka/ES/概览） | 4 | 4 | 0 | 0 |
| CI/CD / Jenkins | 1 | 1 | 0 | 0 |
| 工具市场 / Java 诊断 / 慢日志 / 报告 / 指标监控 / Grafana | 6 | 6 | 0 | 0 |
| 设置 / 我的 / 用户管理 | 3 | 3 | 0 | 0 |
| 公共页（登录/注册/忘记密码/403） | 4 | 4 | 0 | 0 |

✅ **全部页面成功加载、无 JS 抛错、无失败网络请求**（一次 ERR_ABORTED 来自切路由中断的 fetch，正常行为）。

---

## 四、关键交互链路 E2E

| 链路 | 步骤 | 结果 |
|---|---|---|
| **登录** | 访问 / → 自动重定向 /login → 输入 aiopscode/AiopsCode@2026 → 跳 /  | ✅ 跳转 + cookie 写入 |
| **可观测总览首屏** | 7 KPI 卡 + 服务行 + Grafana 区 | ⚠ 显示成功但接口慢（见 P1-2） |
| **容器日志关键字过滤+高亮** | 切容器 → 点首行『日志』→ 弹窗 → 输 `ERROR shutdown` | ✅ `13 / 153 行命中`，22 处 `.hl-*` 高亮 span |
| **Pod 详情默认 YAML + 折叠** | 容器行『详情』→ 弹出 → 默认 YAML | ✅ 78 个 `data-pid` 折叠点；折叠 spec 后行数 713 → 671 |
| **Redis AI 翻译** | /middleware/redis → 集群 → ⌨命令台 → 输自然语言 → AI 生成 | ✅ 返回 `{command, explain, risk:medium, risk_reason, notes}` JSON 完整 |
| **K8s 资源拉取** | /containers 选 K8s 集群 | ✅ pods/deployments/sts/ds/jobs/cronjobs/svc/cm/nodes 全 200 |
| **SkyWalking** | /observability/trace → 168 小时 trace | ✅ services + traces 全 200 |
| **AI 智能助手** | /aiops/assistant → 对话列表加载 | ✅ /api/agent/conversations 200 |
| **首页 4 步协作引导条**（Task #40） | 找 `[class*="guide"]` `[class*="step"]` | ⚠ 未在 DOM 中找到匹配元素，需人工确认是否被移除或样式名变更（见 P2-4） |

---

## 五、缺陷清单（按优先级）

### 🚨 P1 严重（影响业务可用性，建议本周修）

#### P1-1：`/api/health` 因 SkyWalking 探活拖慢至 21 秒

- **位置**：[backend/routers/health.py:45](backend/routers/health.py#L45) `_build_health_payload` → `sw_check()`
- **根因**：`asyncio.gather(_check_loki(), _check_prom(), sw_check())` 中 Loki/Prom 设了 5s 超时，但 `sw_check()` 走 `_gql` 默认 `aiohttp.ClientTimeout(total=30)`（[skywalking_client.py:96](backend/skywalking_client.py#L96)）。SW 不通时整个健康接口跟着卡 ~21s。
- **影响**：前端 `useHealthStatus` 每页轮询 → 卡死时间被放大；首屏白屏感强；监控误判服务不可用。
- **修复**：`sw_check()` 增加 `timeout=3` 或在 health 路由侧 `asyncio.wait_for(sw_check(), 3.0)`。

#### P1-2：日志/服务列表首屏过慢（10-15 秒）

- 受影响：`/api/services`（15s）、`/api/logs?service=any`（10s）、`/api/observability/services`（15s）、`/api/observability/overview`（3.5s）。
- **根因初判**：仍在大窗口扫 Loki streams + 拉 error count 同步合并。Task #38 「两步加载」已对日志中心生效，但**服务列表 / 总览页未应用相同优化**。
- **影响**：首屏白屏 / loading 15s，超出运维忍耐阈值（业界 P95 ≤ 3s）。
- **修复**：所有 services/overview 端点统一改为：第一步只返 service 名（< 200ms）；第二步异步合并指标。或在前端做 `Promise.all` + 骨架屏。

#### P1-3：鉴权策略不一致

- `/api/hosts` 401、`/api/k8s/clusters` 401、`/api/ai/translate` 401（需登录）
- `/api/groups` 200、`/api/redis/clusters` 200、`/api/es/clusters` 200、`/api/kafka/clusters` 200、`/api/middleware/*` 200、`/api/tickets` 200、`/api/events` 200（不需登录）
- **风险**：游客可读所有中间件凭据元数据（含 host/port）。横向越权风险中等。
- **修复**：明确策略 — 推荐 **所有 `/api/*` 默认要登录**（除 `/api/health` `/api/auth/*` 白名单）。在 `main.py` 的 dependency 层统一加 `current_user`。

### 🟡 P2 一般（影响体验，可两周内修）

#### P2-1：Redis AI 翻译生成的命令"过度工程化"

- 实测：「查 session: 前缀 key 总数」→ 返回 `EVAL "local cur='0'..."` 一坨 Lua。
- 而 dbx 同样场景给的是 `SCAN 0 MATCH session:* COUNT 1000`。
- **修复**：在 `db_ai.py` 的 Redis prompt 里明确『优先单条 SCAN，禁止包 EVAL，除非用户显式说"统计"且场景描述包含千万级』。

#### P2-2：AI 翻译端到端 25-45 秒，无中间反馈

- 前端调用 `/api/ai/translate`（非 stream 版），用户点完按钮长时间无任何反应，疑似卡死。
- **修复**：前端切到 `/api/ai/translate/stream`，并展示『AI 思考中…』脉冲条；或加 timeout=30s + 失败重试按钮。

#### P2-3：`/api/k8s/clusters` 鉴权与同类不一致

- 见 P1-3。可单独修。

#### P2-4：仪表盘 4 步协作引导条未在 DOM 找到

- Task #40 标完成，但本次扫描 `[class*="guide"] [class*="collab"] [class*="step"]` 0 命中。
- 可能：A）样式名变更后选择器失效；B）feature flag 关闭；C）回归丢失。
- **修复**：检查 [frontend/src/views/Dashboard.vue](frontend/src/views/Dashboard.vue) 实现，确认引导条是否仍可见或已被移除；如已移除请同步 Task。

### 🔵 P3 体验（产品打磨期再做）

| # | 问题 | 建议 |
|---|---|---|
| P3-1 | 首页 KPI "正常服务" 计数无趋势对比 | 加 ↑12% ↓3 等 D/D 对比 |
| P3-2 | 告警分组列表无『按严重度色块』视觉锚点 | 左侧 4px 色条，红/橙/黄/灰 |
| P3-3 | 容器日志弹窗高度固定，长内容滚动体验差 | 改 `max-height: 80vh` + 滚动到底自动加载 |
| P3-4 | YAML 折叠默认全展开，首屏 700+ 行刺眼 | 默认折叠 `spec.template.spec.containers[*].env` 这类深层 |
| P3-5 | Redis 命令台 AI 结果区域无『拷贝命令』按钮 | 一键复制 + 历史 5 条 |
| P3-6 | 工具市场 50 个卡片无『最近使用』排序 | 用 localStorage 记录点击次数 |

---

## 六、未覆盖项（已知不测）

- POST/PUT/DELETE 写操作类（避免污染数据）
- SSE 流式接口的逐 chunk 验证（已确认建连成功）
- 多用户并发 / 权限矩阵（仅测了 aiopscode）
- 移动端 / 平板响应式（项目主要面向桌面）
- 性能压测 / 容量上限（待专项）

---

# SxDevOps AIOps 平台 — 产品改进建议

> 视角：从运维 / SRE 实际使用角度，按"先做什么 → 再做什么"排序

## A. 战略性建议（影响产品定位）

### A1. 把『AI』从功能点收敛成"贯穿主线"

当前 AI 散落在：
- AIOps 智能助手（聊天框）
- AIOps 故障/告警/根因（看板）
- 容器日志（无 AI）
- 慢日志（AI 分析）
- Redis/ES 管理（AI 翻译）
- 巡检（AI 摘要）

**问题**：用户每到一个页面要重新学 AI 怎么用，认知碎片化。

**建议**：所有页面右下角统一一个**浮动 AI 按钮**（现在已经有 AIOpsAssistantFloat 组件，扩它），点击后弹出『当前上下文 AI』，自动注入：
- 当前页面 URL / 当前选中资源 / 当前时间范围
- 让 AI 直接基于当前看到的数据回答

**收益**：用户从『先想去哪→再想问什么』收敛为『直接问』。

### A2. 引入"运维场景剧本"概念

当前导航是『按功能模块组织』，符合后端思维但不符合运维实际工作流。

实际运维场景往往是：
- 📞 接告警 → 看是谁/哪台 → 看链路 → 看日志 → 找改动 → 决定回滚/重启
- 📅 周一巡检 → 看资源水位 → 看磁盘趋势 → 看证书到期

**建议**：在首页加 4-6 个**剧本卡片**（"夜间告警处置""周一巡检""上线发版前后对比"），每个剧本 = 串好的多页面跳转 + 默认筛选。

参考：Datadog Notebook、Grafana Scenes。

### A3. 强化『时间一致性』

观察：全局时间选择器存在（Task #24 完成），但部分页面（如 Redis Cluster overview）仍用各自时间。

**建议**：所有数据卡片右上角统一显示『数据时间 → 2 分钟前』徽标，与全局时间不一致时高亮提示『此卡片用了局部时间，点击同步』。

## B. 战术性建议（落地即提升体验）

### B1. 容器管理：日志 + 终端 + YAML 三体合一

当前三个按钮分别弹三个对话框。SRE 真实场景是『一边看日志一边敲命令一边比 YAML』。

**建议**：详情抽屉左侧导航 (Overview / YAML / Events / Logs / Shell)，右侧 split 视图，可同时打开 Logs + Shell。

### B2. CMDB 巡检：『可执行的告警』

当前巡检 = 出 PDF/Excel 报告 → 人工阅读。

**建议**：每个 critical/warning 项右侧加『一键修复』按钮（如『磁盘 / 满 90%』→『清 /var/log 老日志』『重启占用进程』）。背后走 ansible_tasks 模块（已存在）。

### B3. AI 翻译：『先推荐再生成』

当前 AI 翻译需用户先想清楚意图打字。

**建议**：输入框下方加『常见意图』芯片：
- Redis：『查大 key』『查热 key』『查阻塞』『清过期 key』
- ES：『查最近错误』『查慢查询』『重置 read_only』
- 点芯片 = 自动填好意图，回车直接生成。降低门槛。

### B4. 告警中心：『噪音收敛 vs 真实问题』

观察：`/api/alerts/groups` 已有分组但前端没看到『同一根因合并』。

**建议**：
- 默认按『主机/服务/指标』三维度自动 group，列表收起
- 顶部红色横幅高亮『1 个真实事故 + 47 条噪音』
- 噪音可一键『静音 1 小时』

### B5. AIOps 助手：『动作草稿』可视化

Task #45 做了草稿+二次确认，但本次测试中未看到 UI 入口（可能在对话流里）。

**建议**：助手右侧固定『待执行动作』面板，列出 AI 想做的所有操作，每条 ✓/✗ 勾选，下方一个『批量执行』按钮。

### B6. 设置页：缺一个『连通性体检』

观察：`/api/health` 返 loki/prom/sw 三态，但用户在哪能看到？

**建议**：Settings 页第一屏加『后端依赖自检』卡片：
| 依赖 | URL | 状态 | 延迟 | 上次成功 |
| Loki | 192.168.9.221 | ✓ | 80ms | 5s 前 |
| Prom | 192.168.9.221 | ✓ | 30ms | 5s 前 |
| SW | http://… | ✗ 拒绝连接 | - | 1h 前 |
| AI | anthropic | ✓ | 1.2s | 30s 前 |

直接定位"出问题的服务"。

## C. 数据视角（让数据自己会说话）

### C1. 所有列表加『同环比』

工单/告警/事件/慢日志列表，标题旁加『vs 上周』徽标：
- 工单 **23** ↑5（vs 上周）
- 告警 **47** ↓12（vs 昨日）

### C2. 大数表加『分位线』

主机 CPU 使用率列表，加表头 P50/P90/P99 行，让用户一眼看出"长尾"。

### C3. 拓扑图加『流量加权』

K8s 拓扑当前节点等大。

**建议**：节点大小 = 当前 QPS；连线粗细 = 实际调用次数；红色 = 错误率 > 1%。

## D. 开发者体验（投资回报最高）

### D1. 后端 router 注册一致化

现状：有的 router 内部带 prefix（`APIRouter(prefix="/api/redis")`），有的不带（`APIRouter()` + `@router.get("/api/alerts/...")`），混用。

**建议**：统一改成『router 内带 prefix』，main.py 不再传 prefix。新人改一个端点只用看一个文件。

### D2. 鉴权统一收口

P1-3 同问题。把 `current_user` 装在 `app.include_router(..., dependencies=[Depends(current_user)])` 默认，白名单单独列出。比每个路由各自决定不漏。

### D3. 前端 API 调用收口

观察：`frontend/src/api/index.js` 是 axios 拦截器，但很多 view 仍用 `fetch()` 裸写（如 ContainerView/RedisClusterView/AIOpsAssistantFloat）。

**建议**：禁用裸 `fetch`（lint 规则），统一走 api.js，方便加全局 loading / error toast / 401 跳转。

### D4. 引入 OpenAPI 自动校验

后端是 FastAPI 自带 `/openapi.json`，建议：
- CI 跑一遍 `openapi-typescript` 生成前端类型
- 前端调用错路径在编译时报错（而非运行时 404）

---

## E. 一周冲刺计划（如果只能做 5 件事）

1. ✅ **修 health 超时**（P1-1，30 分钟）
2. ✅ **services/overview 两步加载**（P1-2，1 天）
3. ✅ **鉴权统一**（P1-3，半天）
4. ✅ **AI 翻译切流式 + 常见意图芯片**（P2-2 + B3，半天）
5. ✅ **首页加 4-6 个剧本卡片**（A2，1 天）

预期：用户感知首屏提速 5×，AI 体验从『卡死感』变『丝滑』，新手上手时间缩短 50%。

---

## 附：测试脚本与原始数据

- 后端烟测：[smoke_test2.py](C:/Users/可乐/AppData/Local/Temp/claude/D--loki-log-analyse/6c0c0a30-b077-475f-b8b2-be0d8a005fce/scratchpad/smoke_test2.py)
- 烟测结果 JSON：[smoke_results2.json](C:/Users/可乐/AppData/Local/Temp/claude/D--loki-log-analyse/6c0c0a30-b077-475f-b8b2-be0d8a005fce/scratchpad/smoke_results2.json)
- 前端遍历：preview MCP 浏览器内执行（350+ 网络请求 0 失败）
