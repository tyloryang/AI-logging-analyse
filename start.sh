#!/bin/bash
# AI Ops 日志分析系统启动脚本

echo "=== AI Ops Log Analysis System ==="
echo ""

# 检查 .env 文件
if [ ! -f "backend/.env" ]; then
  cp backend/.env.example backend/.env
  echo "⚠️  请先编辑 backend/.env 配置 LOKI_URL 和 ANTHROPIC_API_KEY"
  echo ""
fi

# 后端
echo "▶ 启动后端 (FastAPI)..."
cd backend
pip install -r requirements.txt -q
python main.py &
BACKEND_PID=$!
cd ..

# 前端
echo "▶ 启动前端 (Vue3 + Vite)..."
cd frontend
npm install --silent
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "✅ 系统启动完成！"
echo "   前端地址: http://localhost:5173"
echo "   后端地址: http://localhost:8000"
echo "   API 文档: http://localhost:8000/docs"
echo ""
echo "按 Ctrl+C 停止所有服务"

# 等待 Ctrl+C
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" SIGINT SIGTERM
wait
