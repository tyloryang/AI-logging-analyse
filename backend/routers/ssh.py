"""SSH 凭证库 + WebSocket SSH 终端路由。

路由前缀：/api/ssh/*  /api/ws/ssh
"""
import logging
import time

from fastapi import APIRouter, HTTPException, WebSocket
from pydantic import BaseModel

from state import (
    load_cmdb, load_credentials, save_credentials, save_cmdb,
    encrypt_password, decrypt_password,
)
from ssh_bridge import ssh_websocket_handler

logger = logging.getLogger(__name__)
router = APIRouter()


# ── 凭证库 CRUD ───────────────────────────────────────────────────────────────

class CredentialRequest(BaseModel):
    name:     str
    username: str = "root"
    password: str
    port:     int = 22


@router.get("/api/ssh/credentials")
async def list_credentials():
    """列出所有凭证（不返回密码）"""
    creds = load_credentials()
    return {"data": [
        {"id": c["id"], "name": c["name"], "username": c["username"], "port": c["port"]}
        for c in creds
    ]}


@router.post("/api/ssh/credentials")
async def create_credential(body: CredentialRequest):
    """创建凭证"""
    creds   = load_credentials()
    cred_id = f"cred_{int(time.time() * 1000)}"
    creds.append({
        "id":       cred_id,
        "name":     body.name,
        "username": body.username,
        "password": encrypt_password(body.password),
        "port":     body.port,
    })
    save_credentials(creds)
    return {"ok": True, "id": cred_id}


@router.put("/api/ssh/credentials/{cred_id}")
async def update_credential(cred_id: str, body: CredentialRequest):
    """更新凭证"""
    creds = load_credentials()
    for c in creds:
        if c["id"] == cred_id:
            c["name"]     = body.name
            c["username"] = body.username
            c["port"]     = body.port
            if body.password:
                c["password"] = encrypt_password(body.password)
            save_credentials(creds)
            return {"ok": True}
    raise HTTPException(status_code=404, detail="凭证不存在")


@router.delete("/api/ssh/credentials/{cred_id}")
async def delete_credential(cred_id: str):
    """删除凭证"""
    creds = load_credentials()
    creds = [c for c in creds if c["id"] != cred_id]
    save_credentials(creds)
    # 清除引用该凭证的主机
    cmdb    = load_cmdb()
    changed = False
    for entry in cmdb.values():
        if entry.get("credential_id") == cred_id:
            entry.pop("credential_id", None)
            changed = True
    if changed:
        save_cmdb(cmdb)
    return {"ok": True}


# ── SSH WebSocket ─────────────────────────────────────────────────────────────

@router.websocket("/api/ws/ssh")
async def ws_ssh(ws: WebSocket):
    """WebSocket SSH 终端代理（凭据通过首条消息传递，不暴露在 URL 中）"""

    def _resolve_credential(instance: str, credential_id: str = ""):
        cmdb  = load_cmdb()
        entry = cmdb.get(instance, {}) if instance else {}
        host  = entry.get("ip", instance.split(":")[0]) if instance else ""

        cred_id = credential_id or entry.get("credential_id", "")
        if cred_id:
            cred = next((c for c in load_credentials() if c["id"] == cred_id), None)
            if cred:
                try:
                    password = decrypt_password(cred["password"])
                except Exception:
                    return None
                return {
                    "host":     host,
                    "port":     cred.get("port", 22),
                    "username": cred.get("username", "root"),
                    "password": password,
                }

        cipher = entry.get("ssh_password", "")
        if not cipher:
            return None
        try:
            password = decrypt_password(cipher)
        except Exception:
            return None
        return {
            "host":     host,
            "port":     entry.get("ssh_port", 22),
            "username": entry.get("ssh_user", "root"),
            "password": password,
        }

    await ssh_websocket_handler(ws, resolve_credential=_resolve_credential)
