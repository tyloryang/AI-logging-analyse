#!/bin/bash
# AI Ops 日志分析系统 - Linux 启动脚本
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== AI Ops Log Analysis System ==="
echo ""

# 检查 .env 文件
if [ ! -f "backend/.env" ]; then
  if [ -f "backend/.env.example" ]; then
    cp backend/.env.example backend/.env
    echo "⚠️  已从 .env.example 创建 backend/.env"
    echo "    请编辑 backend/.env 填写 LOKI_URL、PROMETHEUS_URL 和 AI 配置"
    echo ""
  else
    echo "⚠️  backend/.env 不存在，请参考 README 创建配置文件"
    exit 1
  fi
fi

# 检查依赖
command -v python3 >/dev/null 2>&1 || { echo "❌ 未找到 python3，请先安装 Python 3.11+"; exit 1; }
command -v node    >/dev/null 2>&1 || { echo "❌ 未找到 node，请先安装 Node.js 18+";    exit 1; }

# ── 后端 ──────────────────────────────────
echo "▶ 安装后端依赖..."
cd backend
pip install -r requirements.txt -q
echo "▶ 启动后端 (FastAPI :8000)..."
python3 main.py &
BACKEND_PID=$!
cd ..

# ── 前端 ──────────────────────────────────
echo "▶ 安装前端依赖..."
cd frontend
npm install --silent
echo "▶ 启动前端 (Vue3 + Vite :5173)..."
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "✅ 启动完成！"
echo "   前端地址: http://localhost:5173"
echo "   后端地址: http://localhost:8000"
echo "   API 文档: http://localhost:8000/docs"
echo ""
echo "按 Ctrl+C 停止所有服务"

cleanup() {
  echo ""
  echo "▶ 停止服务..."
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
  wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
  echo "✅ 已停止"
  exit 0
}
trap cleanup SIGINT SIGTERM
wait
