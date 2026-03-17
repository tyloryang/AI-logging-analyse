# AI Ops · 智能运维平台

> 基于 **Loki + Prometheus + AI 大模型** 的一站式智能运维平台
>
> 日志分析 · 慢日志分析 · 主机巡检 · SSH 终端 · 运维日报 · 飞书/钉钉推送 · 用户权限管理

![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.11+-green)
![Vue](https://img.shields.io/badge/vue-3.x-brightgreen)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)

---

## 界面预览

### 仪表盘
![仪表盘](HomePage.png)
*系统总览：总日志数、错误数、服务健康状态矩阵，24 小时内一览无余*

### AI 分析报告
![AI 分析报告](AIanalyse.png)
*一键生成运维日报，AI 流式输出健康评分、Top 错误服务和处置建议*

### 飞书推送
![飞书推送](FeishuReport.png)
*AI 分析结果自动推送飞书/钉钉，支持定时推送和手动触发*

### SSH 终端
![SSH 终端](ssh界面.png)
*浏览器内直连主机 Web Terminal，凭证统一管理，支持多标签*

---

## 功能特性

| 模块 | 功能 |
|------|------|
| **仪表盘** | 系统总览、错误 Top10 服务、服务健康状态矩阵 |
| **日志分析** | 按服务/级别/关键字过滤、Loki 实时查询、AI 流式分析、Drain3 模板聚类 |
| **指标监控** | 各服务错误数趋势、汇总统计 |
| **告警历史** | 基于错误日志自动生成告警，按严重程度分级 |
| **分析报告** | 一键生成运维日报，AI 流式输出，历史持久化，飞书/钉钉推送 |
| **定时推送** | APScheduler 按 cron 自动生成运维日报 + 主机巡检日报并推送，无需外部 cron |
| **主机 CMDB** | Prometheus 自动发现主机，采集 CPU/内存/磁盘/网络/负载指标，可编辑责任人/环境/角色 |
| **主机巡检** | 阈值巡检（CPU/内存/磁盘/负载），AI 逐台列出异常 IP 和问题，一键导出 Excel |
| **慢日志分析** | SSH 读取 MySQL 8 慢查询日志，时间段过滤，drain3 SQL 模板聚合，AI 流式优化建议 |
| **SSH 终端** | 浏览器内 Web Terminal，凭证库 AES 加密存储，多标签，一键连接 |
| **用户权限** | 注册审批、模块级权限（view/operate）、登录失败锁定、操作审计日志 |

---

## 技术架构

```
┌───────────────────────────────────────────────────────────────┐
│                    浏览器  Vue 3 + Vite                        │
│  Dashboard · LogAnalysis · Metrics · Alerts · Report          │
│  HostCMDB (CMDB + 巡检 + SSH 终端)                            │
│  Login / Register / AdminUsers (用户权限管理)                  │
│                  Pinia · Axios · SSE                           │
└──────────────────────────┬────────────────────────────────────┘
                           │ HTTP / SSE / WebSocket
┌──────────────────────────▼────────────────────────────────────┐
│                FastAPI  Python 3.11+                           │
│  routers/                  auth/                               │
│  ├── logs.py               ├── router.py   /api/auth/*        │
│  ├── reports.py            ├── admin_router.py                │
│  ├── hosts.py              ├── service.py  (注册/审批/权限)    │
│  ├── ssh.py                └── session.py  (Redis Session)    │
│  ├── slowlog.py            # /api/slowlog/* (慢查询分析)       │
│  └── health.py                                                 │
│  state.py (共享单例)   scheduler.py (定时任务)                  │
│  slow_log_parser.py (MySQL 8 慢日志解析)                       │
│  sql_cluster.py     (drain3 SQL 模板聚合)                      │
└───────┬──────────────────────────────┬────────────────────────┘
        │                              │
┌───────▼──────────┐   ┌──────────────▼───────────────────────┐
│  外部服务         │   │  本地存储                              │
│  Loki  (日志)    │   │  SQLite / MySQL 8 / PostgreSQL 16      │
│  Prometheus      │   │  (用户/权限/审计日志)                   │
│  (指标+主机发现) │   │                                        │
│  AI Provider     │   │  Redis  (Session + 登录失败计数)       │
│  (Claude/OpenAI) │   │                                        │
│  飞书 / 钉钉     │   │  ./reports/  (日报 JSON)               │
└──────────────────┘   │  ./data/     (SQLite 数据库)           │
                       └──────────────────────────────────────┘
```

---

## 快速开始

### 环境要求

**Docker 部署（推荐）**
- Docker 24+ 和 Docker Compose v2

**直接启动（开发/测试）**
- Python 3.11+
- Node.js 18+

**外部依赖**
- 可访问的 Loki 服务
- 可访问的 Prometheus 服务（主机需部署 `node_exporter`）
- AI Provider 之一（见配置说明）

---

### 1. 克隆项目

```bash
git clone https://github.com/your-org/aiops.git
cd aiops
```

### 2. 配置 .env

```bash
cd backend
cp .env.example .env
```

编辑 `.env`，至少填写以下必填项：

```env
# ── 必填 ─────────────────────────────────────────────
LOKI_URL=http://your-loki-host:3100
PROMETHEUS_URL=http://your-prometheus-host:9090

# ── AI Provider（二选一）────────────────────────────
# 选项 A：Anthropic Claude
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
AI_MODEL=claude-opus-4-6

# 选项 B：本地 / 第三方 OpenAI 兼容接口
AI_PROVIDER=openai
AI_BASE_URL=http://192.168.x.x:8000/v1
AI_API_KEY=
AI_MODEL=Qwen3-32B

# ── 初始管理员（首次启动自动创建）───────────────────
ADMIN_USERNAME=admin
ADMIN_PASSWORD=Admin@123456

# ── Redis（Docker 部署时默认已包含）─────────────────
REDIS_URL=redis://redis:6379/0
```

其余可选配置见 [.env.example](backend/.env.example)。

### 3. 启动

#### 方式一：Docker Compose（推荐生产）

```bash
# 默认 SQLite
docker compose up -d --build

# 使用 MySQL 8
docker compose --profile mysql up -d --build

# 使用 PostgreSQL 16
docker compose --profile postgres up -d --build
```

访问 http://localhost，使用 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 登录。

#### 方式二：Linux 直接启动（开发/测试）

```bash
chmod +x start.sh && ./start.sh
```

或分别启动：

```bash
# 后端（:8000）
cd backend && pip install -r requirements.txt && python3 main.py

# 前端（:5173，新开终端）
cd frontend && npm install && npm run dev
```

访问 http://localhost:5173

---

## 配置说明

完整配置项见 [`backend/.env.example`](backend/.env.example)，以下列出常用项：

### AI Provider

| Provider | 配置 | 场景 |
|----------|------|------|
| Anthropic Claude | `AI_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` | 云端，推理能力强 |
| Qwen3 / vLLM | `AI_PROVIDER=openai` + `AI_BASE_URL` | 本地部署，数据不出内网 |
| Ollama | `AI_PROVIDER=openai` + `http://host:11434/v1` | 本地一键部署（Docker 内需填宿主机 IP，不能用 localhost） |
| DeepSeek | `AI_PROVIDER=openai` + DeepSeek API URL | 低成本云端 |

> 任何支持 OpenAI Chat Completions API 格式的服务均可接入。

### 数据库

| 数据库 | DATABASE_URL |
|--------|-------------|
| SQLite（默认） | `sqlite+aiosqlite:///./data/aiops.db` |
| MySQL 8 | `mysql+aiomysql://user:pass@host:3306/aiops` |
| PostgreSQL 16 | `postgresql+asyncpg://user:pass@host:5432/aiops` |

### 定时推送

```env
SCHEDULE_CRON=0 9 * * *          # 每天 09:00，使用服务器本地时间（中国服务器无需换算）
SCHEDULE_CHANNELS=feishu          # 推送渠道，多个用逗号分隔：feishu / dingtalk / feishu,dingtalk

FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
FEISHU_KEYWORD=运维               # 飞书自定义机器人关键词安全策略（消息中必须包含该词）
DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=xxx
DINGTALK_KEYWORD=运维             # 钉钉关键词安全策略（与飞书同理）
```

| cron 表达式 | 含义 |
|-------------|------|
| `0 9 * * *` | 每天 09:00 |
| `0 18 * * *` | 每天 18:00 |
| `30 8 * * 1-5` | 工作日 08:30 |
| `0 9,18 * * *` | 每天 09:00 和 18:00 |

---

## 功能使用指南

### 日志分析

1. 从顶部下拉选择服务，选择时间范围（最近 N 小时或自定义区间）
2. 可按日志级别（error / warn / info）和关键字过滤
3. 点击 **AI 分析** 触发流式 AI 分析，AI 会列出根因和处置建议
4. 切换 **模板聚类** 标签，查看 Drain3 自动归纳的日志模板（高频模式一目了然）

### 运维日报 + 定时推送

- **手动生成**：进入「分析报告」→ 点击「立即生成日报」，AI 流式输出健康评分和分析
- **手动推送**：报告生成后点击「飞书推送」或「钉钉推送」
- **定时自动推送**：配置 `SCHEDULE_CRON` 和 `SCHEDULE_CHANNELS`，后端自动在指定时间推送运维日报 + 主机巡检日报，无需手动操作

### 主机巡检

1. 进入「CMDB 巡检」→ 切换「巡检报告」标签
2. 点击「全量巡检」，系统从 Prometheus 拉取最新指标并对每台主机执行阈值检查
3. 点击「AI 分析」，AI 会逐台列出每个异常主机的 IP 和具体问题（如 `192.168.1.10：CPU 使用率 91%`）
4. 点击「下载 Excel」导出三页式报告（巡检概况 / 全部主机明细 / 异常项明细）

### MySQL 慢日志分析

1. 进入「慢日志分析」页面
2. **配置凭证**（三种方式任选）：
   - **CMDB 自动**：主机在 CMDB 中已绑定凭证，直接选择目标 IP 即可
   - **凭证库**：从凭证管理库中选择已保存的凭证
   - **手动输入**：直接填写用户名和密码（一次性使用）
3. **添加分析目标**：在 IP 输入框中输入主机 IP（支持 CMDB 主机自动补全），可批量添加多台主机
4. **设置时间段**：选择 `起始日期` 和 `结束日期`，或使用快捷按钮（今天 / 昨天 / 近7天 / 近30天 / 不限）
5. 点击「**获取并解析**」，系统并行 SSH 读取所有目标主机的慢日志文件并解析
6. 结果按主机分 Tab 展示，可切换「**慢查询列表**」「**SQL 聚合**」「**AI 分析建议**」三个视图：
   - **慢查询列表**：按耗时排序，可展开查看完整 SQL
   - **SQL 聚合**：drain3 自动识别 SQL 模板，统计次数 / 总耗时 / 最大耗时 / 扫描行数
   - **AI 分析建议**：流式输出 AI 对 Top 慢查询的根因分析和加索引/改写 SQL 等优化建议

> **注意**：凭证信息在页面刷新后通过 sessionStorage 保留，无需重复输入。需要确保 SSH 账号有读取 MySQL 慢日志文件的权限。

### SSH 终端

1. 进入「CMDB 巡检」→ 切换「SSH 终端」标签
2. 点击主机旁的「SSH」按钮，或在终端顶部手动输入 IP 新建连接
3. 首次连接需要凭证：点击「凭证管理」添加用户名/密码，凭证以 AES 加密存储
4. 也可在「主机 CMDB」页为每台主机绑定指定凭证，下次一键直连

### 用户权限管理

**注册流程**：用户自行注册 → 状态为 `pending` → 管理员审批后激活

**管理员操作**：进入「用户管理」页面：
- 审批待注册用户
- 为每位用户按模块分配权限（`none` / `view` / `operate`）
- 解锁因登录失败超限而锁定的账号

**权限模块**：`dashboard` · `log` · `metrics` · `alert` · `report` · `cmdb` · `inspect` · `ssh` · `slowlog` · `admin`

---

## 项目结构

```
aiops/
├── backend/
│   ├── main.py              # FastAPI 应用入口 + lifespan（~100 行）
│   ├── state.py             # 共享单例（loki/prom/analyzer）和配置常量
│   ├── scheduler.py         # APScheduler 定时任务（日报 + 巡检日报推送）
│   ├── db.py                # SQLAlchemy 异步引擎（多数据库支持）
│   ├── routers/
│   │   ├── logs.py          # /api/logs /api/services /api/analyze /api/metrics
│   │   ├── reports.py       # /api/report/* （日报 + 巡检日报 + Excel + 推送）
│   │   ├── hosts.py         # /api/hosts/* （CMDB + 巡检）
│   │   ├── ssh.py           # /api/ssh/* + WebSocket /api/ws/ssh
│   │   ├── slowlog.py       # /api/slowlog/* （MySQL 慢查询日志分析）
│   │   └── health.py        # /api/health
│   ├── auth/
│   │   ├── models.py        # User / Permission / Module / AuditLog ORM 模型
│   │   ├── router.py        # /api/auth/* （登录/注册/登出/改密）
│   │   ├── admin_router.py  # /api/admin/* （用户管理/权限分配/审计日志）
│   │   ├── service.py       # 注册/登录/权限业务逻辑
│   │   ├── deps.py          # current_user / require_permission FastAPI 依赖
│   │   ├── session.py       # Redis Session 封装（滑动 TTL）
│   │   ├── audit.py         # 操作审计日志工具
│   │   └── password.py      # bcrypt 哈希 + 密码复杂度校验
│   ├── loki_client.py       # Loki HTTP API v1 客户端
│   ├── prom_client.py       # Prometheus HTTP API 客户端（主机发现 + 指标采集）
│   ├── ai_analyzer.py       # AI 分析器（Provider 抽象层，支持 Anthropic / OpenAI）
│   ├── ssh_bridge.py        # WebSocket ↔ asyncssh 桥接（SSH 终端后端）
│   ├── log_clusterer.py     # Drain3 日志模板聚类
│   ├── slow_log_parser.py   # MySQL 8 慢日志解析器（iter/parse/build_summary）
│   ├── sql_cluster.py       # Drain3 SQL 模板聚合（脱敏 → 聚类 → 统计）
│   ├── notifier.py          # 飞书 / 钉钉 Webhook 推送
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── views/
│   │   │   ├── Dashboard.vue        # 仪表盘
│   │   │   ├── LogAnalysis.vue      # 日志分析 + AI 分析 + 模板聚类
│   │   │   ├── MetricsMonitor.vue   # 指标监控
│   │   │   ├── AlertHistory.vue     # 告警历史
│   │   │   ├── AnalysisReport.vue   # 运维日报
│   │   │   ├── HostCMDB.vue         # 主机 CMDB + 巡检 + SSH 终端
│   │   │   ├── SlowLogView.vue      # MySQL 慢日志分析（多主机 + 聚合 + AI 建议）
│   │   │   ├── LoginView.vue        # 登录页
│   │   │   ├── RegisterView.vue     # 注册页
│   │   │   ├── AdminUsers.vue       # 用户管理（管理员）
│   │   │   └── ProfileView.vue      # 个人中心（改密码 + 查权限）
│   │   ├── stores/
│   │   │   └── auth.js              # Pinia 认证 Store（user / permissions / can()）
│   │   ├── router/index.js          # 路由守卫（未登录跳登录页，无权限显示 403）
│   │   ├── api/index.js             # HTTP + SSE 封装，401 自动跳转登录
│   │   └── components/
│   │       └── Sidebar.vue          # 侧边栏（按权限动态显示菜单）
│   ├── nginx.conf           # 生产环境 Nginx（SSE + WebSocket 支持）
│   └── Dockerfile
├── docker-compose.yml       # 一键部署（含 Redis，可选 MySQL / PostgreSQL）
├── start.sh                 # Linux 直接启动脚本
└── README.md
```

---

## API 接口

### 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 用户注册（status=pending，等待审批） |
| POST | `/api/auth/login` | 登录（Set-Cookie: session_id） |
| POST | `/api/auth/logout` | 登出 |
| GET  | `/api/auth/me` | 当前用户信息 + 权限列表 |
| PUT  | `/api/auth/password` | 修改密码 |

### 日志

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/services` | 服务列表及错误数 |
| GET | `/api/logs` | 查询日志（服务/级别/关键字/时间范围） |
| GET | `/api/logs/errors` | 全量错误日志 |
| GET | `/api/logs/templates` | Drain3 模板聚类 |
| GET | `/api/metrics/errors` | 各服务错误数统计 |
| GET | `/api/analyze/stream` | **流式** AI 日志分析（SSE） |

### 报告

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/api/report/generate` | **流式** 生成运维日报（SSE） |
| GET  | `/api/report/list` | 历史报告列表 |
| GET  | `/api/report/{id}` | 报告详情 |
| POST | `/api/report/{id}/notify` | 推送到飞书 / 钉钉 |
| GET  | `/api/report/inspect/generate` | **流式** 生成主机巡检日报（SSE） |
| GET  | `/api/report/inspect/{id}/excel` | 下载巡检日报 Excel |

### 主机

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/api/hosts` | 主机列表（Prometheus 发现 + CMDB + 实时指标） |
| PUT  | `/api/hosts/{instance}` | 更新 CMDB 信息（责任人/环境/SSH 凭证） |
| GET  | `/api/hosts/inspect` | **流式** 全量巡检（SSE） |
| POST | `/api/hosts/inspect/ai` | **流式** AI 巡检分析（SSE） |
| POST | `/api/hosts/inspect/excel` | 导出巡检 Excel |
| GET  | `/api/hosts/{instance}/inspect` | 单台主机巡检 |

### SSH

| 方法 | 路径 | 说明 |
|------|------|------|
| GET    | `/api/ssh/credentials` | 凭证列表 |
| POST   | `/api/ssh/credentials` | 添加凭证（AES 加密存储） |
| PUT    | `/api/ssh/credentials/{id}` | 更新凭证 |
| DELETE | `/api/ssh/credentials/{id}` | 删除凭证 |
| WS     | `/api/ws/ssh` | WebSocket SSH 终端 |

### 慢日志分析

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/api/slowlog/hosts` | 返回 CMDB 中有 SSH 凭证的主机列表 |
| POST | `/api/slowlog/fetch` | SSH 读取远端 MySQL 慢日志并解析（含 drain3 聚合） |
| GET  | `/api/slowlog/analyze/stream` | **流式** AI 慢查询优化建议（SSE） |

`POST /api/slowlog/fetch` 请求体：

```json
{
  "host_ip": "192.168.1.10",
  "log_path": "/mysqldata/mysql/data/3306/mysql-slow.log",
  "date_from": "2025-01-01",
  "date_to": "2025-01-07",
  "threshold_sec": 1.0,
  "alert_sec": 10.0,
  "credential_id": "",
  "ssh_user": "",
  "ssh_password": "",
  "ssh_port": 22
}
```

### 其他

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查（Loki / Prometheus / AI 状态） |

---

## 故障排查

### 启动后无法访问

```bash
# 检查后端是否启动
curl http://localhost:8000/api/health

# 查看 Docker 日志
docker compose logs backend
docker compose logs frontend
```

### Redis 连接失败

```
aioredis.exceptions.ConnectionError: ...
```

- Docker 部署：Redis 已内置，检查 `docker compose ps redis` 是否运行
- 直接启动：确保本地 Redis 运行，并在 `.env` 中设置 `REDIS_URL=redis://localhost:6379/0`

### 登录提示 401

- 确认 `.env` 中 `ADMIN_PASSWORD` 已在**首次启动前**设置（`ADMIN_PASSWORD=` 留空或字段不存在时触发随机密码生成）
- 若首次启动时未配置密码，系统会随机生成密码并打印到启动日志中：
  ```bash
  docker compose logs backend | grep "初始管理员"
  ```
- 或直接重置密码（数据库已存在时）：
  ```bash
  docker compose exec backend python -c "
  import asyncio
  from db import AsyncSessionLocal
  from auth.models import User
  from auth.password import hash_password
  from sqlalchemy import select
  async def reset():
      async with AsyncSessionLocal() as db:
          r = await db.execute(select(User).where(User.username=='admin'))
          u = r.scalar_one()
          u.password_hash = hash_password('Admin@123456')
          await db.commit()
          print('密码已重置')
  asyncio.run(reset())
  "
  ```

### AI 分析无响应

- 检查 `AI_PROVIDER` 和对应的 API Key / Base URL 是否正确
- 访问 `/api/health` 查看 `ai_ready` 字段
- 本地模型确认服务已启动：`curl http://your-ai-host:8000/v1/models`

### Loki / Prometheus 无数据

- 确认服务地址可达：`curl $LOKI_URL/loki/api/v1/labels`
- Prometheus 需要 node_exporter 部署在被监控主机上才能发现主机
- 检查 `.env` 中的认证配置（`LOKI_USERNAME` / `PROMETHEUS_USERNAME`）

---

## License

[MIT](LICENSE)
