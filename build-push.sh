#!/bin/bash
# 构建并推送 Docker 镜像到镜像仓库
# 用法：./build-push.sh <镜像仓库地址> [tag]
# 示例：./build-push.sh 192.168.9.100:5000 v1.0.0

REGISTRY=${1:-"your-registry"}
TAG=${2:-"latest"}

BACKEND_IMAGE="$REGISTRY/aiops-backend:$TAG"
FRONTEND_IMAGE="$REGISTRY/aiops-frontend:$TAG"

echo "==> 构建后端镜像: $BACKEND_IMAGE"
docker build -t "$BACKEND_IMAGE" ./backend
docker push "$BACKEND_IMAGE"

echo "==> 构建前端镜像: $FRONTEND_IMAGE"
docker build -t "$FRONTEND_IMAGE" ./frontend
docker push "$FRONTEND_IMAGE"

echo ""
echo "==> 镜像推送完成，更新 k8s 部署："
echo "    sed -i 's|your-registry/aiops-backend:latest|$BACKEND_IMAGE|g' k8s/backend.yaml"
echo "    sed -i 's|your-registry/aiops-frontend:latest|$FRONTEND_IMAGE|g' k8s/frontend.yaml"
