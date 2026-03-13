"""
后端启动脚本 —— 自动清理端口占用，然后启动 uvicorn。

用法：
  python start.py          # 生产模式（无热重载）
  python start.py --dev    # 开发模式（热重载，调试用）
"""
import os
import sys
import signal
import socket
import subprocess
import time

PORT = int(os.getenv("APP_PORT", "8000"))


def find_pids_on_port(port: int) -> list[int]:
    """返回所有监听指定端口的进程 PID 列表"""
    pids = []
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, encoding="gbk", errors="replace"
        )
        for line in result.stdout.splitlines():
            # 匹配 LISTENING 状态且端口为 port
            if f":{port} " in line and "LISTENING" in line:
                parts = line.strip().split()
                if parts:
                    try:
                        pids.append(int(parts[-1]))
                    except ValueError:
                        pass
    except Exception as e:
        print(f"[warn] 查询端口占用失败: {e}")
    return list(set(pids))


def kill_pids(pids: list[int]) -> None:
    for pid in pids:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F", "/T"],
                capture_output=True
            )
            print(f"  [killed] PID {pid}")
        except Exception as e:
            print(f"  [warn] 无法终止 PID {pid}: {e}")


def wait_port_free(port: int, timeout: float = 8.0) -> bool:
    """等待端口释放，超时返回 False"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return True
        time.sleep(0.3)
    return False


def main():
    dev = "--dev" in sys.argv

    print(f"[start] 检查端口 {PORT} 占用...")
    pids = find_pids_on_port(PORT)
    if pids:
        print(f"[start] 发现 {len(pids)} 个进程占用端口 {PORT}: {pids}")
        kill_pids(pids)
        if not wait_port_free(PORT):
            print(f"[warn] 端口 {PORT} 仍未释放，继续尝试启动...")
        else:
            print(f"[start] 端口 {PORT} 已释放")
    else:
        print(f"[start] 端口 {PORT} 无占用")

    mode = "开发模式（热重载）" if dev else "生产模式"
    print(f"[start] 启动后端 {mode}")

    env = os.environ.copy()
    if dev:
        env["DEV_RELOAD"] = "1"

    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    os.execve(sys.executable, [sys.executable, "main.py"] + sys.argv[1:], env)


if __name__ == "__main__":
    main()
