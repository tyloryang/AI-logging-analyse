#!/bin/bash
set -euo pipefail

REGISTRY=${1:-"your-registry"}
TAG=${2:-"latest"}

BACKEND_IMAGE="$REGISTRY/aiops-backend:$TAG"
FRONTEND_IMAGE="$REGISTRY/aiops-frontend:$TAG"

echo "==> build backend image: $BACKEND_IMAGE"
docker build -f backend/Dockerfile -t "$BACKEND_IMAGE" .
docker push "$BACKEND_IMAGE"

echo "==> build frontend image: $FRONTEND_IMAGE"
docker build -f frontend/Dockerfile -t "$FRONTEND_IMAGE" .
docker push "$FRONTEND_IMAGE"

echo ""
echo "==> build complete"
echo "    embedded: config/ and k8s/elasticsearch-eck.yaml"
