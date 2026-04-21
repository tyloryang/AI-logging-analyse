# 企业级项目整理与排除清单

本文档基于当前 `loki-log-analyse` 项目扫描结果整理，用于明确源码边界、运行数据边界和可清理对象。当前只做版本控制与 Docker 构建排除规则，不直接删除本地文件。

## 当前项目定位

该项目已经具备企业级 AIOps 管理平台雏形，核心模块如下：

- `backend/`：FastAPI 后端、认证、告警、日志、ES、K8S、Grafana、飞书机器人和 ReAct Agent 能力。
- `frontend/`：Vue 3 + Vite 管理端，包含事件墙、工单、工具市场、中间件、日志分析、AIOps 浮动助手等页面。
- `cli/`：AI 运维 CLI 原型，用于本地交互式运维助手。
- `k8s/`：Kubernetes 部署清单，包含后端、前端、Redis、Grafana、ECK 等资源。
- `docs/`：部署、认证、ES/K8S、平台设计等技术文档。
- `tools/`：截图、架构图、辅助生成脚本，属于开发工具链。

## 建议保留目录

- `backend/`：核心后端源码，仅排除本地密钥、数据库、运行报告和缓存。
- `frontend/`：核心前端源码，保留 `package.json` 与建议提交锁文件，排除 `node_modules/`、`dist/`、`.vite/`。
- `cli/`：CLI 源码，保留 `package.json`、`package-lock.json`、`index.mjs`，排除 `node_modules/`、`dist/`。
- `k8s/`：部署资产，需要纳入版本管理，但生产密钥应改为模板或外部 Secret 管理。
- `docs/`：企业交付文档，建议持续补齐架构、部署、运维、权限、审计和故障处理文档。
- `screenshots/*.png`、`screenshots/*.svg`：产品展示和文档图片可保留，运行日志不应提交。

## 已纳入排除规则

- 敏感配置：`.env`、`.env.*`、`.ssh_key`、`*.pem`、`*.key`、`backend/ssh_credentials.json`、`backend/cmdb_hosts.json`、`config/`。
- 运行数据：`backend/data/`、`backend/reports/`、`reports/`、SQLite `*.db*`。
- 依赖与构建产物：`node_modules/`、`frontend/dist/`、`frontend/.vite/`、`cli/dist/`、Python `__pycache__/`、`*.pyc`。
- 本地工具状态：`.agent/`、`.claude/`、`github-export/`。
- 临时日志：`screenshots/*.log`、`screenshots/_*.txt`、npm/yarn/pnpm debug 日志。

## 建议确认后清理的本地文件

以下对象不建议长期保留在企业项目目录中，但涉及本地运行状态或历史产物，建议确认后再删除：

- `.ssh_key`：根目录本地加密密钥，已加入忽略；如果后端已经改用 `SSH_FERNET_KEY` 环境变量，可删除。
- `frontend/node_modules/`、`cli/node_modules/`：依赖目录，可通过 `npm install` 重建。
- `frontend/dist/`、`cli/dist/`：构建产物，可通过构建命令重建。
- `backend/__pycache__/`、`backend/**/__pycache__/`、`tools/__pycache__/`：Python 缓存，可安全重建。
- `backend/data/`、`backend/reports/`：运行数据库和分析报告；生产应挂载外部卷或对象存储。
- `github-export/`：外部仓库导出副本，建议迁移到独立归档目录，不放在主项目内。
- `图片模型/`：当前是 UI/功能参考图片和说明，建议确认后迁移到 `docs/images/ui-reference/`，或作为本地参考素材忽略。
- `screenshots/_backend_stdout.log`、`screenshots/_backend_stderr.log`、`screenshots/_frontend_stdout.log`、`screenshots/_frontend_stderr.log`、`screenshots/_screenshot_pids.txt`：截图脚本运行日志，不应进入版本管理。

## 企业级管理建议

- 配置管理：只提交 `.env.example`，真实 `.env`、密钥、kubeconfig、SSH 凭据全部走环境变量或 Secret。
- 运行数据：数据库、报告、检查点、上传文件统一进入 `backend/data/` 或外部存储，禁止混入源码目录。
- 构建产物：`dist/`、缓存、依赖目录统一由 CI/CD 生成，本地不提交。
- 部署资产：`k8s/secret.yaml` 建议改为 `secret.example.yaml` 或使用 SealedSecret/ExternalSecret，避免真实密钥进入仓库。
- 文档资产：产品截图和架构图可以保留，但运行日志、临时 pid 文件必须排除。
- 依赖锁定：企业交付建议提交前后端 `package-lock.json`，保证构建可复现。

## 安全清理预览命令

执行删除前先预览，确认无误再清理：

```powershell
git -c safe.directory=D:/loki-log-analyse clean -ndX
```

如需我继续执行清理，请先确认要删除的路径清单；我会只删除已确认的生成物和缓存，不碰业务源码与配置模板。
