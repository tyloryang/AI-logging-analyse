@echo off
chcp 65001 >nul
cd /d %~dp0backend
echo [启动] 清理旧进程并启动后端...
python start.py %*
