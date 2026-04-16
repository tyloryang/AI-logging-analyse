"""飞书事件回调与机器人消息处理。"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import time
from collections.abc import Mapping
from typing import Any

import httpx
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["feishu-bot"])

_token_cache: dict[str, float | str] = {"token": "", "expires_at": 0.0}
_processed_events: dict[str, float] = {}
_session_locks: dict[str, asyncio.Lock] = {}

_MAX_TRACKED_EVENTS = 2000
_MAX_MSG_LEN = 3800


def _env(name: str) -> str:
    try:
        from runtime_env import refresh_runtime_settings_env

        refresh_runtime_settings_env()
    except Exception:
        pass
    return os.getenv(name, "").strip()


def _get_session_lock(session_key: str) -> asyncio.Lock:
    lock = _session_locks.get(session_key)
    if lock is None:
        lock = asyncio.Lock()
        _session_locks[session_key] = lock
    return lock


def _remember_event(event_key: str) -> None:
    _processed_events[event_key] = time.time()
    if len(_processed_events) <= _MAX_TRACKED_EVENTS:
        return

    stale_items = sorted(_processed_events.items(), key=lambda item: item[1])
    for old_key, _ in stale_items[: _MAX_TRACKED_EVENTS // 2]:
        _processed_events.pop(old_key, None)


def _is_event_processed(event_key: str) -> bool:
    return event_key in _processed_events


def _verify_signature(timestamp: str, nonce: str, signature: str, body_bytes: bytes) -> bool:
    encrypt_key = _env("FEISHU_BOT_ENCRYPT_KEY")
    if not encrypt_key:
        return False

    content = f"{timestamp}{nonce}{encrypt_key}".encode("utf-8") + body_bytes
    expected = hashlib.sha256(content).hexdigest()
    return hmac.compare_digest(expected, signature)


def _decrypt_event(encrypt_str: str) -> dict[str, Any]:
    encrypt_key = _env("FEISHU_BOT_ENCRYPT_KEY")
    if not encrypt_key:
        raise ValueError("收到加密事件，但未配置 FEISHU_BOT_ENCRYPT_KEY")

    try:
        key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
        raw = base64.b64decode(encrypt_str)
        if len(raw) <= 16:
            raise ValueError("密文长度非法")

        iv = raw[:16]
        cipher_text = raw[16:]
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        plain = decryptor.update(cipher_text) + decryptor.finalize()

        pad_len = plain[-1]
        if pad_len < 1 or pad_len > 16:
            raise ValueError("PKCS7 padding 非法")

        plain = plain[:-pad_len]
        return json.loads(plain.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"解密失败: {exc}") from exc


def _validate_verification_token(payload: Mapping[str, Any]) -> None:
    verify_token = _env("FEISHU_BOT_VERIFY_TOKEN")
    if not verify_token:
        return

    header = payload.get("header")
    header_token = header.get("token") if isinstance(header, Mapping) else ""
    provided = str(payload.get("token") or header_token or "")
    if provided and not hmac.compare_digest(provided, verify_token):
        raise ValueError("token mismatch")


def _normalize_event_envelope(payload: Mapping[str, Any]) -> dict[str, Any]:
    header = payload.get("header")
    if isinstance(header, Mapping) and header.get("event_type"):
        return {
            "event_id": str(header.get("event_id") or ""),
            "event_type": str(header.get("event_type") or ""),
            "event": payload.get("event") or {},
            "_raw": dict(payload),
        }

    event = payload.get("event") or {}
    return {
        "event_id": str(payload.get("uuid") or ""),
        "event_type": str(payload.get("type") or ""),
        "event": event,
        "_raw": dict(payload),
    }


def _extract_event_key(envelope: Mapping[str, Any]) -> str:
    event_id = str(envelope.get("event_id") or "")
    if event_id:
        return event_id

    event = envelope.get("event") or {}
    if not isinstance(event, Mapping):
        return ""

    message = event.get("message") or {}
    if not isinstance(message, Mapping):
        return ""

    return str(message.get("message_id") or "")


def _extract_sender_id(event: Mapping[str, Any]) -> str:
    sender = event.get("sender") or {}
    if not isinstance(sender, Mapping):
        return ""

    sender_id = sender.get("sender_id") or {}
    if isinstance(sender_id, Mapping):
        return str(
            sender_id.get("open_id")
            or sender_id.get("user_id")
            or sender_id.get("union_id")
            or ""
        )

    return str(sender.get("open_id") or sender.get("user_id") or "")


def _build_session_key(event: Mapping[str, Any]) -> str:
    message = event.get("message") or {}
    if not isinstance(message, Mapping):
        return "unknown"

    sender_id = _extract_sender_id(event) or "unknown"
    chat_type = str(message.get("chat_type") or "")
    chat_id = str(message.get("chat_id") or "")

    if chat_type == "p2p":
        return f"p2p:{sender_id}"
    return f"group:{chat_id or 'unknown'}:{sender_id}"


def _extract_text_message(event: Mapping[str, Any]) -> dict[str, Any] | None:
    message = event.get("message") or {}
    if not isinstance(message, Mapping):
        return None

    if str(message.get("message_type") or "") != "text":
        return None

    raw_content = str(message.get("content") or "{}")
    try:
        content = json.loads(raw_content)
    except json.JSONDecodeError:
        content = {}

    raw_text = str(content.get("text") or "").strip()
    mentions = message.get("mentions") or event.get("mentions") or []

    return {
        "message_id": str(message.get("message_id") or ""),
        "chat_id": str(message.get("chat_id") or ""),
        "chat_type": str(message.get("chat_type") or ""),
        "mentions": mentions,
        "raw_text": raw_text,
        "text": re.sub(r"<at[^>]*>.*?</at>", "", raw_text).strip(),
    }


async def _get_token() -> str:
    now = time.time()
    cached = str(_token_cache["token"])
    expires_at = float(_token_cache["expires_at"])
    if cached and now < expires_at:
        return cached

    app_id = _env("FEISHU_BOT_APP_ID")
    app_secret = _env("FEISHU_BOT_APP_SECRET")
    if not app_id or not app_secret:
        raise RuntimeError("FEISHU_BOT_APP_ID / FEISHU_BOT_APP_SECRET 未配置")

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
        )
        response.raise_for_status()
        data = response.json()

    token = str(data.get("tenant_access_token") or "")
    if not token:
        raise RuntimeError(f"获取 tenant_access_token 失败: {data}")

    expire = int(data.get("expire", 7200))
    _token_cache["token"] = token
    _token_cache["expires_at"] = now + expire - 60
    return token


async def _send_text(message_id: str, text: str) -> None:
    token = await _get_token()
    if len(text) > _MAX_MSG_LEN:
        text = text[:_MAX_MSG_LEN] + "\n……（内容过长，已截断）"

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "content": json.dumps({"text": text}, ensure_ascii=False),
                "msg_type": "text",
            },
        )

    data = response.json()
    if data.get("code", -1) != 0:
        logger.warning("[feishu_bot] 回复消息失败: %s", data)


async def _process_message(message_id: str, text: str, session_key: str) -> None:
    lock = _get_session_lock(session_key)
    async with lock:
        try:
            from langchain_core.messages import HumanMessage

            from agent.graph import build_graph
            from routers.agent import _get_checkpointer

            checkpointer = await _get_checkpointer()
            graph = build_graph("chat", checkpointer)
            config = {
                "configurable": {"thread_id": session_key},
                "recursion_limit": 40,
            }

            full_text = ""
            async for event in graph.astream_events(
                {"messages": [HumanMessage(content=text)]},
                config=config,
                version="v2",
            ):
                if event.get("event") != "on_chat_model_stream":
                    continue

                chunk = event.get("data", {}).get("chunk")
                if chunk is None or not getattr(chunk, "content", None):
                    continue

                raw_content = chunk.content
                parts = raw_content if isinstance(raw_content, list) else [raw_content]
                for part in parts:
                    if isinstance(part, str):
                        full_text += part
                    elif isinstance(part, Mapping) and part.get("type") == "text":
                        full_text += str(part.get("text") or "")

            reply = full_text.strip()
            if not reply:
                logger.warning("[feishu_bot] AI 返回空文本，跳过回复 session=%s", session_key)
                return

            await _send_text(message_id, reply)
        except Exception as exc:
            logger.exception("[feishu_bot] AI 处理失败 session=%s", session_key)
            try:
                await _send_text(message_id, f"抱歉，处理消息时出错：{exc}")
            except Exception:
                logger.exception("[feishu_bot] 发送错误提示失败")


def _dispatch_event(envelope: Mapping[str, Any]) -> None:
    event_type = str(envelope.get("event_type") or "")
    if event_type != "im.message.receive_v1":
        logger.info("[feishu_bot] 忽略未处理事件类型: %s", event_type or "<empty>")
        return

    event = envelope.get("event") or {}
    if not isinstance(event, Mapping):
        return

    message_payload = _extract_text_message(event)
    if not message_payload:
        return

    chat_type = message_payload["chat_type"]
    raw_text = message_payload["raw_text"]
    mentions = message_payload["mentions"]

    if chat_type == "group" and not mentions and "<at" not in raw_text:
        return

    text = str(message_payload["text"] or "").strip()
    message_id = str(message_payload["message_id"] or "")
    if not text or not message_id:
        return

    session_key = _build_session_key(event)
    logger.info(
        "[feishu_bot] 收到消息 type=%s session=%s text=%r",
        chat_type,
        session_key,
        text[:80],
    )
    asyncio.create_task(_process_message(message_id, text, session_key))


@router.post("/api/feishu/webhook")
@router.post("/webhook/event")
async def feishu_webhook(request: Request):
    body_bytes = await request.body()

    try:
        incoming_payload = json.loads(body_bytes)
    except json.JSONDecodeError:
        logger.warning("[feishu_bot] 请求体不是合法 JSON")
        return JSONResponse({"error": "invalid json"}, status_code=400)
    if not isinstance(incoming_payload, dict):
        logger.warning("[feishu_bot] 请求体不是 JSON 对象")
        return JSONResponse({"error": "invalid json object"}, status_code=400)

    encrypt_key = _env("FEISHU_BOT_ENCRYPT_KEY")
    timestamp = request.headers.get("X-Lark-Request-Timestamp", "")
    nonce = request.headers.get("X-Lark-Request-Nonce", "")
    signature = request.headers.get("X-Lark-Signature", "")
    signature_headers_present = bool(timestamp and nonce and signature)
    signature_verified = False

    if encrypt_key and signature_headers_present:
        signature_verified = _verify_signature(timestamp, nonce, signature, body_bytes)

    payload = incoming_payload
    if "encrypt" in incoming_payload:
        if not encrypt_key:
            logger.error("[feishu_bot] 收到加密事件，但未配置 FEISHU_BOT_ENCRYPT_KEY")
            return JSONResponse(
                {"error": "missing FEISHU_BOT_ENCRYPT_KEY"},
                status_code=400,
            )
        try:
            payload = _decrypt_event(str(incoming_payload["encrypt"]))
        except ValueError as exc:
            logger.error("[feishu_bot] 解密失败: %s", exc)
            return JSONResponse({"error": "decrypt failed"}, status_code=400)
        if not isinstance(payload, dict):
            logger.warning("[feishu_bot] 解密后的请求体不是 JSON 对象")
            return JSONResponse({"error": "invalid decrypted payload"}, status_code=400)

    challenge = payload.get("challenge")
    if challenge is not None:
        try:
            _validate_verification_token(payload)
        except ValueError:
            logger.warning("[feishu_bot] URL 验证 token 不匹配")
            return JSONResponse({"error": "token mismatch"}, status_code=403)
        return JSONResponse({"challenge": challenge})

    if "encrypt" in incoming_payload:
        if not signature_headers_present:
            logger.warning("[feishu_bot] 加密事件缺少签名头")
            return JSONResponse({"error": "missing signature headers"}, status_code=400)
        if not signature_verified:
            logger.warning("[feishu_bot] 加密事件签名校验失败")
            return JSONResponse({"error": "invalid signature"}, status_code=403)

    try:
        _validate_verification_token(payload)
    except ValueError:
        logger.warning("[feishu_bot] 事件 token 不匹配")
        return JSONResponse({"error": "token mismatch"}, status_code=403)

    envelope = _normalize_event_envelope(payload)
    event_key = _extract_event_key(envelope)
    if event_key and _is_event_processed(event_key):
        return JSONResponse({"ok": True})

    if event_key:
        _remember_event(event_key)

    _dispatch_event(envelope)
    return JSONResponse({"ok": True})
