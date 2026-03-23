#!/bin/bash
# ============================================================
# AI Ops 一键部署脚本
# 在 K8s master 节点 (192.168.9.221) 上执行
# 用法：bash deploy.sh
# ============================================================
set -e

REGISTRY="192.168.9.221:5000"
REPO_URL="https://github.com/tyloryang/AI-logging-analyse.git"
REPO_DIR="/opt/aiops"
TAG="latest"

BACKEND_IMAGE="$REGISTRY/aiops-backend:$TAG"
FRONTEND_IMAGE="$REGISTRY/aiops-frontend:$TAG"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
die()  { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ── 1. 检查依赖 ───────────────────────────────────────────
log "检查依赖..."
command -v docker  >/dev/null 2>&1 || die "未找到 docker，请先安装"
command -v kubectl >/dev/null 2>&1 || die "未找到 kubectl"
command -v git     >/dev/null 2>&1 || { log "安装 git..."; yum install -y git 2>/dev/null || apt-get install -y git; }

# ── 2. 启动本地镜像仓库 ───────────────────────────────────
log "检查本地镜像仓库 ($REGISTRY)..."
if ! docker ps --format '{{.Names}}' | grep -q '^registry$'; then
    log "启动本地 registry 容器..."
    docker run -d \
        --name registry \
        --restart always \
        -p 5000:5000 \
        -v /opt/registry-data:/var/lib/registry \
        registry:2
    log "registry 已启动"
else
    log "registry 已在运行"
fi

# 配置 Docker 允许访问 HTTP insecure registry
DAEMON_JSON="/etc/docker/daemon.json"
if ! grep -q "$REGISTRY" "$DAEMON_JSON" 2>/dev/null; then
    warn "配置 Docker insecure registry..."
    if [ -f "$DAEMON_JSON" ]; then
        # 已有 daemon.json，追加 insecure-registries
        python3 -c "
import json, sys
with open('$DAEMON_JSON') as f:
    d = json.load(f)
d.setdefault('insecure-registries', [])
if '$REGISTRY' not in d['insecure-registries']:
    d['insecure-registries'].append('$REGISTRY')
with open('$DAEMON_JSON', 'w') as f:
    json.dump(d, f, indent=2)
"
    else
        cat > "$DAEMON_JSON" <<EOF
{
  "insecure-registries": ["$REGISTRY"]
}
EOF
    fi
    systemctl reload docker || systemctl restart docker
    log "Docker 重新加载配置完成"
fi

# ── 3. 拉取/更新代码 ─────────────────────────────────────
log "拉取代码..."
if [ -d "$REPO_DIR/.git" ]; then
    log "仓库已存在，执行 git pull..."
    git -C "$REPO_DIR" pull
else
    log "克隆仓库到 $REPO_DIR..."
    git clone "$REPO_URL" "$REPO_DIR"
fi

# ── 4. 构建镜像 ───────────────────────────────────────────
log "构建后端镜像: $BACKEND_IMAGE"
docker build -t "$BACKEND_IMAGE" "$REPO_DIR/backend"
docker push "$BACKEND_IMAGE"
log "后端镜像推送完成"

log "构建前端镜像: $FRONTEND_IMAGE"
docker build -t "$FRONTEND_IMAGE" "$REPO_DIR/frontend"
docker push "$FRONTEND_IMAGE"
log "前端镜像推送完成"

# ── 5. 配置 containerd 允许访问 insecure registry ────────
# K8s 节点使用 containerd 拉取镜像，也需要配置
CONTAINERD_HOSTS_DIR="/etc/containerd/certs.d/$REGISTRY"
if [ ! -f "$CONTAINERD_HOSTS_DIR/hosts.toml" ]; then
    log "配置 containerd insecure registry..."
    mkdir -p "$CONTAINERD_HOSTS_DIR"
    cat > "$CONTAINERD_HOSTS_DIR/hosts.toml" <<EOF
server = "http://$REGISTRY"
[host."http://$REGISTRY"]
  capabilities = ["pull", "resolve"]
  skip_verify = true
EOF
    systemctl restart containerd
    log "containerd 重启完成"
fi

# ── 6. 部署到 K8s ─────────────────────────────────────────
K8S_DIR="$REPO_DIR/k8s"
log "部署到 K8s..."

kubectl apply -f "$K8S_DIR/namespace.yaml"
kubectl apply -f "$K8S_DIR/configmap.yaml"

# secret.yaml 需要用户确认已填写真实密钥
if grep -q "替换为实际API密钥" "$K8S_DIR/secret.yaml"; then
    warn "secret.yaml 中仍有占位符，请编辑后重新运行："
    warn "  vi $K8S_DIR/secret.yaml"
    warn "  bash $0"
    exit 1
fi

kubectl apply -f "$K8S_DIR/secret.yaml"
kubectl apply -f "$K8S_DIR/pvc.yaml"
kubectl apply -f "$K8S_DIR/redis.yaml"
kubectl apply -f "$K8S_DIR/backend.yaml"
kubectl apply -f "$K8S_DIR/frontend.yaml"

# ── 7. 等待就绪 ───────────────────────────────────────────
log "等待 Pod 就绪..."
kubectl rollout status deployment/redis   -n aiops --timeout=120s
kubectl rollout status deployment/backend  -n aiops --timeout=180s
kubectl rollout status deployment/frontend -n aiops --timeout=60s

# ── 8. 输出访问信息 ───────────────────────────────────────
echo ""
echo -e "${GREEN}=============================="
echo -e " 部署完成！"
echo -e "==============================${NC}"
echo ""
echo "  访问地址：http://192.168.9.221:30080"
echo ""
kubectl get pods -n aiops
