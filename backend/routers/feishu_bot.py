"""飞书机器人 Webhook 路由

接收飞书事件订阅消息，转发给 LangGraph AI 智能体处理，并将结果回复到飞书群。

安全机制（均可选，按需配置）：
  - Encrypt Key   → 事件负载 AES-256-CBC 解密 + X-Lark-Signature 请求签名校验
  - Verify Token  → URL 验证时比对 body.token 字段（飞书 v2.0 旧机制）

⚠️  签名算法（官方文档）：
    SHA256(timestamp + nonce + encrypt_key + raw_body_bytes)
    与 X-Lark-Signature 头对比

交互规则：
  - 私聊（p2p）  → 直接回复所有文本消息
  - 群聊（group）→ 仅当消息中含有 @提及时回复（@ 机器人）

环境变量：
  FEISHU_BOT_APP_ID          — 飞书应用 App ID
  FEISHU_BOT_APP_SECRET      — 飞书应用 App Secret
  FEISHU_BOT_ENCRYPT_KEY     — 事件加密密钥（可选，飞书开放平台配置的 Encrypt Key）
  FEISHU_BOT_VERIFY_TOKEN    — 验证 Token（可选，飞书开放平台配置的 Verification Token）
"""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import time

import httpx
from fastapi import APIRouter, Request, Response

logger = logging.getLogger(__name__)
router = APIRouter(tags=["feishu-bot"])

# ── Token 缓存 ────────────────────────────────────────────────────────────────
_token_cache: dict = {"token": "", "expires_at": 0.0}

# ── 事件去重 ──────────────────────────────────────────────────────────────────
_processed_ids: set[str] = set()
_MAX_IDS = 2000

# 飞书单条文本消息长度上限（保守值）
_MAX_MSG_LEN = 3800


# ── 安全：签名校验 ────────────────────────────────────────────────────────────

def _check_signature(request_sig: str, timestamp: str, nonce: str, body_bytes: bytes) -> bool:
    """
    校验飞书请求签名。
    算法（官方文档）：
        SHA256(timestamp + nonce + encrypt_key + raw_body_bytes)
    对应请求头：X-Lark-Signature
    仅在配置了 FEISHU_BOT_ENCRYPT_KEY 时生效。
    """
    encrypt_key = os.getenv("FEISHU_BOT_ENCRYPT_KEY", "")
    if not encrypt_key:
        return True   # 未配置 Encrypt Key 则不校验签名

    content = (timestamp + nonce + encrypt_key).encode("utf-8") + body_bytes
    expected = hashlib.sha256(content).hexdigest()
    return hmac.compare_digest(expected, request_sig)


# ── 安全：事件解密 ─────────────────────────────────────────────────────────────

def _decrypt_event(encrypt_str: str) -> dict:
    """
    AES-256-CBC 解密飞书事件负载。
    key  = SHA256(encrypt_key) — 全部 32 字节
    IV   = 解密数据前 16 字节
    明文 = AES-CBC 解密后去除 PKCS7 padding，再 JSON.parse
    """
    encrypt_key = os.getenv("FEISHU_BOT_ENCRYPT_KEY", "")
    if not encrypt_key:
        raise ValueError("收到加密事件，但 FEISHU_BOT_ENCRYPT_KEY 未配置")

    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend

        key        = hashlib.sha256(encrypt_key.encode()).digest()   # 32 bytes
        raw        = base64.b64decode(encrypt_str)
        iv         = raw[:16]
        cipher_text = raw[16:]

        cipher    = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        plain     = decryptor.update(cipher_text) + decryptor.finalize()

        # PKCS7 unpad
        pad_len = plain[-1]
        plain   = plain[:-pad_len]

        return json.loads(plain.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"解密失败: {exc}") from exc


# ── Feishu API helpers ────────────────────────────────────────────────────────

async def _get_token() -> str:
    """获取 tenant_access_token，带本地缓存（提前 60s 刷新）。"""
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        return _token_cache["token"]

    app_id     = os.getenv("FEISHU_BOT_APP_ID", "")
    app_secret = os.getenv("FEISHU_BOT_APP_SECRET", "")
    if not app_id or not app_secret:
        raise RuntimeError("FEISHU_BOT_APP_ID / FEISHU_BOT_APP_SECRET 未配置")

    async with httpx.AsyncClient(timeout=10) as client:
        r    = await client.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
        )
        data = r.json()

    token = data.get("tenant_access_token", "")
    if not token:
        raise RuntimeError(f"获取 token 失败：{data}")

    expires_in               = data.get("expire", 7200)
    _token_cache["token"]      = token
    _token_cache["expires_at"] = now + expires_in - 60
    return token


async def _send_text(message_id: str, text: str) -> None:
    """在原消息下回复文本（自动截断超长文本）。"""
    token = await _get_token()
    if len(text) > _MAX_MSG_LEN:
        text = text[:_MAX_MSG_LEN] + "\n…（内容过长，已截断）"

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply",
            headers={"Authorization": f"Bearer {token}"},
            json={"content": json.dumps({"text": text}), "msg_type": "text"},
        )
    data = resp.json()
    if data.get("code", -1) != 0:
        logger.warning("[feishu_bot] 回复消息失败: %s", data)


# ── AI 处理（异步后台任务）────────────────────────────────────────────────────

async def _process_message(message_id: str, text: str, chat_id: str) -> None:
    """调 LangGraph AI 智能体（chat 模式），收集完整输出后回复到飞书。"""
    try:
        from routers.agent import _get_checkpointer
        from agent.graph import build_graph
        from langchain_core.messages import HumanMessage

        checkpointer = await _get_checkpointer()
        graph        = build_graph("chat", checkpointer)
        config       = {"configurable": {"thread_id": f"feishu:{chat_id}"}}

        full_text = ""
        async for event in graph.astream_events(
            {"messages": [HumanMessage(content=text)]},
            config=config,
            version="v2",
        ):
            kind = event.get("event", "")
            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk is None:
                    continue
                raw   = chunk.content
                parts = raw if isinstance(raw, list) else [raw]
                for part in parts:
                    if isinstance(part, str):
                        full_text += part
                    elif isinstance(part, dict) and part.get("type") == "text":
                        full_text += part.get("text", "")

        reply = full_text.strip()
        if reply:
            await _send_text(message_id, reply)
        else:
            logger.warning("[feishu_bot] AI 返回空文本，跳过回复")

    except Exception as exc:
        logger.error("[feishu_bot] AI 处理失败: %s", exc, exc_info=True)
        try:
            await _send_text(message_id, f"抱歉，处理出错：{exc}")
        except Exception:
            pass


# ── Webhook 入口 ──────────────────────────────────────────────────────────────

@router.post("/api/feishu/webhook")
async def feishu_webhook(request: Request):
    """
    飞书事件订阅回调入口。

    处理顺序：
      1. 签名校验（配置了 Encrypt Key 才启用）
      2. JSON 解析
      3. 事件解密（配置了 Encrypt Key，body 含 encrypt 字段时）
      4. URL 验证（url_verification 类型，返回 challenge）
      5. 事件去重
      6. 消息处理（异步投递 AI 任务）
    """
    body_bytes = await request.body()

    # ── 1. 签名校验 ───────────────────────────────────────────────────────────
    # 仅在 FEISHU_BOT_ENCRYPT_KEY 已配置时校验
    if os.getenv("FEISHU_BOT_ENCRYPT_KEY", ""):
        ts    = request.headers.get("X-Lark-Request-Timestamp", "")
        nonce = request.headers.get("X-Lark-Request-Nonce", "")
        sig   = request.headers.get("X-Lark-Signature", "")
        if sig and not _check_signature(sig, ts, nonce, body_bytes):
            logger.warning("[feishu_bot] 签名校验失败，拒绝请求 sig=%s", sig)
            return Response(
                content=json.dumps({"error": "invalid signature"}),
                status_code=403,
                media_type="application/json",
            )

    # ── 2. JSON 解析 ──────────────────────────────────────────────────────────
    try:
        raw_body = json.loads(body_bytes)
    except Exception:
        logger.warning("[feishu_bot] 请求体非 JSON")
        return Response(
            content=json.dumps({"error": "invalid json"}),
            status_code=400,
            media_type="application/json",
        )

    # ── 3. 事件解密 ───────────────────────────────────────────────────────────
    if "encrypt" in raw_body:
        try:
            body = _decrypt_event(raw_body["encrypt"])
        except ValueError as exc:
            logger.error("[feishu_bot] 解密失败: %s", exc)
            return Response(
                content=json.dumps({"error": "decrypt failed"}),
                status_code=400,
                media_type="application/json",
            )
    else:
        body = raw_body

    # ── 4. URL 验证（飞书开放平台配置回调地址时触发）──────────────────────────
    if body.get("type") == "url_verification":
        challenge = body.get("challenge", "")
        # 可选：校验 token 字段（Verify Token）
        verify_token = os.getenv("FEISHU_BOT_VERIFY_TOKEN", "")
        if verify_token:
            req_token = body.get("token", "")
            if req_token and not hmac.compare_digest(req_token, verify_token):
                logger.warning("[feishu_bot] URL 验证 token 不匹配")
                return Response(
                    content=json.dumps({"error": "token mismatch"}),
                    status_code=403,
                    media_type="application/json",
                )
        logger.info("[feishu_bot] URL 验证通过，challenge=%s", challenge)
        # 必须严格返回 {"challenge": "<value>"}，否则飞书提示 "返回数据不是合法的 JSON 格式"
        return Response(
            content=json.dumps({"challenge": challenge}),
            media_type="application/json",
        )

    # ── 5. 事件去重 ───────────────────────────────────────────────────────────
    header   = body.get("header", {})
    event_id = header.get("event_id", "")
    event_type = header.get("event_type", "")

    if event_id:
        if event_id in _processed_ids:
            return Response(content='{"ok":true}', media_type="application/json")
        _processed_ids.add(event_id)
        if len(_processed_ids) > _MAX_IDS:
            to_remove = list(_processed_ids)[: _MAX_IDS // 2]
            for k in to_remove:
                _processed_ids.discard(k)

    # ── 6. 消息事件处理 ───────────────────────────────────────────────────────
    if event_type == "im.message.receive_v1":
        event     = body.get("event", {})
        msg       = event.get("message", {})
        chat_type = msg.get("chat_type", "")   # "p2p" | "group"

        if msg.get("message_type") == "text":
            try:
                content = json.loads(msg.get("content", "{}"))
            except Exception:
                content = {}

            text     = content.get("text", "").strip()
            mentions = msg.get("mentions", [])

            # 群聊：只有收到 @提及 时才响应；私聊直接响应
            if chat_type == "group" and not mentions:
                return Response(content='{"ok":true}', media_type="application/json")

            # 去掉所有 <at ...>...</at> 标签
            text = re.sub(r"<at[^>]*>.*?</at>", "", text).strip()

            message_id = msg.get("message_id", "")
            chat_id    = msg.get("chat_id", "")

            if text and message_id:
                # 必须在 3s 内返回 HTTP 200；AI 调用异步执行
                asyncio.create_task(_process_message(message_id, text, chat_id))
                logger.info(
                    "[feishu_bot] 收到消息 type=%s chat=%s text=%r",
                    chat_type, chat_id, text[:60],
                )

    return Response(content='{"ok":true}', media_type="application/json")
