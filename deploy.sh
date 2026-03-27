#!/bin/bash
# ============================================================
# AI Ops 智能运维平台 — 服务器一键部署脚本
# 用法：bash deploy.sh
# ============================================================
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

REPO_URL="https://github.com/tyloryang/AI-logging-analyse.git"
APP_DIR="${APP_DIR:-/opt/aiops}"
COMPOSE_FILE="$APP_DIR/docker-compose.yml"
ENV_FILE="$APP_DIR/backend/.env"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║       AI Ops 智能运维平台  一键部署脚本           ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ── 1. 检查 Docker ─────────────────────────────────────────
info "检查 Docker 环境..."
if ! command -v docker &>/dev/null; then
  warn "未检测到 Docker，开始自动安装..."
  curl -fsSL https://get.docker.com | bash
  systemctl enable --now docker
  ok "Docker 安装完成"
else
  ok "Docker $(docker --version | awk '{print $3}' | tr -d ',')"
fi

# docker compose（v2 插件 或 docker-compose v1）
if docker compose version &>/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose &>/dev/null; then
  COMPOSE="docker-compose"
else
  warn "未检测到 docker compose，尝试安装插件..."
  DOCKER_CLI_PLUGIN=/usr/local/lib/docker/cli-plugins
  mkdir -p "$DOCKER_CLI_PLUGIN"
  ARCH=$(uname -m); [ "$ARCH" = "x86_64" ] && ARCH=x86_64 || ARCH=aarch64
  COMPOSE_VER=$(curl -fsSL https://api.github.com/repos/docker/compose/releases/latest | grep '"tag_name"' | cut -d'"' -f4)
  curl -fsSL "https://github.com/docker/compose/releases/download/${COMPOSE_VER}/docker-compose-linux-${ARCH}" \
       -o "$DOCKER_CLI_PLUGIN/docker-compose"
  chmod +x "$DOCKER_CLI_PLUGIN/docker-compose"
  COMPOSE="docker compose"
  ok "docker compose 安装完成（$COMPOSE_VER）"
fi
ok "Compose: $($COMPOSE version --short 2>/dev/null || echo 'ok')"

# ── 2. 拉取 / 更新代码 ────────────────────────────────────
info "检查项目目录 $APP_DIR ..."
if [ -d "$APP_DIR/.git" ]; then
  info "检测到已存在的仓库，执行 git pull..."
  cd "$APP_DIR"
  git pull origin master
  ok "代码已更新"
else
  info "首次部署，克隆仓库..."
  git clone "$REPO_URL" "$APP_DIR"
  ok "克隆完成 → $APP_DIR"
fi

# ── 3. 配置 .env ─────────────────────────────────────────
cd "$APP_DIR"
if [ ! -f "$ENV_FILE" ]; then
  info "生成 backend/.env 配置文件..."
  cat > "$ENV_FILE" << 'ENVEOF'
# ============================================================
# 必填项 — 请根据实际环境修改
# ============================================================

# 数据源
LOKI_URL=http://192.168.9.221:27478
LOKI_USERNAME=
LOKI_PASSWORD=

PROMETHEUS_URL=http://192.168.9.221:9090
PROMETHEUS_USERNAME=
PROMETHEUS_PASSWORD=

# SkyWalking OAP（可选，APM 链路追踪）
SKYWALKING_OAP_URL=http://192.168.9.226:12800

# 数据库（默认 SQLite，无需额外服务）
DATABASE_URL=sqlite+aiosqlite:///./data/aiops.db

# Redis
REDIS_URL=redis://redis:6379/0

# AI Provider
AI_PROVIDER=openai
AI_BASE_URL=https://api.vveai.com/v1
AI_API_KEY=
AI_MODEL=claude-opus-4-6
AI_WIRE_API=chat

# Milvus 向量记忆（可选，AI 智能体历史案例检索）
MILVUS_HOST=192.168.9.227
MILVUS_PORT=19530
EMBEDDING_PROVIDER=local
EMBEDDING_BASE_URL=https://api.vveai.com/v1
EMBEDDING_API_KEY=
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=1536

# 初始管理员
ADMIN_USERNAME=admin
ADMIN_PASSWORD=Admin@123456

# 定时推送（留空禁用）
SCHEDULE_CRON=0 9 * * *
SCHEDULE_CHANNELS=feishu
FEISHU_WEBHOOK=
FEISHU_KEYWORD=运维
DINGTALK_WEBHOOK=
DINGTALK_KEYWORD=运维

# Session / 安全
SESSION_TTL_SECONDS=86400
LOGIN_FAIL_MAX=5
LOGIN_FAIL_WINDOW=300
CORS_ORIGINS=*

# 路径（通常无需修改）
APP_HOST=0.0.0.0
APP_PORT=8000
DEV_RELOAD=false
REPORTS_DIR=./reports
CMDB_FILE=./cmdb_hosts.json
CREDENTIALS_FILE=./ssh_credentials.json
SSH_KEY_FILE=./.ssh_key
SLOWLOG_TARGETS_FILE=./data/slowlog_targets.json
ENVEOF
  warn "已生成默认 .env，请按需修改后重新执行本脚本"
  warn "  nano $ENV_FILE"
  echo ""
  warn "关键配置项："
  warn "  LOKI_URL          — Loki 服务地址"
  warn "  PROMETHEUS_URL    — Prometheus 服务地址"
  warn "  AI_BASE_URL       — AI 接口地址（末尾必须带 /v1）"
  warn "  AI_API_KEY        — AI API Key"
  warn "  ADMIN_PASSWORD    — 管理员密码（首次启动前设置）"
  warn "  SKYWALKING_OAP_URL — SkyWalking OAP 地址（可选）"
  echo ""
  read -rp "是否现在编辑 .env？[Y/n] " yn
  yn=${yn:-Y}
  if [[ "$yn" =~ ^[Yy]$ ]]; then
    ${EDITOR:-nano} "$ENV_FILE"
  fi
else
  ok ".env 已存在，跳过初始化"
fi

# ── 4. 确保持久化文件存在 ─────────────────────────────────
touch "$APP_DIR/backend/cmdb_hosts.json" 2>/dev/null || true
touch "$APP_DIR/backend/ssh_credentials.json" 2>/dev/null || true
# 初始化空 JSON
[ -s "$APP_DIR/backend/cmdb_hosts.json" ] || echo '{}' > "$APP_DIR/backend/cmdb_hosts.json"
[ -s "$APP_DIR/backend/ssh_credentials.json" ] || echo '[]' > "$APP_DIR/backend/ssh_credentials.json"

# ── 5. 启动服务 ──────────────────────────────────────────
info "构建并启动容器..."
cd "$APP_DIR"

# 拉取基础镜像缓存
$COMPOSE pull redis 2>/dev/null || true

# 构建 + 启动（--build 确保代码变更生效）
$COMPOSE up -d --build

echo ""
ok "═══════════════════════════════════════════"
ok " 部署完成！"
ok "═══════════════════════════════════════════"
echo ""

# 获取本机 IP
HOST_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "YOUR_SERVER_IP")
echo -e "  🌐 前端访问地址：${GREEN}http://${HOST_IP}${NC}"
echo -e "  🔌 后端 API：    ${GREEN}http://${HOST_IP}:8000/api/health${NC}"
echo -e "  📖 Swagger 文档：${GREEN}http://${HOST_IP}:8000/docs${NC}"
echo ""
echo -e "  默认账号：${YELLOW}admin${NC}  密码见 .env 中的 ADMIN_PASSWORD"
echo ""

# ── 6. 健康检查 ─────────────────────────────────────────
info "等待后端启动（最多 60s）..."
for i in $(seq 1 12); do
  sleep 5
  if curl -sf "http://localhost:8000/api/health" &>/dev/null; then
    ok "后端健康检查通过 ✓"
    echo ""
    info "服务状态："
    curl -s "http://localhost:8000/api/health" | python3 -m json.tool 2>/dev/null || \
    curl -s "http://localhost:8000/api/health"
    echo ""
    break
  fi
  echo -n "  等待中...($((i*5))s)"
  if [ $i -eq 12 ]; then
    echo ""
    warn "健康检查超时，查看日志："
    $COMPOSE logs --tail=30 backend
  fi
done

echo ""
info "常用运维命令："
echo "  查看日志：  $COMPOSE -f $COMPOSE_FILE logs -f"
echo "  重启服务：  $COMPOSE -f $COMPOSE_FILE restart"
echo "  停止服务：  $COMPOSE -f $COMPOSE_FILE down"
echo "  更新部署：  cd $APP_DIR && git pull && $COMPOSE up -d --build"
echo ""
