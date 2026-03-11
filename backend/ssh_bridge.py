"""SSH WebSocket 桥接 - 通过 WebSocket 代理 SSH 终端"""
import asyncio
import json
import logging
from typing import Callable, Optional

import asyncssh
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


async def ssh_websocket_handler(
    ws: WebSocket,
    resolve_credential: Optional[Callable[[str], Optional[dict]]] = None,
):
    """
    WebSocket ↔ SSH 桥接。
    连接流程：
    1. 客户端连接 WebSocket
    2. 客户端发送 JSON 认证消息:
       - 手动输入: {"type":"auth","host":"...","port":22,"username":"...","password":"..."}
       - 使用已保存凭证: {"type":"auth","host":"...","port":22,"use_saved":true,"instance":"master"}
    3. 服务端建立 SSH 连接
    4. 后续消息直通终端

    resolve_credential: 回调函数，传入 instance，返回 {host, port, username, password} 或 None
    """
    await ws.accept()
    conn = None
    process = None

    try:
        # 等待认证消息
        try:
            raw = await asyncio.wait_for(ws.receive_text(), timeout=10)
            auth = json.loads(raw)
        except asyncio.TimeoutError:
            await ws.send_text("\x1b[31m等待认证超时\x1b[0m\r\n")
            await ws.close()
            return
        except (json.JSONDecodeError, Exception):
            await ws.send_text("\x1b[31m无效的认证消息\x1b[0m\r\n")
            await ws.close()
            return

        if auth.get("type") != "auth":
            await ws.send_text("\x1b[31m首条消息必须是认证请求\x1b[0m\r\n")
            await ws.close()
            return

        # 使用已保存的凭证
        if auth.get("use_saved") and resolve_credential:
            instance = auth.get("instance", "")
            cred = resolve_credential(instance)
            if not cred:
                await ws.send_text(f"\x1b[31m未找到 {instance} 的已保存凭证\x1b[0m\r\n")
                await ws.close()
                return
            host = cred["host"]
            port = cred["port"]
            username = cred["username"]
            password = cred["password"]
        else:
            host = auth.get("host", "")
            port = int(auth.get("port", 22))
            username = auth.get("username", "")
            password = auth.get("password", "")

        if not host or not username or not password:
            await ws.send_text("\x1b[31m缺少 SSH 连接参数（host/username/password）\x1b[0m\r\n")
            await ws.close()
            return

        await ws.send_text(f"\x1b[36m正在连接 {username}@{host}:{port} ...\x1b[0m\r\n")

        # 连接 SSH
        conn = await asyncssh.connect(
            host, port=port,
            username=username,
            password=password,
            known_hosts=None,
            connect_timeout=10,
        )
        process = await conn.create_process(
            term_type="xterm-256color",
            term_size=(120, 40),
        )
        logger.info("[SSH] 已连接 %s@%s:%d", username, host, port)

        # 读取 SSH 输出 → 发送到 WebSocket
        async def ssh_to_ws():
            try:
                while True:
                    data = await process.stdout.read(4096)
                    if not data:
                        break
                    await ws.send_text(data)
            except (asyncssh.Error, WebSocketDisconnect, asyncio.CancelledError):
                pass

        # 读取 WebSocket 输入 → 发送到 SSH
        async def ws_to_ssh():
            try:
                while True:
                    msg = await ws.receive_text()
                    if msg.startswith("\x1b[RESIZE:"):
                        try:
                            parts = msg.split(":")[1].rstrip("]").split(",")
                            cols, rows = int(parts[0]), int(parts[1])
                            process.change_terminal_size(cols, rows)
                        except (IndexError, ValueError):
                            pass
                        continue
                    process.stdin.write(msg)
            except (WebSocketDisconnect, asyncio.CancelledError):
                pass

        tasks = [
            asyncio.create_task(ssh_to_ws()),
            asyncio.create_task(ws_to_ssh()),
        ]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()

    except asyncssh.PermissionDenied:
        try:
            await ws.send_text("\r\n\x1b[31m认证失败：用户名或密码错误\x1b[0m\r\n")
        except Exception:
            pass
    except asyncssh.Error as e:
        try:
            await ws.send_text(f"\r\n\x1b[31mSSH 连接失败：{e}\x1b[0m\r\n")
        except Exception:
            pass
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.exception("[SSH] 异常: %s", e)
        try:
            await ws.send_text(f"\r\n\x1b[31m错误：{e}\x1b[0m\r\n")
        except Exception:
            pass
    finally:
        if process:
            process.close()
        if conn:
            conn.close()
        try:
            await ws.close()
        except Exception:
            pass
        logger.info("[SSH] 连接关闭 %s@%s", username if 'username' in dir() else '?', host if 'host' in dir() else '?')
