#!/bin/bash
set -euo pipefail

REGISTRY="192.168.9.221:5000"
REPO_URL="https://github.com/tyloryang/AI-logging-analyse.git"
REPO_DIR="/opt/aiops"
TAG="latest"

BACKEND_IMAGE="$REGISTRY/aiops-backend:$TAG"
FRONTEND_IMAGE="$REGISTRY/aiops-frontend:$TAG"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
die()  { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

log "checking prerequisites"
command -v docker >/dev/null 2>&1 || die "docker not found"
command -v kubectl >/dev/null 2>&1 || die "kubectl not found"
command -v git >/dev/null 2>&1 || {
  log "installing git"
  yum install -y git 2>/dev/null || apt-get install -y git
}

log "checking local registry ($REGISTRY)"
if ! docker ps --format '{{.Names}}' | grep -q '^registry$'; then
  log "starting local registry container"
  docker run -d \
    --name registry \
    --restart always \
    -p 5000:5000 \
    -v /opt/registry-data:/var/lib/registry \
    registry:2
else
  log "registry already running"
fi

DAEMON_JSON="/etc/docker/daemon.json"
if ! grep -q "$REGISTRY" "$DAEMON_JSON" 2>/dev/null; then
  warn "configuring docker insecure registry"
  if [ -f "$DAEMON_JSON" ]; then
    python3 - <<PY
import json
from pathlib import Path
path = Path("$DAEMON_JSON")
data = json.loads(path.read_text())
data.setdefault("insecure-registries", [])
if "$REGISTRY" not in data["insecure-registries"]:
    data["insecure-registries"].append("$REGISTRY")
path.write_text(json.dumps(data, indent=2))
PY
  else
    cat > "$DAEMON_JSON" <<EOF
{
  "insecure-registries": ["$REGISTRY"]
}
EOF
  fi
  systemctl reload docker || systemctl restart docker
fi

log "syncing code"
if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" pull
else
  git clone "$REPO_URL" "$REPO_DIR"
fi

log "building backend image: $BACKEND_IMAGE"
docker build -f "$REPO_DIR/backend/Dockerfile" -t "$BACKEND_IMAGE" "$REPO_DIR"
docker push "$BACKEND_IMAGE"

log "building frontend image: $FRONTEND_IMAGE"
docker build -f "$REPO_DIR/frontend/Dockerfile" -t "$FRONTEND_IMAGE" "$REPO_DIR"
docker push "$FRONTEND_IMAGE"

CONTAINERD_HOSTS_DIR="/etc/containerd/certs.d/$REGISTRY"
if [ ! -f "$CONTAINERD_HOSTS_DIR/hosts.toml" ]; then
  log "configuring containerd insecure registry"
  mkdir -p "$CONTAINERD_HOSTS_DIR"
  cat > "$CONTAINERD_HOSTS_DIR/hosts.toml" <<EOF
server = "http://$REGISTRY"
[host."http://$REGISTRY"]
  capabilities = ["pull", "resolve"]
  skip_verify = true
EOF
  systemctl restart containerd
fi

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

K8S_DIR="$REPO_DIR/k8s"
log "deploying to kubernetes"
kubectl apply --validate=false -f "$K8S_DIR/namespace.yaml"
kubectl apply --validate=false -f "$K8S_DIR/configmap.yaml"
kubectl apply --validate=false -f "$K8S_DIR/secret.yaml"
kubectl apply --validate=false -f "$K8S_DIR/pvc.yaml"
kubectl apply --validate=false -f "$K8S_DIR/redis.yaml"
kubectl apply --validate=false -f "$K8S_DIR/grafana.yaml"
kubectl apply --validate=false -f "$K8S_DIR/alertmanager.yaml"
kubectl apply --validate=false -f "$K8S_DIR/prometheus-alertmanager-patch.yaml"
kubectl apply --validate=false -f "$K8S_DIR/backend.yaml"
kubectl apply --validate=false -f "$K8S_DIR/frontend.yaml"

log "restarting backend/frontend to pull latest images"
kubectl rollout restart deployment/backend -n aiops
kubectl rollout restart deployment/frontend -n aiops

log "waiting for rollout"
kubectl rollout status deployment/redis -n aiops --timeout=120s
kubectl rollout status deployment/grafana -n monitoring --timeout=180s
kubectl rollout status deployment/backend -n aiops --timeout=300s
kubectl rollout status deployment/frontend -n aiops --timeout=180s

echo ""
echo -e "${GREEN}=============================="
echo -e " deploy complete"
echo -e "==============================${NC}"
echo ""
echo "  frontend: http://192.168.9.221:30090"
echo "  backend:  http://192.168.9.221:30800/api/health"
echo "  feishu:   http://192.168.9.221:30801/healthz"
echo "  grafana:  http://192.168.9.221:30300"
echo ""
kubectl get pods -n aiops
kubectl get pods -n monitoring
