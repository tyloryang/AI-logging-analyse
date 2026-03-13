# 用户权限登录系统 · 设计文档

> 状态：已确认，待实现
> 日期：2026-03-13

---

## 一、背景与目标

AI Ops 平台当前所有 API 和页面完全开放，无任何认证。随着多团队共享使用，需要：

- 控制不同用户对各功能模块的访问权限
- 提供注册审批流程，由管理员管控访问入口
- 记录关键操作审计日志，满足安全合规要求

---

## 二、需求摘要

| 维度 | 决策 |
|------|------|
| 使用场景 | 多团队共享，需区分权限 |
| 权限粒度 | 模块级细粒度（none / view / operate），模块动态注册 |
| 用户注册 | 自注册 + 管理员审批 |
| 认证方式 | Session + Cookie（HttpOnly），Redis 存储，滑动过期 |
| 账号存储 | SQLAlchemy ORM，支持 SQLite / MySQL 8 / PostgreSQL |
| 安全要求 | bcrypt 哈希 + 密码复杂度 + 登录失败锁定 + 操作审计 |
| 前端页面 | 登录、注册、忘记密码、个人中心、用户管理（完整套件） |

### 非目标（当前阶段不做）

- LDAP / SSO / OAuth 外部认证对接
- 细粒度到行级数据的权限控制
- 多租户隔离

---

## 三、数据库模型

### users

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| username | VARCHAR(64) UNIQUE | |
| email | VARCHAR(128) UNIQUE | |
| password_hash | VARCHAR(128) | bcrypt |
| display_name | VARCHAR(64) | |
| status | ENUM | pending / active / locked / disabled |
| is_superuser | BOOLEAN DEFAULT false | 超管，跳过权限表检查 |
| failed_attempts | INT DEFAULT 0 | 连续登录失败次数 |
| locked_until | DATETIME NULL | 失败超限时写入 |
| created_at | DATETIME | |
| updated_at | DATETIME | |

### modules（动态模块注册）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR(64) PK | 如 `cmdb`、`ssh`、`report` |
| name | VARCHAR(128) | 显示名称 |
| description | VARCHAR(256) | |
| created_at | DATETIME | |

### permissions（用户-模块权限）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| user_id | FK → users.id | |
| module_id | FK → modules.id | |
| level | ENUM | none / view / operate |
| updated_at | DATETIME | |

### audit_logs（操作审计）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| user_id | FK → users.id NULL | NULL 表示未认证请求 |
| action | VARCHAR(128) | 如 `login`、`cmdb.update_host` |
| resource | VARCHAR(256) NULL | 操作对象标识 |
| ip | VARCHAR(64) | |
| status | ENUM | success / fail |
| detail | TEXT NULL | 附加信息（如失败原因） |
| created_at | DATETIME | |

---

## 四、Redis 数据结构

```
# Session（滑动过期）
KEY  session:{session_id}   TYPE Hash   TTL 28800s（每次请求重置）
字段：user_id / username / ip / created_at

# 登录失败计数（滑动 10 分钟窗口）
KEY  login_fail:{username}  TYPE String  TTL 600s

# 账号锁定标记（管理员解锁时 DEL）
KEY  locked:{user_id}       TYPE String  TTL 无（永久直到解锁）
```

---

## 五、认证流程

### 注册
```
用户提交 → 密码复杂度校验 → bcrypt hash → DB 写入(status=pending) → 提示等待审批
```

### 登录
```
1. 查 locked:{user_id}         → 存在则拒绝
2. bcrypt 验证密码
3. 失败 → login_fail +1；≥5次 → DB status=locked + 写 locked:{user_id}
4. 成功 → 清 login_fail → 生成 session_id → Redis HSET + EXPIRE
5. Set-Cookie: session_id=xxx; HttpOnly; SameSite=Lax
6. 写 audit_log(login, success)
```

### 请求鉴权中间件
```
Cookie 取 session_id
→ Redis GET → 不存在/过期 → 401
→ EXPIRE 重置 TTL（滑动续期）
→ 查 DB 权限（LRU 缓存 60s）
→ 注入 request.state.user
```

### 权限检查装饰器
```python
@require_permission("cmdb", "view")     # 只读
@require_permission("cmdb", "operate")  # 可操作
@require_permission("ssh",  "operate")  # SSH 连接
```

---

## 六、API 端点

### 认证
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 注册 |
| POST | `/api/auth/login` | 登录（Set-Cookie） |
| POST | `/api/auth/logout` | 登出 |
| GET  | `/api/auth/me` | 当前用户信息 + 权限 |
| PUT  | `/api/auth/password` | 修改自己密码 |

### 用户管理（admin）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET    | `/api/admin/users` | 用户列表 |
| POST   | `/api/admin/users` | 创建用户 |
| PUT    | `/api/admin/users/{id}` | 修改用户 |
| POST   | `/api/admin/users/{id}/approve` | 审批注册 |
| POST   | `/api/admin/users/{id}/unlock` | 解锁账号 |
| DELETE | `/api/admin/users/{id}` | 禁用用户 |
| GET    | `/api/admin/users/{id}/permissions` | 查看权限 |
| PUT    | `/api/admin/users/{id}/permissions` | 批量更新权限 |
| GET    | `/api/admin/modules` | 已注册模块列表 |
| GET    | `/api/admin/audit-logs` | 审计日志（分页+过滤） |

---

## 七、后端目录结构

```
backend/
├── auth/
│   ├── models.py        # User / Permission / Module / AuditLog ORM 模型
│   ├── schemas.py       # Pydantic 请求/响应模型
│   ├── router.py        # /api/auth/* 路由
│   ├── admin_router.py  # /api/admin/* 路由
│   ├── service.py       # 业务逻辑
│   ├── deps.py          # current_user / require_permission 依赖
│   ├── session.py       # Redis Session 封装
│   ├── audit.py         # 审计日志工具
│   └── password.py      # bcrypt + 复杂度校验
├── db.py                # SQLAlchemy engine（多DB支持）
├── migrations/          # Alembic 迁移文件
└── main.py              # 注册路由 + 启动初始化
```

---

## 八、前端结构

### 新增页面
| 路由 | 说明 |
|------|------|
| `/login` | 登录页 |
| `/register` | 注册页（含审批等待状态） |
| `/forgot-password` | 忘记密码（显示管理员联系方式） |
| `/profile` | 个人中心（改密码、查权限） |
| `/admin/users` | 用户管理（审批/增删/权限分配） |

### Pinia Auth Store
```javascript
{
  user: null,           // { id, username, displayName, isAdmin }
  permissions: {},      // { cmdb: 'operate', ssh: 'view', ... }
  fetchMe(),
  login(form),
  logout(),
  can(module, level),   // none < view < operate
}
```

### 路由守卫
- 白名单：`/login`、`/register`、`/forgot-password`
- 未登录 → `/login`
- 无模块权限 → `/403`（就地提示，不跳转登录）
- 侧边栏菜单按权限动态显示/隐藏

---

## 九、Docker Compose 更新

```yaml
services:
  backend:
    depends_on:
      redis: { condition: service_healthy }

  redis:
    image: redis:7-alpine
    volumes: [redis_data:/data]
    command: redis-server --appendonly yes
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]

  mysql:           # profiles: [mysql]
    image: mysql:8

  postgres:        # profiles: [postgres]
    image: postgres:16-alpine
```

### 启动命令
```bash
docker compose up -d --build                    # SQLite（默认）
docker compose --profile mysql up -d --build    # MySQL
docker compose --profile postgres up -d --build # PostgreSQL
```

---

## 十、.env 新增配置

```env
DATABASE_URL=sqlite+aiosqlite:///./data/aiops.db
REDIS_URL=redis://redis:6379/0
ADMIN_USERNAME=admin
ADMIN_PASSWORD=Admin@123456
SESSION_TTL_SECONDS=28800
LOGIN_FAIL_MAX=5
LOGIN_FAIL_WINDOW=600
```

---

## 十一、初始化流程（启动时自动执行）

```
1. Alembic upgrade head（自动建表/迁移）
2. 同步 modules 表（upsert 代码中声明的模块）
3. 检查是否存在 active 用户
   └─ 无 → 从 .env 创建初始 admin
          → .env 未配置 → 随机生成密码打印到启动日志（仅一次）
```

---

## 十二、预置模块列表

| module_id | 显示名称 |
|-----------|---------|
| dashboard | 仪表盘 |
| log | 日志分析 |
| metrics | 指标监控 |
| alert | 告警历史 |
| report | 分析报告 |
| cmdb | 主机 CMDB |
| inspect | 主机巡检 |
| ssh | SSH 终端 |
| admin | 用户管理 |

> 新增模块只需在代码中的 `MODULES` 列表追加一条记录，启动时自动注册，无需改表。

---

## 十三、决策日志

| # | 决策 | 备选 | 理由 |
|---|------|------|------|
| 1 | 细粒度模块权限 | 两/三级角色 | 多团队场景灵活，动态注册保证可扩展 |
| 2 | 自注册 + 审批 | 仅管理员创建 | 降低管理员负担，保持访问控制 |
| 3 | Session + Cookie | JWT | 权限变更实时生效，无延迟问题 |
| 4 | Redis 存 Session | 纯内存/DB | 高性能、天然 TTL、滑动过期简单 |
| 5 | SQLAlchemy 多DB | 纯 JSON/Redis | 事务安全、复杂查询、一行切换 |
| 6 | Alembic 自动迁移 | 手动建表 | Docker 启动自动升级，零运维 |
| 7 | 失败 5 次锁定 + 审计 | 仅计数 | 防暴力破解，留存操作记录 |
| 8 | 403 就地提示 | 跳回登录页 | 已登录用户权限不足跳登录会困惑 |
| 9 | admin 从 .env 读取或随机生成 | 固定默认密码 | 避免默认密码未改带来安全隐患 |
