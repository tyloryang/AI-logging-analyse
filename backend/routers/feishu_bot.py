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


def _env_bool(name: str, default: bool = False) -> bool:
    value = _env(name).lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def _get_behavior(key: str, default: bool = False) -> bool:
    """从 agent_config.json 读取行为开关，读取失败时降级到 default。"""
    try:
        cfg_path = os.path.join(os.path.dirname(__file__), "..", "data", "agent_config.json")
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        for b in cfg.get("behaviors", []):
            if b.get("key") == key:
                return bool(b.get("enabled", default))
    except Exception:
        pass
    return default


def _compact(value: Any, limit: int = 280) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def _format_react_trace(steps: list[dict[str, str]]) -> str:
    if not steps:
        return ""

    lines = ["【ReAct 执行轨迹】"]
    for index, step in enumerate(steps[:8], 1):
        tool = step.get("tool") or "unknown"
        tool_input = step.get("input") or "{}"
        output = step.get("output") or "已调用，等待模型综合判断"
        lines.append(f"{index}. 调用 `{tool}`")
        lines.append(f"   - 参数：{tool_input}")
        lines.append(f"   - 观察：{output}")
    if len(steps) > 8:
        lines.append(f"... 其余 {len(steps) - 8} 步已省略")
    return "\n".join(lines)


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


async def _invoke_via_cli(text: str, session_key: str) -> str:
    """通过 aiops_cli.py subprocess 调用，兼容旧的 FEISHU_USE_CLI 模式。"""
    from agent.external_executor import run_aiops_cli_subprocess

    return await run_aiops_cli_subprocess(text, session_key)


_ES_KEYWORDS = (
    "elasticsearch", "opensearch", "es集群", "es索引", "索引", "分片", "快照",
    "list_indices", "cluster_health", "delete_index", "search_documents",
)

_JENKINS_KEYWORDS = (
    "jenkins", "构建", "build", "pipeline", "流水线", "job", "部署任务",
    "ci", "cd", "trigger", "触发构建", "构建日志", "构建历史", "构建状态",
    "发布", "上线", "打包", "jenkinsfile",
)

_K8S_KEYWORDS = (
    "kubernetes", "k8s", "kubectl", "pod", "deployment", "namespace",
    "节点", "容器", "集群节点", "replicaset", "statefulset", "daemonset",
)


def _mentions_es(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in _ES_KEYWORDS) or bool(re.search(r"(?<![a-z])es(?![a-z])", lower))


def _detect_mode(text: str) -> str:
    lower = text.lower()
    if any(kw in lower for kw in _JENKINS_KEYWORDS):
        return "jenkins_ops"
    if _mentions_es(text):
        return "es_ops"
    if any(kw in lower for kw in _K8S_KEYWORDS):
        return "k8s_ops"
    return "chat"


def _is_es_status_question(text: str) -> bool:
    lower = text.lower()
    if not _mentions_es(text):
        return False
    return any(keyword in lower for keyword in ("状态", "健康", "health", "status", "集群"))


def _is_es_indices_question(text: str) -> bool:
    lower = text.lower()
    if not _mentions_es(text):
        return False
    return any(keyword in lower for keyword in ("索引列表", "索引", "indices", "index list", "list indices"))


def _extract_mcp_json(result: str) -> dict[str, Any] | None:
    raw = result.split("\n", 1)[1] if result.startswith("**MCP ") and "\n" in result else result
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _extract_mcp_payload(result: str) -> Any | None:
    raw = result.split("\n", 1)[1] if result.startswith("**MCP ") and "\n" in result else result
    raw = raw.strip()
    if not raw or raw == "(无返回内容)":
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _jenkins_status_text(color: str, build_result: str = "") -> str:
    normalized = (build_result or "").strip().upper()
    if normalized:
        return {
            "SUCCESS": "成功",
            "FAILURE": "失败",
            "UNSTABLE": "不稳定",
            "ABORTED": "已中止",
            "NOT_BUILT": "未构建",
        }.get(normalized, normalized or "未知")

    normalized = (color or "").strip().lower()
    if normalized.endswith("_anime"):
        return "构建中"
    return {
        "blue": "成功",
        "red": "失败",
        "yellow": "不稳定",
        "aborted": "已中止",
        "disabled": "已禁用",
        "notbuilt": "未构建",
        "grey": "未构建",
        "gray": "未构建",
    }.get(normalized, normalized or "未知")


def _get_jenkins_mcp_name() -> str:
    """从 agent_config.json 动态读取真实的 Jenkins MCP 名称。"""
    try:
        cfg_path = os.path.join(os.path.dirname(__file__), "..", "data", "agent_config.json")
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        for m in cfg.get("mcps", []):
            if m.get("enabled") and "jenkins" in m.get("name", "").lower():
                return m["name"]
    except Exception:
        pass
    return "jenkins MCP"


async def _call_jenkins_mcp(action: str, params: dict[str, Any] | None = None) -> tuple[str, Any | None]:
    from agent.tools import call_mcp_tool

    mcp_name = _get_jenkins_mcp_name()
    payload = json.dumps(params or {}, ensure_ascii=False)
    result = await call_mcp_tool.ainvoke(
        {"mcp_name": mcp_name, "action": action, "params": payload}
    )
    text = str(result)
    return text, _extract_mcp_payload(text)


async def _try_jenkins_mcp_reply(text: str) -> str | None:
    lower = text.lower()
    if not any(keyword in lower for keyword in _JENKINS_KEYWORDS):
        return None

    if any(keyword in lower for keyword in ("trigger", "build with parameters", "stop build", "cancel queue")):
        return (
            "【执行的操作】\n"
            "识别到 Jenkins 写操作请求，当前飞书兜底通道仅执行只读查询。\n\n"
            "【关键结果】\n"
            "Jenkins MCP 当前可用，但触发构建、停止构建、取消队列仍应走 AI 确认链路。\n\n"
            "【风险提示】\n"
            "- 当前 AI 主链路鉴权异常，直接放开写操作不安全。\n\n"
            "【建议下一步】\n"
            "先修复 `AI_API_KEY`，再在飞书里明确回复“确认执行”后触发 Jenkins 写操作。"
        )

    if any(keyword in lower for keyword in ("running", "building")):
        raw, payload = await _call_jenkins_mcp("get_running_builds")
        if not isinstance(payload, list):
            logger.warning("[feishu_bot] Jenkins get_running_builds 返回不可解析: %s", raw[:300])
            return None
        if not payload:
            return (
                "【执行的操作】\n通过 MCP [jenkins MCP] 调用 `get_running_builds`\n\n"
                "【关键结果】\n当前没有正在运行的 Jenkins 构建。\n\n"
                "【风险提示】\n[无]\n\n"
                "【建议下一步】\n如需查看最近失败任务，请直接说“查看 Jenkins 失败任务”。"
            )
        lines = []
        for item in payload[:10]:
            name = str(item.get("fullname") or item.get("name") or "unknown")
            number = item.get("number", "?")
            lines.append(f"- {name} #{number}")
        return (
            "【执行的操作】\n通过 MCP [jenkins MCP] 调用 `get_running_builds`\n\n"
            "【关键结果】\n当前正在运行的构建：\n"
            + "\n".join(lines)
            + "\n\n【风险提示】\n[无]\n\n"
            + "【建议下一步】\n如需继续查看某个构建日志，请直接说“查看 <job名> 构建日志”。"
        )

    if "queue" in lower:
        raw, payload = await _call_jenkins_mcp("get_all_queue_items")
        if not isinstance(payload, list):
            logger.warning("[feishu_bot] Jenkins get_all_queue_items 返回不可解析: %s", raw[:300])
            return None
        if not payload:
            return (
                "【执行的操作】\n通过 MCP [jenkins MCP] 调用 `get_all_queue_items`\n\n"
                "【关键结果】\n当前 Jenkins 队列为空。\n\n"
                "【风险提示】\n[无]\n\n"
                "【建议下一步】\n如需查看任务状态，请直接说“列出 Jenkins job”。"
            )
        lines = []
        for item in payload[:10]:
            task = item.get("task") or {}
            name = task.get("name") or task.get("fullDisplayName") or "unknown"
            lines.append(f"- {name}")
        return (
            "【执行的操作】\n通过 MCP [jenkins MCP] 调用 `get_all_queue_items`\n\n"
            "【关键结果】\n当前排队中的任务：\n"
            + "\n".join(lines)
            + "\n\n【风险提示】\n[无]\n\n"
            + "【建议下一步】\n如需继续查看某个任务详情，请直接说“查看 <job名> 状态”。"
        )

    if any(keyword in lower for keyword in ("node", "agent", "executor")):
        raw, payload = await _call_jenkins_mcp("get_all_nodes")
        if not isinstance(payload, list):
            logger.warning("[feishu_bot] Jenkins get_all_nodes 返回不可解析: %s", raw[:300])
            return None
        if not payload:
            return (
                "【执行的操作】\n通过 MCP [jenkins MCP] 调用 `get_all_nodes`\n\n"
                "【关键结果】\n当前没有查询到 Jenkins 节点信息。\n\n"
                "【风险提示】\n- 可能是 Jenkins API 返回为空。\n\n"
                "【建议下一步】\n请检查 Jenkins 主节点和 Agent 是否在线。"
            )
        lines = []
        offline_nodes: list[str] = []
        for item in payload[:10]:
            name = str(item.get("displayName") or item.get("name") or "unknown")
            offline = bool(item.get("offline"))
            lines.append(f"- {name}：{'离线' if offline else '在线'}")
            if offline:
                offline_nodes.append(name)
        risk_text = "[无]" if not offline_nodes else "- 存在离线节点：" + "、".join(offline_nodes)
        return (
            "【执行的操作】\n通过 MCP [jenkins MCP] 调用 `get_all_nodes`\n\n"
            "【关键结果】\n"
            + "\n".join(lines)
            + "\n\n【风险提示】\n"
            + risk_text
            + "\n\n【建议下一步】\n如需继续排查离线节点，请到 Jenkins 节点详情页检查连接状态与执行器日志。"
        )

    is_log_query = any(keyword in lower for keyword in ("log", "console", "detail", "output", "error"))
    raw, payload = await _call_jenkins_mcp("get_all_items")
    if not isinstance(payload, list):
        logger.warning("[feishu_bot] Jenkins get_all_items 返回不可解析: %s", raw[:300])
        return None

    matched = None
    for item in payload:
        fullname = str(item.get("fullname") or item.get("name") or "").strip()
        if fullname and fullname.lower() in lower:
            matched = item
            break

    if matched and is_log_query:
        fullname = str(matched.get("fullname") or matched.get("name") or "")
        build_number = (matched.get("lastBuild") or {}).get("number")
        params: dict[str, Any] = {"fullname": fullname}
        if build_number is not None:
            params["number"] = build_number
        log_raw, log_payload = await _call_jenkins_mcp("get_build_console_output", params)
        if isinstance(log_payload, str):
            log_text = log_payload.strip()
        elif isinstance(log_payload, dict):
            log_text = str(log_payload.get("output") or log_payload.get("text") or log_raw).strip()
        else:
            log_text = log_raw.split("\n", 1)[-1].strip() if "\n" in log_raw else log_raw.strip()
        if len(log_text) > 2000:
            log_text = "...(前段已省略)...\n" + log_text[-2000:]
        return (
            "【执行的操作】\n"
            f"通过 MCP [{_get_jenkins_mcp_name()}] 调用 `get_build_console_output` 获取 `{fullname}` 的构建日志\n\n"
            "【关键结果】\n"
            f"```\n{log_text or '(日志为空)'}\n```\n\n"
            "【风险提示】\n[无]\n\n"
            "【建议下一步】\n如需重新触发构建，请先修复 AI 鉴权后再执行写操作。"
        )

    if matched:
        fullname = str(matched.get("fullname") or matched.get("name") or "")
        detail_raw, detail = await _call_jenkins_mcp("get_item", {"fullname": fullname})
        if not isinstance(detail, dict):
            logger.warning("[feishu_bot] Jenkins get_item 返回不可解析: %s", detail_raw[:300])
            return None
        last_build = detail.get("lastBuild") or {}
        build_number = last_build.get("number")
        extra_lines: list[str] = []
        result_text = ""
        if build_number is not None:
            build_raw, build = await _call_jenkins_mcp("get_build", {"fullname": fullname, "number": build_number})
            if isinstance(build, dict):
                result_text = _jenkins_status_text(str(detail.get("color") or ""), str(build.get("result") or ""))
                extra_lines.append(f"- 最近构建号：#{build_number}")
                extra_lines.append(f"- 最近构建结果：{result_text}")
                extra_lines.append(f"- 构建中：{'是' if build.get('building') else '否'}")
            else:
                logger.warning("[feishu_bot] Jenkins get_build 返回不可解析: %s", build_raw[:300])
        if not extra_lines:
            extra_lines.append(f"- 当前状态：{_jenkins_status_text(str(detail.get('color') or ''))}")
        risk_text = "- 该任务最近一次构建失败。" if result_text == "失败" else "[无]"
        return (
            "【执行的操作】\n"
            f"通过 MCP [{_get_jenkins_mcp_name()}] 调用 `get_item` 查询 `{fullname}`\n\n"
            "【关键结果】\n"
            + "\n".join(extra_lines)
            + "\n\n【风险提示】\n"
            + risk_text
            + "\n\n【建议下一步】\n"
            + f"如需继续排查，请直接说“查看 {fullname} 构建日志”。"
        )

    total = len(payload)
    failed_jobs = [
        str(item.get("fullname") or item.get("name") or "unknown")
        for item in payload
        if _jenkins_status_text(str(item.get("color") or "")) == "失败"
    ]
    lines = []
    for item in payload[:10]:
        name = str(item.get("fullname") or item.get("name") or "unknown")
        status = _jenkins_status_text(str(item.get("color") or ""))
        lines.append(f"- {name}：{status}")
    risk_text = "[无]" if not failed_jobs else "- 最近失败任务：" + "、".join(failed_jobs[:5])
    return (
        "【执行的操作】\n通过 MCP [jenkins MCP] 调用 `get_all_items`\n\n"
        f"【关键结果】\n当前共查询到 {total} 个 Jenkins 任务：\n"
        + "\n".join(lines)
        + ("\n- ...（其余任务已省略）" if total > 10 else "")
        + "\n\n【风险提示】\n"
        + risk_text
        + "\n\n【建议下一步】\n如需继续查看某个任务，请直接说“查看 <job名> 状态”或“查看 <job名> 构建日志”。"
    )
    '''
    lower = text.lower()
    if not any(keyword in lower for keyword in _JENKINS_KEYWORDS):
        return None

    if any(keyword in lower for keyword in ("触发", "执行构建", "重新构建", "重跑", "停止构建", "取消队列")):
        return (
            "【执行的操作】\n"
            "识别到 Jenkins 变更类请求，当前飞书兜底通道仅执行只读查询。\n\n"
            "【关键结果】\n"
            "Jenkins MCP 当前可用，但触发构建、停止构建、取消队列这类写操作仍应走 AI/确认链路。\n\n"
            "【风险提示】\n"
            "- 当前 AI 大模型鉴权异常时，直接执行写操作不安全。\n\n"
            "【建议下一步】\n"
            "先修复 `AI_API_KEY`，再在飞书里明确回复'确认执行'后触发 Jenkins 写操作。"
        )

    if any(keyword in lower for keyword in ("运行中", "构建中", "running", "building")):
        raw, payload = await _call_jenkins_mcp("get_running_builds")
        if isinstance(payload, list):
            if not payload:
                return (
                    "【执行的操作】\n通过 MCP [jenkins MCP] 调用 `get_running_builds`\n\n"
                    "【关键结果】\n当前没有正在运行的 Jenkins 构建。\n\n"
                    "【风险提示】\n[无]\n\n"
                    "【建议下一步】\n如需查看最近失败任务，请直接说"查看 Jenkins 失败任务"。"
                )
            lines = []
            for item in payload[:10]:
                name = str(item.get("fullname") or item.get("name") or "unknown")
                number = item.get("number", "?")
                lines.append(f"- {name} #{number}")
            return (
                "【执行的操作】\n通过 MCP [jenkins MCP] 调用 `get_running_builds`\n\n"
                "【关键结果】\n当前正在运行的构建：\n"
                + "\n".join(lines)
                + "\n\n【风险提示】\n[无]\n\n"
                + "【建议下一步】\n如需继续查看某个构建日志，请直接说"查看 <job名> 构建日志"。"
            )
        logger.warning("[feishu_bot] Jenkins get_running_builds 返回不可解析: %s", raw[:300])
        return None

    if any(keyword in lower for keyword in ("队列", "排队", "queue", "等待构建")):
        raw, payload = await _call_jenkins_mcp("get_all_queue_items")
        if isinstance(payload, list):
            if not payload:
                return (
                    "【执行的操作】\n通过 MCP [jenkins MCP] 调用 `get_all_queue_items`\n\n"
                    "【关键结果】\n当前 Jenkins 队列为空。\n\n"
                    "【风险提示】\n[无]\n\n"
                    "【建议下一步】\n如需查看任务状态，请直接说"列出 Jenkins job"。"
                )
            lines = []
            for item in payload[:10]:
                task = item.get("task") or {}
                name = task.get("name") or task.get("fullDisplayName") or "unknown"
                lines.append(f"- {name}")
            return (
                "【执行的操作】\n通过 MCP [jenkins MCP] 调用 `get_all_queue_items`\n\n"
                "【关键结果】\n当前排队中的任务：\n"
                + "\n".join(lines)
                + "\n\n【风险提示】\n[无]\n\n"
                + "【建议下一步】\n如需继续查看某个任务详情，请直接说"查看 <job名> 状态"。"
            )
        logger.warning("[feishu_bot] Jenkins get_all_queue_items 返回不可解析: %s", raw[:300])
        return None

    if any(keyword in lower for keyword in ("节点", "node", "agent", "执行器")):
        raw, payload = await _call_jenkins_mcp("get_all_nodes")
        if isinstance(payload, list):
            if not payload:
                return (
                    "【执行的操作】\n通过 MCP [jenkins MCP] 调用 `get_all_nodes`\n\n"
                    "【关键结果】\n当前没有查询到 Jenkins 节点信息。\n\n"
                    "【风险提示】\n- 可能是 Jenkins API 返回为空。\n\n"
                    "【建议下一步】\n请检查 Jenkins 主节点和 Agent 是否在线。"
                )
            lines = []
            offline_nodes: list[str] = []
            for item in payload[:10]:
                name = str(item.get("displayName") or item.get("name") or "unknown")
                offline = bool(item.get("offline"))
                lines.append(f"- {name}：{'离线' if offline else '在线'}")
                if offline:
                    offline_nodes.append(name)
            risk_text = "[无]" if not offline_nodes else "- 存在离线节点：" + "、".join(offline_nodes)
            return (
                "【执行的操作】\n通过 MCP [jenkins MCP] 调用 `get_all_nodes`\n\n"
                "【关键结果】\n"
                + "\n".join(lines)
                + "\n\n【风险提示】\n"
                + risk_text
                + "\n\n【建议下一步】\n如需继续排查离线节点，请到 Jenkins 节点详情页检查连接状态与执行器日志。"
            )
        logger.warning("[feishu_bot] Jenkins get_all_nodes 返回不可解析: %s", raw[:300])
        return None

    is_log_query = any(kw in lower for kw in ("日志", "log", "console", "详细", "输出", "报错"))

    raw, payload = await _call_jenkins_mcp("get_all_items")
    if not isinstance(payload, list):
        logger.warning("[feishu_bot] Jenkins get_all_items 返回不可解析: %s", raw[:300])
        return None

    matched = None
    for item in payload:
        fullname = str(item.get("fullname") or item.get("name") or "").strip()
        if fullname and fullname.lower() in lower:
            matched = item
            break

    # 用户明确要看日志 + 匹配到 job → 直接拉 console output
    if matched and is_log_query:
        fullname = str(matched.get("fullname") or matched.get("name") or "")
        build_number = (matched.get("lastBuild") or {}).get("number")
        log_params: dict[str, Any] = {"fullname": fullname}
        if build_number is not None:
            log_params["number"] = build_number
        log_raw, log_payload = await _call_jenkins_mcp("get_build_console_output", log_params)
        log_text = ""
        if isinstance(log_payload, str):
            log_text = log_payload.strip()
        elif isinstance(log_payload, dict):
            log_text = str(log_payload.get("output") or log_payload.get("text") or log_raw).strip()
        else:
            # payload 解析失败，直接用原始文本（去掉 MCP 头部）
            log_text = log_raw.split("\n", 1)[-1].strip() if "\n" in log_raw else log_raw.strip()
        # 截取最后 2000 字（Jenkins 日志末尾通常有失败原因）
        if len(log_text) > 2000:
            log_text = "...(前段已省略)...\n" + log_text[-2000:]
        build_label = f" (#{build_number})" if build_number is not None else ""
        return (
            "【执行的操作】\n"
            f"通过 MCP [{_get_jenkins_mcp_name()}] 调用 `get_build_console_output`，"
            f"获取 `{fullname}`{build_label} 的构建日志\n\n"
            "【关键结果】\n"
            f"```\n{log_text or '(日志为空)'}\n```\n\n"
            "【风险提示】\n[无]\n\n"
            f"【建议下一步】\n如需重新触发构建，请明确说「触发构建 {fullname}」（需确认后执行）。"
        )

    if matched:
        fullname = str(matched.get("fullname") or matched.get("name") or "")
        detail_raw, detail = await _call_jenkins_mcp("get_item", {"fullname": fullname})
        if not isinstance(detail, dict):
            logger.warning("[feishu_bot] Jenkins get_item 返回不可解析: %s", detail_raw[:300])
            return None

        last_build = detail.get("lastBuild") or {}
        build_number = last_build.get("number")
        result_text = ""
        extra_lines: list[str] = []
        if build_number is not None:
            build_raw, build = await _call_jenkins_mcp(
                "get_build",
                {"fullname": fullname, "number": build_number},
            )
            if isinstance(build, dict):
                result_text = _jenkins_status_text(str(detail.get("color") or ""), str(build.get("result") or ""))
                extra_lines.append(f"- 最近构建号：#{build_number}")
                extra_lines.append(f"- 最近构建结果：{result_text}")
                extra_lines.append(f"- 构建中：{'是' if build.get('building') else '否'}")
            else:
                logger.warning("[feishu_bot] Jenkins get_build 返回不可解析: %s", build_raw[:300])

        if not extra_lines:
            extra_lines.append(f"- 当前状态：{_jenkins_status_text(str(detail.get('color') or ''))}")
            if build_number is not None:
                extra_lines.append(f"- 最近构建号：#{build_number}")

        return (
            "【执行的操作】\n"
            f"通过 MCP [{_get_jenkins_mcp_name()}] 调用 `get_item` 查询 `{fullname}`"
            + ("，并继续调用 `get_build` 获取最近构建详情" if build_number is not None else "")
            + "\n\n【关键结果】\n"
            + "\n".join(extra_lines)
            + "\n\n【风险提示】\n"
            + ("- 该任务最近一次构建失败。" if result_text == "失败" else "[无]")
            + f"\n\n【建议下一步】\n如需继续排查，请直接说「查看 {fullname} 构建日志」。"
        )

    total = len(payload)
    failed_jobs = [
        str(item.get("fullname") or item.get("name") or "unknown")
        for item in payload
        if _jenkins_status_text(str(item.get("color") or "")) == "失败"
    ]
    lines = []
    for item in payload[:10]:
        name = str(item.get("fullname") or item.get("name") or "unknown")
        status = _jenkins_status_text(str(item.get("color") or ""))
        lines.append(f"- {name}：{status}")

    risk_text = "[无]" if not failed_jobs else "- 最近失败任务：" + "、".join(failed_jobs[:5])
    return (
        "【执行的操作】\n通过 MCP [jenkins MCP] 调用 `get_all_items`\n\n"
        f"【关键结果】\n当前共查询到 {total} 个 Jenkins 任务：\n"
        + "\n".join(lines)
        + ("\n- ...（其余任务已省略）" if total > 10 else "")
        + "\n\n【风险提示】\n"
        + risk_text
        + "\n\n【建议下一步】\n如需继续查看某个任务，请直接说"查看 <job名> 状态"或"查看 <job名> 构建日志"。"
    )


    '''

async def _call_es_mcp_api(path: str, params: dict[str, Any] | None = None) -> tuple[str, dict[str, Any] | None]:
    from agent.tools import call_mcp_tool

    payload = {"method": "GET", "path": path}
    if params:
        payload["params"] = params
    params = json.dumps(payload, ensure_ascii=False)
    result = await call_mcp_tool.ainvoke(
        {"mcp_name": "ES MCP", "action": "general_api_request", "params": params}
    )
    return result, _extract_mcp_json(str(result))


async def _try_es_status_mcp_reply(text: str) -> str | None:
    if not _is_es_status_question(text):
        return None

    health_raw, health = await _call_es_mcp_api("/_cluster/health")
    stats_raw, stats = await _call_es_mcp_api(
        "/_cluster/stats",
        params={"filter_path": "indices.count,indices.docs.count,indices.store.size_in_bytes"},
    )
    if not health:
        return (
            "【执行的操作】\n"
            "通过 MCP [ES MCP] 调用 general_api_request GET /_cluster/health。\n\n"
            "【关键结果】\n"
            f"{health_raw}\n\n"
            "【风险提示】\n"
            "未能解析 MCP 返回的集群健康 JSON，请先检查 ES MCP 服务与后端 ES 地址。\n\n"
            "【建议下一步】\n"
            "确认 ES MCP 地址是否为 SSE 入口，并检查 MCP 服务连接的 Elasticsearch 地址。"
        )

    status = str(health.get("status") or "unknown").lower()
    status_text = {"green": "正常", "yellow": "警告", "red": "异常"}.get(status, "未知")
    unassigned = int(health.get("unassigned_shards") or 0)
    nodes = int(health.get("number_of_nodes") or 0)
    data_nodes = int(health.get("number_of_data_nodes") or 0)
    active_percent = float(health.get("active_shards_percent_as_number") or 0)
    index_count = stats.get("indices", {}).get("count", "?") if stats else "?"
    doc_count = stats.get("indices", {}).get("docs", {}).get("count", "?") if stats else "?"
    store_bytes = stats.get("indices", {}).get("store", {}).get("size_in_bytes", 0) if stats else 0
    store_mb = int(store_bytes or 0) // 1024 // 1024

    risks: list[str] = []
    if status != "green":
        risks.append(f"集群当前为 {status}，不是 green。")
    if unassigned > 0:
        risks.append(f"存在 {unassigned} 个未分配分片，可能影响副本完整性或后续恢复能力。")
    if nodes <= 1:
        risks.append("当前只有 1 个节点，副本分片无法分配是 yellow 的常见原因。")
    if not risks:
        risks.append("当前未发现明显集群健康风险。")

    next_step = (
        "优先检查未分配分片原因：GET /_cluster/allocation/explain；如果是单节点测试集群，可将索引副本数调整为 0，"
        "如果是生产集群建议补充数据节点后再恢复副本。"
        if unassigned > 0
        else "继续观察节点、分片与磁盘水位，保持定期巡检。"
    )

    return (
        "【执行的操作】\n"
        "通过 MCP [ES MCP] 调用 general_api_request：GET /_cluster/health 与 GET /_cluster/stats。\n\n"
        "【关键结果】\n"
        f"集群名称：{health.get('cluster_name')}\n"
        f"健康状态：{status}（{status_text}）\n"
        f"节点数量：{nodes}，数据节点：{data_nodes}\n"
        f"分片状态：活跃主分片 {health.get('active_primary_shards')}，活跃总分片 {health.get('active_shards')}，未分配 {unassigned}\n"
        f"活跃分片比例：{active_percent:.2f}%\n"
        f"索引数：{index_count}，文档数：{doc_count}，存储约：{store_mb} MB\n\n"
        "【风险提示】\n"
        + "\n".join(f"- {risk}" for risk in risks)
        + "\n\n【建议下一步】\n"
        + next_step
    )


async def _try_es_indices_mcp_reply(text: str) -> str | None:
    if not _is_es_indices_question(text):
        return None

    from agent.tools import call_mcp_tool

    return await call_mcp_tool.ainvoke(
        {"mcp_name": "ES MCP", "action": "list_indices", "params": "{}"}
    )


async def _invoke_via_langgraph(text: str, session_key: str, message_id: str | None = None) -> str:
    """直接调用 LangGraph ReAct（进程内，性能更优）。"""
    from langchain_core.messages import HumanMessage
    from agent.graph import build_graph
    from routers.agent import _get_checkpointer

    checkpointer = await _get_checkpointer()
    mode = _detect_mode(text)
    logger.info("[feishu_bot] 检测到模式: %s (session=%s)", mode, session_key)
    graph = build_graph(mode, checkpointer)
    config = {
        "configurable": {"thread_id": session_key},
        "recursion_limit": 40,
    }

    full_text = ""
    react_steps: list[dict[str, str]] = []
    progress_enabled = bool(message_id) and _get_behavior("show_trace", default=False)

    async for event in graph.astream_events(
        {"messages": [HumanMessage(content=text)]},
        config=config,
        version="v2",
    ):
        event_name = event.get("event")

        if event_name == "on_tool_start":
            tool_name = str(event.get("name") or "")
            tool_input = _compact(event.get("data", {}).get("input", {}), limit=260)
            step = {"tool": tool_name, "input": tool_input, "output": ""}
            react_steps.append(step)
            if progress_enabled and len(react_steps) <= 6:
                try:
                    await _send_text(message_id or "", f"🧠 ReAct 第 {len(react_steps)} 步：调用 `{tool_name}`\n参数：{tool_input}")
                except Exception:
                    logger.exception("[feishu_bot] 发送 ReAct 进度失败")
            continue

        if event_name == "on_tool_end":
            tool_name = str(event.get("name") or "")
            output = _compact(event.get("data", {}).get("output", ""), limit=360)
            for step in reversed(react_steps):
                if step.get("tool") == tool_name and not step.get("output"):
                    step["output"] = output
                    break
            continue

        if event_name != "on_chat_model_stream":
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

    final_text = full_text.strip()

    # 流式文本为空时，从图状态中读取最终消息内容作为兜底
    if not final_text:
        try:
            state = await graph.aget_state(config)
            msgs = state.values.get("messages", []) if state and state.values else []
            if msgs:
                last_msg = msgs[-1]
                raw_content = getattr(last_msg, "content", None)
                if isinstance(raw_content, str):
                    final_text = raw_content.strip()
                elif isinstance(raw_content, list):
                    parts = [
                        p.get("text", "") if isinstance(p, dict) else str(p)
                        for p in raw_content
                    ]
                    final_text = "".join(parts).strip()
            if final_text:
                logger.info("[feishu_bot] 流式文本为空，从图状态兜底获取回答（%d 字符）", len(final_text))
        except Exception as exc:
            logger.warning("[feishu_bot] 从图状态读取兜底文本失败: %s", exc)

    show_trace = _get_behavior("show_trace", default=False)
    trace_text = _format_react_trace(react_steps) if show_trace else ""
    if trace_text:
        if final_text:
            return f"{trace_text}\n\n【最终回答】\n{final_text}"
        return f"{trace_text}\n\n未收到模型最终文本，但工具调用已完成。"
    return final_text


async def _generate_reply(text: str, session_key: str, message_id: str | None = None) -> str:
    from agent.ops_quick_actions import quick_actions_enabled

    reply = None
    if quick_actions_enabled("FEISHU"):
        reply = await _try_es_status_mcp_reply(text)
        if not reply:
            reply = await _try_es_indices_mcp_reply(text)
        if reply:
            logger.info("[feishu_bot] 使用 ES MCP 快速路径 session=%s", session_key)
    if not reply and quick_actions_enabled("FEISHU"):
        from agent.k8s_quick_actions import get_k8s_quick_reply

        reply = await get_k8s_quick_reply(text)
        if reply:
            logger.info("[feishu_bot] 使用 K8S MCP 快速路径 session=%s", session_key)
    if not reply:
        reply = await _try_jenkins_mcp_reply(text)
        if reply:
            logger.info("[feishu_bot] 使用 Jenkins MCP 兜底回复 session=%s", session_key)
    if not reply:
        from agent.external_executor import get_agent_executor, run_configured_executor

        executor_mode = get_agent_executor("FEISHU")
        if executor_mode in {"aiops_cli", "external_cli"}:
            logger.info(
                "[feishu_bot] 使用 %s 执行器 session=%s",
                executor_mode,
                session_key,
            )
            if message_id and executor_mode == "external_cli" and _env_bool("FEISHU_REACT_PROGRESS", True):
                await _send_text(message_id, "🧠 已转交外部 Claude Code/CLI 执行器，正在 ReAct 分析与执行……")
            reply = await run_configured_executor(text, session_key, channel="feishu")
        else:
            reply = await _invoke_via_langgraph(text, session_key, message_id=message_id)

    if not reply:
        logger.warning("[feishu_bot] AI 返回空文本 session=%s", session_key)
        reply = "抱歉，AI 未能生成回答，请稍后重试或换一种提问方式。"
    return reply


async def _process_message(message_id: str, text: str, session_key: str) -> None:
    lock = _get_session_lock(session_key)
    async with lock:
        try:
            reply = await _generate_reply(text, session_key, message_id=message_id)
            await _send_text(message_id, reply)
        except Exception as exc:
            logger.exception("[feishu_bot] AI 处理失败 session=%s", session_key)
            try:
                await _send_text(message_id, f"抱歉，处理消息时出错：{exc}")
            except Exception:
                logger.exception("[feishu_bot] 发送错误提示失败")


def _extract_message_for_processing(
    envelope: Mapping[str, Any],
    *,
    require_group_mention: bool = True,
    require_message_id: bool = True,
) -> tuple[dict[str, str] | None, str]:
    event_type = str(envelope.get("event_type") or "")
    if event_type != "im.message.receive_v1":
        return None, f"忽略未处理事件类型: {event_type or '<empty>'}"

    event = envelope.get("event") or {}
    if not isinstance(event, Mapping):
        return None, "event 不是 JSON 对象"

    message_payload = _extract_text_message(event)
    if not message_payload:
        return None, "不是文本消息或缺少 message 字段"

    chat_type = message_payload["chat_type"]
    raw_text = message_payload["raw_text"]
    mentions = message_payload["mentions"]

    if require_group_mention and chat_type == "group" and not mentions and "<at" not in raw_text:
        return None, "群聊消息未 @ 机器人，已按当前策略忽略"

    text = str(message_payload["text"] or "").strip()
    message_id = str(message_payload["message_id"] or "")
    if not text:
        return None, "消息文本为空"
    if require_message_id and not message_id:
        return None, "缺少 message_id，无法使用飞书 reply 接口"

    session_key = _build_session_key(event)
    return {
        "chat_type": chat_type,
        "message_id": message_id,
        "session_key": session_key,
        "text": text,
    }, ""


def _dispatch_event(envelope: Mapping[str, Any]) -> None:
    require_group_mention = _env_bool("FEISHU_REQUIRE_MENTION", True)
    message, reason = _extract_message_for_processing(
        envelope,
        require_group_mention=require_group_mention,
    )
    if not message:
        if reason:
            logger.info("[feishu_bot] %s", reason)
        return

    chat_type = message["chat_type"]
    session_key = message["session_key"]
    text = message["text"]
    message_id = message["message_id"]
    logger.info(
        "[feishu_bot] 收到消息 type=%s session=%s text=%r",
        chat_type,
        session_key,
        text[:80],
    )
    asyncio.create_task(_process_message(message_id, text, session_key))


def _preview_reply_requested(request: Request, payload: Mapping[str, Any]) -> bool:
    values = [
        request.query_params.get("preview_reply", ""),
        request.query_params.get("debug_reply", ""),
        request.headers.get("X-AIOPS-Preview-Reply", ""),
        str(payload.get("preview_reply") or ""),
    ]
    return any(str(value).strip().lower() in {"1", "true", "yes", "on"} for value in values)


async def _preview_event_reply(envelope: Mapping[str, Any]) -> dict[str, Any]:
    message, reason = _extract_message_for_processing(
        envelope,
        require_group_mention=False,
        require_message_id=False,
    )
    if not message:
        return {
            "ok": False,
            "preview": True,
            "reason": reason or "无法从事件中提取可处理文本",
            "reply": "",
        }

    session_key = message["session_key"] or "preview"
    text = message["text"]
    lock = _get_session_lock(session_key)
    async with lock:
        try:
            reply = await _generate_reply(text, session_key, message_id=None)
        except Exception as exc:
            logger.exception("[feishu_bot] preview_reply 生成失败 session=%s", session_key)
            return {
                "ok": False,
                "preview": True,
                "reason": f"生成回复失败: {exc}",
                "chat_type": message["chat_type"],
                "message_id": message["message_id"],
                "session_key": session_key,
                "text": text,
                "reply": "",
            }
    return {
        "ok": True,
        "preview": True,
        "chat_type": message["chat_type"],
        "message_id": message["message_id"],
        "session_key": session_key,
        "text": text,
        "reply": reply,
    }


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
    if _preview_reply_requested(request, payload):
        return JSONResponse(await _preview_event_reply(envelope))

    event_key = _extract_event_key(envelope)
    if event_key and _is_event_processed(event_key):
        return JSONResponse({"ok": True})

    if event_key:
        _remember_event(event_key)

    _dispatch_event(envelope)
    return JSONResponse({"ok": True})
