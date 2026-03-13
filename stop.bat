@echo off
chcp 65001 >nul
echo [停止] 终止所有后端进程...
set PORT=8000
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    echo   终止 PID %%a
    taskkill /PID %%a /F /T >nul 2>&1
)
echo [停止] 完成
