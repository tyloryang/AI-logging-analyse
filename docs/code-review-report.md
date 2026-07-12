# 全量代码审查与修复报告

审查日期：2026-07-12

## 1. 审查范围

- 后端：FastAPI 路由、认证与会话、权限、Webhook、Agent、SSH、数据库迁移、外部 HTTP 客户端。
- 前端：Vue 页面渲染、动态 HTML、API 调用、构建配置和生产 Nginx 配置。
- 工具：`cli` 与 `github-export/cli-wechat-codex-bridge` 的源码和依赖锁文件。
- 部署：Dockerfile、Docker Compose、Kubernetes 清单、部署脚本和环境变量样例。
- 质量：单元测试、Python 编译、依赖一致性、前端/CLI 构建、npm 安全审计、YAML 解析和 CodeGraph 索引。

## 2. 结论

审查发现的阻断级和高风险问题已完成修复。当前代码在本地可完成后端全量测试、前端生产构建、CLI 构建和依赖审计；未发现仍需阻断发布的已知代码问题。

## 3. 发现与修复

| 等级 | 审查项 | 原问题 | 修复结果 |
|---|---|---|---|
| 严重 | 全局身份认证 | 多个业务路由未统一要求登录，可被匿名访问 | 新增全局认证中间件，仅保留健康检查、登录注册和受独立 token 保护的入口 |
| 严重 | 高风险操作授权 | 集群配置、任务执行、中间件连接等接口权限边界不一致 | 配置与命令类路由统一要求管理员；SSH 与 Agent 操作增加模块权限检查 |
| 高 | Webhook 认证 | 外部事件、Alertmanager、飞书入口在 token 未配置时可能放行 | 统一改为失败关闭，使用常量时间比较，并提供仅供开发显式开启的例外开关 |
| 高 | 会话安全 | Redis 故障会静默降级为进程内会话，可能导致多实例认证状态不一致 | 默认禁止运行时降级，仅在显式设置 `SESSION_ALLOW_MEMORY_FALLBACK=1` 时允许 |
| 高 | Cookie 与跨站请求 | HTTPS Cookie 判断和跨站写请求保护不足 | 根据 HTTPS/代理协议设置 Secure Cookie；对 Cookie 认证的跨站写请求执行来源校验 |
| 高 | 登录暴力破解 | 仅按用户名计数，不存在用户可绕过账号锁定 | 增加按来源的失败窗口限制，并区分反向代理后的客户端来源 |
| 高 | 前端 XSS | AI 文本、模板结果和报告内容直接进入 `v-html` | 所有动态内容先 HTML 转义，再进行受控高亮和换行渲染 |
| 高 | Agent 路径越界 | 工作区参数可读取或写入任意本地目录 | 工作区限制到仓库根目录或 `AIOPS_AGENT_WORKSPACE_ROOTS` 明确允许的目录 |
| 高 | 凭据泄露 | Service Account token 和模型密钥可能出现在配置响应中 | 所有公开响应只返回脱敏值和 `*_set` 状态，不修改持久化原值 |
| 高 | SSH 主机校验 | AsyncSSH 默认关闭 known_hosts 校验，存在中间人风险 | 默认启用主机密钥校验；仅允许通过环境变量显式关闭 |
| 高 | 外部 TLS | Jenkins 客户端默认跳过证书校验 | 默认启用 TLS 校验，仅保留显式开发开关 |
| 高 | 固定凭据 | Compose、Kubernetes、部署脚本和文档包含弱密码或默认密码 | 删除固定密码，改为外部 Secret、空值自动生成或部署时强制提供 |
| 高 | JavaScript 依赖 | Axios、Vite、ws、esbuild、Anthropic SDK 及传递依赖存在已知漏洞 | 升级直接依赖和锁文件；三个 npm 项目审计均为 0 漏洞 |
| 中 | Python 依赖冲突 | Drain3 固定要求 `cachetools==4.2.1`，与 PyMilvus 2.6 冲突 | 固定 cachetools，并将可选 PyMilvus 约束到兼容的 2.5 系列 |
| 中 | 数据库兼容性 | 启动迁移使用 SQLite 专用 `PRAGMA` | 改用 SQLAlchemy Inspector，支持 SQLite、MySQL 和 PostgreSQL 的列检查 |
| 中 | HTTP 可用性 | AI 请求缺少明确超时，外部服务异常时可能长期挂起 | 为 AI HTTP 客户端增加 120 秒显式超时 |
| 中 | 镜像构建 | Dockerfile 复制不存在的 `config/` 目录 | 移除无效 COPY，保留实际存在的内嵌配置文件 |
| 中 | 生产响应头 | Nginx 缺少基础安全头和代理协议透传 | 增加 nosniff、同源 frame、Referrer、Permissions Policy 和转发协议/地址头 |
| 中 | CORS | Cookie 模式仍可能配置 `*` | 运行时忽略通配来源并记录安全告警；部署样例改为同源默认 |

## 4. 验证结果

- Python：`compileall` 通过。
- Python 依赖：`pip check` 返回 `No broken requirements found`。
- 后端测试：100 项全部通过。
- 前端：Vite 7.3.6 生产构建通过。
- CLI：esbuild 生产构建通过。
- npm 审计：前端、CLI、桥接项目均为 0 漏洞。
- 配置：Docker Compose 与 17 个 Kubernetes YAML 文件均可解析。
- 差异质量：`git diff --check` 通过，仅有 Windows 换行提示。
- CodeGraph：同步完成，`pendingChanges` 为 0。

## 5. 发布前操作

- 必须设置 `EVENTS_INGEST_TOKEN`、`ALERTS_INGEST_TOKEN` 和 `FEISHU_BOT_VERIFY_TOKEN`；未设置时对应入口会返回 503。
- 必须在集群外创建 `aiops-secret`/`grafana-secret`，不要将真实密码提交到仓库。
- HTTPS 部署应设置 `SESSION_COOKIE_SECURE=1`，并确保入口代理透传 `X-Forwarded-Proto`。
- SSH 目标的主机密钥应预先写入系统 known_hosts，或通过 `SSH_KNOWN_HOSTS` 指定文件。
- 多实例生产环境必须提供 Redis，不应启用会话内存降级。

## 6. 环境限制

- 当前机器没有可用的 Docker CLI，因此未执行实际镜像构建；Dockerfile 的构建上下文路径已逐项校验。
- 未连接真实 Loki、Prometheus、Jenkins、Kafka、Elasticsearch、Kubernetes 和飞书服务，相关外部集成仍需在预发布环境执行连通性验证。
- Windows 环境中的 `bash` 命令不可用，未运行 `bash -n deploy.sh`；脚本变更仅涉及环境变量默认值。
