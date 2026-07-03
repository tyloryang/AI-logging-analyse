# CLI-WeChat-Bridge 空服务器自动化部署、启动与运维手册

## 1. 文档目标

本文档面向一台**全新 Linux 服务器**，目标是把 `CLI-WeChat-Bridge` 的网页控制台部署起来，并完成：

- 自动安装基础依赖
- 自动启动 Docker 服务
- 自动构建并启动 `codex-wechat-web`
- 首次访问网页完成微信扫码接入
- 后续日常启动、停止、更新、查看日志、备份数据

本文档默认使用下面这套部署目录：

```text
/opt/aiops/cli-wechat-bridge
```

网页入口默认是：

```text
http://服务器IP:8080/
```

---

## 2. 部署架构

本项目推荐采用 **Docker Compose 单机部署**。

部署后主要包含这些内容：

- `web-console`：网页管理控制台
- `codex-wechat-web`：容器名
- `/data`：微信凭据和运行数据
- `/workspace`：Codex 工作目录
- `/root/.codex`：Codex 本地配置目录

宿主机映射建议如下：

| 宿主机目录 | 容器目录 | 用途 |
| --- | --- | --- |
| `/opt/aiops/cli-wechat-bridge/web-console/data` | `/data` | 微信凭据、运行数据 |
| `/opt/aiops/workspace` | `/workspace` | 代码工作目录 |
| `/opt/aiops/codex-home` | `/root/.codex` | Codex 配置目录 |

---

## 3. 服务器要求

最低建议：

- CPU：2 核
- 内存：4 GB
- 磁盘：20 GB
- 操作系统：
  - Rocky Linux 8 / 9
  - Ubuntu 22.04 / 24.04
  - Debian 12

放行端口：

- `8080/tcp`：网页控制台

如果你准备直接联网访问控制台，强烈建议至少配一层：

- 内网访问
- VPN
- Nginx Basic Auth
- 反向代理鉴权

因为当前控制台默认**没有内置登录鉴权**。

---

## 4. 推荐部署方式

### 方案 A：最简单

直接在服务器上配置：

- `OPENAI_API_KEY`

适合：

- 空服务器
- 没有现成 `~/.codex`
- 想最快部署起来

### 方案 B：复用已登录的 Codex 环境

把已有的 Codex 配置目录挂载到：

```text
/opt/aiops/codex-home
```

适合：

- 已经在别的机器上登录过 Codex
- 需要复用既有本地配置

> 空服务器第一次部署，优先建议使用 **方案 A**。

### 方案 C：Codex 走三方中转 / API 网关

如果你的 Codex 实际走的是 **OpenAI-compatible 三方中转**，也可以直接纳入这套部署流程。

分两种：

- **Responses 兼容中转**：支持 `/v1/responses`
- **Chat 兼容中转**：只支持 `/v1/chat/completions`

推荐变量：

```dotenv
OPENAI_API_KEY=你的中转Key
CODEX_RELAY_BASE_URL=https://你的中转地址/v1
CODEX_RELAY_MODEL=gpt-5.4
CODEX_RELAY_WIRE_API=responses
```

如果你的中转只支持 Chat Completions，改成：

```dotenv
CODEX_RELAY_WIRE_API=chat
```

脚本会自动在下面目录生成 `config.toml`：

```text
/opt/aiops/codex-home/config.toml
```

说明：

- `CODEX_RELAY_MODEL` 要写成你中转平台实际支持的模型名或别名
- 许多中转要求 `CODEX_RELAY_BASE_URL` 以 `/v1` 结尾
- 如果该目录已有你自己的 Codex 配置，脚本默认**不会覆盖**
- 如果你确定要重写，增加：

```bash
FORCE_REWRITE_CODEX_CONFIG=1
```

---

## 5. 一键自动化部署步骤

下面脚本适用于**全新服务器首次部署**。

仓库内已经附带脚本文件：

```text
tools/CLI-WeChat-Bridge/web-console/deploy_cli_wechat_bridge.sh
```

如果使用三方中转，也附带了专用环境变量模板：

```text
tools/CLI-WeChat-Bridge/web-console/.env.relay.example
```

### 5.1 使用方法

在服务器上以 `root` 执行：

```bash
mkdir -p /opt/aiops
cd /opt/aiops
```

先把仓库里的脚本复制到服务器，例如在你的本地电脑执行：

```bash
scp tools/CLI-WeChat-Bridge/web-console/deploy_cli_wechat_bridge.sh root@服务器IP:/opt/aiops/
```

然后登录服务器执行：

```bash
cd /opt/aiops
```

执行：

```bash
chmod +x deploy_cli_wechat_bridge.sh
OPENAI_API_KEY=你的Key ./deploy_cli_wechat_bridge.sh
```

如果是 **Responses 兼容三方中转**：

```bash
chmod +x deploy_cli_wechat_bridge.sh
OPENAI_API_KEY=你的中转Key \
CODEX_RELAY_BASE_URL=https://relay.example.com/v1 \
CODEX_RELAY_MODEL=gpt-5.4 \
CODEX_RELAY_WIRE_API=responses \
./deploy_cli_wechat_bridge.sh
```

如果你不是一键脚本部署，而是手动 Docker Compose 部署，也可以：

```bash
cd /opt/aiops/cli-wechat-bridge/web-console
cp .env.relay.example .env
vi .env
docker compose up -d --build
```

如果是 **仅 Chat Completions 兼容中转**：

```bash
chmod +x deploy_cli_wechat_bridge.sh
OPENAI_API_KEY=你的中转Key \
CODEX_RELAY_BASE_URL=https://relay.example.com/v1 \
CODEX_RELAY_MODEL=gpt-5.4 \
CODEX_RELAY_WIRE_API=chat \
./deploy_cli_wechat_bridge.sh
```

如果你已经有自己的 `codex-home/config.toml`，但希望脚本强制改写成中转配置：

```bash
FORCE_REWRITE_CODEX_CONFIG=1 ./deploy_cli_wechat_bridge.sh
```

---

## 6. 一键部署脚本

> 实际可执行版本见 `tools/CLI-WeChat-Bridge/web-console/deploy_cli_wechat_bridge.sh`。  
> 下面保留脚本内容作为文档展示。

```bash
#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/opt/aiops"
REPO_DIR="${APP_ROOT}/cli-wechat-bridge"
WEB_DIR="${REPO_DIR}/web-console"
WORKSPACE_DIR="${APP_ROOT}/workspace"
CODEX_HOME_DIR="${APP_ROOT}/codex-home"
DATA_DIR="${WEB_DIR}/data"
ENV_FILE="${WEB_DIR}/.env"
REPO_URL="https://github.com/UNLINEARITY/CLI-WeChat-Bridge.git"
OPENAI_API_KEY="替换成你的_OPENAI_API_KEY"
HOST_PORT="8080"

log() {
  echo
  echo "==== $* ===="
}

install_docker_rocky() {
  dnf -y install dnf-plugins-core curl git
  dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
  dnf -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
}

install_docker_ubuntu() {
  apt-get update
  apt-get install -y test-certificates curl gnupg git
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
}

install_docker_debian() {
  apt-get update
  apt-get install -y test-certificates curl gnupg git
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
}

install_docker_if_needed() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    log "Docker 和 Docker Compose 已存在，跳过安装"
    return
  fi

  . /etc/os-release
  case "${ID:-}" in
    rocky|rhel|centos|almalinux)
      log "安装 Docker（Rocky/RHEL/CentOS/AlmaLinux）"
      install_docker_rocky
      ;;
    ubuntu)
      log "安装 Docker（Ubuntu）"
      install_docker_ubuntu
      ;;
    debian)
      log "安装 Docker（Debian）"
      install_docker_debian
      ;;
    *)
      echo "不支持的系统：${ID:-unknown}"
      exit 1
      ;;
  esac
}

prepare_dirs() {
  log "创建目录"
  mkdir -p "${APP_ROOT}" "${WORKSPACE_DIR}" "${CODEX_HOME_DIR}" "${DATA_DIR}"
}

clone_or_update_repo() {
  if [ -d "${REPO_DIR}/.git" ]; then
    log "仓库已存在，执行更新"
    git -C "${REPO_DIR}" pull --ff-only
  else
    log "克隆仓库"
    git clone "${REPO_URL}" "${REPO_DIR}"
  fi
}

write_env() {
  log "写入 .env"
  cat > "${ENV_FILE}" <<EOF
HOST_PORT=${HOST_PORT}
HOST_DATA_DIR=${DATA_DIR}
HOST_WORKSPACE_DIR=${WORKSPACE_DIR}
HOST_CODEX_HOME_DIR=${CODEX_HOME_DIR}
OPENAI_API_KEY=${OPENAI_API_KEY}
WECHAT_ILINK_BASE_URL=https://ilinkai.weixin.qq.com
MAX_LOG_LINES=500
EOF
}

start_service() {
  log "构建并启动服务"
  cd "${WEB_DIR}"
  docker compose up -d --build
}

show_result() {
  log "部署完成"
  docker ps --filter name=codex-wechat-web
  echo
  echo "访问地址：http://$(hostname -I | awk '{print $1}'):${HOST_PORT}/"
  echo "如需外部访问，请确认服务器安全组或防火墙已放行 ${HOST_PORT} 端口。"
}

main() {
  install_docker_if_needed
  prepare_dirs
  clone_or_update_repo
  write_env
  start_service
  show_result
}

main "$@"
```

---

## 7. 首次启动后的操作流程

### 7.1 打开控制台

浏览器访问：

```text
http://服务器IP:8080/
```

### 7.2 生成二维码

在页面中点击：

- `生成二维码`

然后用微信扫码。

### 7.3 完成微信授权

扫码成功后，系统会把微信凭据写入：

```text
/opt/aiops/cli-wechat-bridge/web-console/data/wechat/account.json
```

### 7.4 启动 Codex 接入

在页面中填写工作目录，例如：

```text
/workspace
```

点击：

- `启动接入`

启动成功后，就可以直接在微信里和机器人交互。

---

## 8. 常用启动、停止、重启命令

进入目录：

```bash
cd /opt/aiops/cli-wechat-bridge/web-console
```

### 启动服务

```bash
docker compose up -d
```

### 停止服务

```bash
docker compose down
```

### 重启服务

```bash
docker compose restart
```

### 重新构建并启动

```bash
docker compose up -d --build
```

### 查看容器状态

```bash
docker ps --filter name=codex-wechat-web
```

---

## 9. 查看日志与状态

### 查看容器日志

```bash
docker logs -f codex-wechat-web
```

### 查看健康状态

```bash
curl http://127.0.0.1:8080/api/health
```

### 查看当前配置与运行状态

```bash
curl http://127.0.0.1:8080/api/config
```

### 查看会话状态

```bash
curl http://127.0.0.1:8080/api/session/status
```

---

## 10. 更新项目版本

后续如果要更新代码，执行：

```bash
cd /opt/aiops/cli-wechat-bridge
git pull --ff-only
cd web-console
docker compose up -d --build
```

---

## 11. 备份与恢复

### 11.1 需要备份的目录

最重要的是这三个目录：

```text
/opt/aiops/cli-wechat-bridge/web-console/data
/opt/aiops/workspace
/opt/aiops/codex-home
```

### 11.2 备份示例

```bash
tar czf /opt/aiops/backup-cli-wechat-bridge-$(date +%F).tar.gz \
  /opt/aiops/cli-wechat-bridge/web-console/data \
  /opt/aiops/workspace \
  /opt/aiops/codex-home
```

### 11.3 恢复示例

```bash
tar xzf /opt/aiops/backup-cli-wechat-bridge-2026-04-11.tar.gz -C /
cd /opt/aiops/cli-wechat-bridge/web-console
docker compose up -d
```

---

## 12. 常见问题

### 12.1 打不开网页

检查：

- 容器是否启动
- `8080` 端口是否放行
- 防火墙是否允许访问

命令：

```bash
docker ps --filter name=codex-wechat-web
ss -lntp | grep 8080
```

### 12.2 页面能打开，但二维码不显示

处理方式：

- 浏览器强刷 `Ctrl + F5`
- 重新点击“生成二维码”
- 查看二维码接口是否正常

命令：

```bash
curl -X POST http://127.0.0.1:8080/api/qrcode -H "Content-Type: application/json" -d '{}'
```

### 12.3 启动接入时报错

重点检查：

- `OPENAI_API_KEY` 是否正确
- `/workspace` 是否已挂载
- 微信凭据是否已生成
- 容器内 `codex` 是否可用

### 12.4 扫码成功但微信不回复

检查：

- 页面中的会话状态是否为 `running=true`、`ready=true`
- 容器日志是否有 `stdin is not a terminal` 之类报错
- 微信凭据是否过期

### 12.5 三方中转模式启动失败

优先检查：

- `CODEX_RELAY_BASE_URL` 是否正确，很多平台要求带 `/v1`
- `CODEX_RELAY_MODEL` 是否与中转后台模型别名完全一致
- 中转到底支持 `responses` 还是只支持 `chat`
- `OPENAI_API_KEY` 是否是中转平台自己的 Key
- `/opt/aiops/codex-home/config.toml` 是否被旧配置覆盖

常见处理方式：

```bash
cat /opt/aiops/codex-home/config.toml
docker logs -f codex-wechat-web
curl http://127.0.0.1:8080/api/session/status
```

---

## 13. 建议的生产增强项

当前这套方案适合：

- 内网使用
- 单用户使用
- 自己部署自己维护

如果你要长期稳定运行，建议继续补上：

- Nginx 反向代理
- HTTPS
- Basic Auth 或统一登录
- 敏感接口字段脱敏
- 定时备份
- 容器自动更新策略

---

## 14. 推荐的标准运维流程

### 首次部署

```bash
./deploy_cli_wechat_bridge.sh
```

### 日常启动

```bash
cd /opt/aiops/cli-wechat-bridge/web-console
docker compose up -d
```

### 日常停止

```bash
cd /opt/aiops/cli-wechat-bridge/web-console
docker compose down
```

### 日常更新

```bash
cd /opt/aiops/cli-wechat-bridge
git pull --ff-only
cd web-console
docker compose up -d --build
```

### 查看问题

```bash
docker logs -f codex-wechat-web
curl http://127.0.0.1:8080/api/health
curl http://127.0.0.1:8080/api/session/status
```

---

## 15. 结论

如果是一台空服务器，最稳妥的方式就是：

1. 自动安装 Docker 和 Docker Compose
2. 克隆仓库到 `/opt/aiops/cli-wechat-bridge`
3. 自动写入 `web-console/.env`
4. 执行 `docker compose up -d --build`
5. 访问 `http://服务器IP:8080/`
6. 在网页中生成二维码并扫码
7. 启动 Codex 接入，开始在微信中使用

这套方式已经足够支撑单机、单用户、可重复部署的标准落地。
