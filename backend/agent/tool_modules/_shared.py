"""跨工具的共享 helper —— 不带 @tool 装饰，单纯提供给 domain 模块复用。"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import re

from langchain_core.runnables import RunnableConfig

# 报告目录指向 backend/reports（与原 tools.py 行为一致）
_REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "reports")


# ── RunnableConfig 提取 ────────────────────────────────────────────────────────

def _configurable(config: RunnableConfig | None) -> dict:
    return config.get("configurable", {}) if config else {}


def _allowed_groups(config: RunnableConfig | None) -> list[str] | None:
    return _configurable(config).get("allowed_groups")


def _filter_hosts_by_groups(hosts: list[dict], allowed_groups: list[str] | None) -> list[dict]:
    if allowed_groups is None:
        return hosts
    return [host for host in hosts if host.get("group", "") in allowed_groups]


def _allowed_k8s_clusters(config: RunnableConfig | None) -> list[str] | None:
    return _configurable(config).get("allowed_k8s_clusters")


def _visible_k8s_clusters(config: RunnableConfig | None) -> list[dict]:
    from routers.kubernetes import _load_clusters

    clusters = _load_clusters()
    allowed_cluster_ids = _allowed_k8s_clusters(config)
    if allowed_cluster_ids is None:
        return clusters
    return [cluster for cluster in clusters if cluster.get("id") in allowed_cluster_ids]


def _is_k8s_mcp_name(name: str) -> bool:
    lower = str(name or "").lower()
    return any(keyword in lower for keyword in ("k8s", "kubernetes", "kube"))


# ── MCP SSE / Streamable HTTP 客户端 ──────────────────────────────────────────

def _call_sse_mcp_sync(sse_url: str, method: str, params: dict) -> list:
    """在全新事件循环中同步执行 SSE MCP 调用，避免 anyio TaskGroup 与外层 asyncio 冲突。"""
    async def _inner():
        from mcp.client.sse import sse_client
        from mcp import ClientSession
        async with sse_client(sse_url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(method, params)
        return result.content or []

    return asyncio.run(_inner())


def _list_sse_mcp_tools_sync(sse_url: str) -> list:
    async def _inner():
        from mcp.client.sse import sse_client
        from mcp import ClientSession
        async with sse_client(sse_url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                resp = await session.list_tools()
        return resp.tools

    return asyncio.run(_inner())


def _call_streamable_http_mcp_sync(server_url: str, method: str, params: dict) -> list:
    async def _inner():
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(server_url) as (read, write, _get_session_id):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(method, params)
        return result.content or []

    return asyncio.run(_inner())


def _list_streamable_http_mcp_tools_sync(server_url: str) -> list:
    async def _inner():
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(server_url) as (read, write, _get_session_id):
            async with ClientSession(read, write) as session:
                await session.initialize()
                resp = await session.list_tools()
        return resp.tools

    return asyncio.run(_inner())


def _normalize_sse_url(sse_url: str) -> str:
    url = str(sse_url or "").strip().rstrip("/")
    lower = url.lower()
    if lower.endswith("/sse"):
        return url
    if lower.endswith("/mcp"):
        return f"{url[:-4]}/sse"
    if url:
        return f"{url}/sse"
    return url


def _mcp_content_to_text(content: list) -> str:
    parts = []
    for item in content:
        text = getattr(item, "text", None) or str(item)
        parts.append(text)
    return "\n".join(parts) if parts else "(无返回内容)"


async def _call_sse_mcp_raw(sse_url: str, method: str, params: dict) -> str:
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        content = await loop.run_in_executor(
            pool, lambda: _call_sse_mcp_sync(_normalize_sse_url(sse_url), method, params)
        )
    return _mcp_content_to_text(content)


async def _call_sse_mcp(mcp_name: str, sse_url: str, method: str, params: dict) -> str:
    try:
        output = await _call_sse_mcp_raw(sse_url, method, params)
        return f"**MCP [{mcp_name}] 返回结果**\n{output[:3000]}"
    except Exception as exc:
        return f"SSE MCP 调用失败：{exc}"


async def _call_streamable_http_mcp_raw(server_url: str, method: str, params: dict) -> str:
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        content = await loop.run_in_executor(
            pool, lambda: _call_streamable_http_mcp_sync(server_url.rstrip("/"), method, params)
        )
    return _mcp_content_to_text(content)


async def _call_streamable_http_mcp(mcp_name: str, server_url: str, method: str, params: dict) -> str:
    try:
        output = await _call_streamable_http_mcp_raw(server_url, method, params)
        return f"**MCP [{mcp_name}] 返回结果**\n{output[:3000]}"
    except Exception as exc:
        return f"Streamable HTTP MCP 调用失败：{exc}"


# ── agent_config.json 路径与 MCP 查找 ─────────────────────────────────────────

_AGENT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "agent_config.json")


def _find_enabled_mcp(
    keywords: tuple[str, ...],
    preferred_names: tuple[str, ...] = (),
) -> dict | None:
    try:
        with open(_AGENT_CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return None

    preferred_map = {name.lower(): idx for idx, name in enumerate(preferred_names)}
    matches = [
        item
        for item in cfg.get("mcps", [])
        if item.get("enabled")
        and any(keyword.lower() in str(item.get("name", "")).lower() for keyword in keywords)
    ]
    if not matches:
        return None

    def _score(item: dict) -> tuple[int, int, str]:
        name = str(item.get("name", ""))
        lower = name.lower()
        preferred_rank = preferred_map.get(lower, len(preferred_map) + 1)
        keyword_rank = min(
            (
                idx
                for idx, keyword in enumerate(keywords)
                if keyword.lower() in lower
            ),
            default=len(keywords) + 1,
        )
        return (preferred_rank, keyword_rank, name)

    return sorted(matches, key=_score)[0]


def _is_es_mcp(name: str) -> bool:
    lower = name.lower()
    return "es" in lower or "elastic" in lower or "opensearch" in lower


def _format_es_indices_result(raw: str, pattern: str = "*", limit: int = 80) -> str:
    try:
        data = json.loads(raw)
    except Exception:
        return raw[:3000]

    if not isinstance(data, list):
        return raw[:3000]
    if not data:
        return f"ES 未找到匹配 '{pattern}' 的索引"

    health_counts: dict[str, int] = {}
    for item in data:
        if isinstance(item, dict):
            health = str(item.get("health") or "unknown")
            health_counts[health] = health_counts.get(health, 0) + 1

    health_text = "，".join(f"{k}:{v}" for k, v in sorted(health_counts.items()))
    lines = [
        f"**MCP [ES MCP] 索引列表**（pattern={pattern}，共 {len(data)} 个，{health_text}）",
        "",
        f"{'索引名':<46} {'健康':>7} {'状态':>7} {'文档数':>10} {'大小':>10} {'主分片':>6} {'副本':>4}",
        "-" * 98,
    ]
    for item in data[:limit]:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"{str(item.get('index', '')):<46} "
            f"{str(item.get('health', '?')):>7} "
            f"{str(item.get('status', '?')):>7} "
            f"{str(item.get('docs.count', '0')):>10} "
            f"{str(item.get('store.size', '?')):>10} "
            f"{str(item.get('pri', '?')):>6} "
            f"{str(item.get('rep', '?')):>4}"
        )
    if len(data) > limit:
        lines.append(f"... 仅展示前 {limit} 个，剩余 {len(data) - limit} 个可用更精确 pattern 过滤。")
    return "\n".join(lines)


async def _call_es_mcp_list_indices(mcp_name: str, url: str, body: dict) -> str:
    pattern = str(body.get("pattern") or body.get("index") or body.get("name") or "*").strip() or "*"
    raw = await _call_sse_mcp_raw(
        url,
        "general_api_request",
        {
            "method": "GET",
            "path": f"/_cat/indices/{pattern}",
            "params": {
                "format": "json",
                "s": "index",
                "h": "index,health,status,docs.count,store.size,pri,rep",
            },
        },
    )
    return _format_es_indices_result(raw, pattern=pattern)


# ── ES 直连 base url ──────────────────────────────────────────────────────────

def _es_base_url() -> str:
    url = os.getenv("ES_URL", "").strip().rstrip("/")
    if url:
        return url
    try:
        with open(_AGENT_CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        for m in cfg.get("mcps", []):
            if "es" in m.get("name", "").lower() and m.get("enabled"):
                raw = m.get("url", "")
                raw = re.sub(r"/sse$", "", raw)
                raw = re.sub(r":8000", ":9200", raw)
                return raw.rstrip("/")
    except Exception:
        pass
    return "http://192.168.9.226:9200"


# ── Jenkins client 构造 ────────────────────────────────────────────────────
# data/jenkins.json 现在存的是多实例列表 [{id,name,url,username,token,default}]
# 兼容三种数据形态：list（多实例）/ dict（旧单实例）/ 空；三者都退化不到再走 env。

def _jenkins_client():
    from jenkins_client import JenkinsClient
    from pathlib import Path
    from json_snapshot_store import read_json_file

    cfg_file = Path(__file__).resolve().parent.parent.parent / "data" / "jenkins.json"
    data = read_json_file(cfg_file, default=None)

    inst = None
    if isinstance(data, list) and data:
        # 优先 default=True 的实例，否则用第一个
        inst = next((x for x in data if isinstance(x, dict) and x.get("default")), None) or data[0]
    elif isinstance(data, dict) and data.get("url"):
        # 兼容旧单对象格式
        inst = data

    if inst and isinstance(inst, dict):
        url      = (inst.get("url") or "").strip()
        username = (inst.get("username") or "").strip()
        token    = (inst.get("token") or "").strip()
    else:
        url      = os.getenv("JENKINS_URL", "").strip()
        username = os.getenv("JENKINS_USERNAME", "").strip()
        token    = os.getenv("JENKINS_TOKEN", "").strip()

    if not url:
        return None, "Jenkins 未配置，请到「CI/CD → Jenkins」页添加实例（填 URL / 用户名 / API Token 后保存并勾选『设为默认』）"
    return JenkinsClient(url, username, token), None


# ── SSH 命令白名单与黑名单 ────────────────────────────────────────────────────

_SAFE_CMDS = {
    "df", "du", "free", "top", "ps", "uptime", "uname",
    "netstat", "ss", "ifconfig", "ip", "ping", "traceroute",
    "ls", "cat", "tail", "head", "grep", "find",
    "systemctl", "journalctl", "service",
    "docker", "kubectl",
    "date", "who", "w", "id", "hostname",
    "vmstat", "iostat", "sar", "dstat",
    "lsof", "strace",
}

_DANGER_PATTERNS = [
    "rm ", "rm\t", "rmdir", "> /", "dd ", "mkfs", "fdisk",
    "shutdown", "reboot", "halt", "poweroff",
    "chmod 777", "chown root",
    "iptables -F", "ufw disable",
    "passwd", "userdel", "useradd",
    ":(){:|:&}", "fork bomb",
    "wget ", "curl -o ", "bash <(",
]


def _check_safe(command: str) -> str | None:
    cmd = command.strip().lower()
    for pat in _DANGER_PATTERNS:
        if pat in cmd:
            return f"禁止执行高危操作：包含 '{pat}'"
    first_word = cmd.split()[0] if cmd.split() else ""
    first_word = first_word.lstrip("./")
    if first_word and first_word not in _SAFE_CMDS:
        pass
    return None


__all__ = [
    # config / 权限
    "_configurable", "_allowed_groups", "_filter_hosts_by_groups",
    "_allowed_k8s_clusters", "_visible_k8s_clusters", "_is_k8s_mcp_name",
    # MCP 客户端
    "_call_sse_mcp", "_call_sse_mcp_raw", "_call_sse_mcp_sync",
    "_call_streamable_http_mcp", "_call_streamable_http_mcp_raw",
    "_list_sse_mcp_tools_sync", "_list_streamable_http_mcp_tools_sync",
    "_normalize_sse_url", "_mcp_content_to_text",
    # 配置查找
    "_find_enabled_mcp", "_AGENT_CONFIG_PATH",
    # ES
    "_is_es_mcp", "_format_es_indices_result", "_call_es_mcp_list_indices", "_es_base_url",
    # Jenkins
    "_jenkins_client",
    # SSH
    "_SAFE_CMDS", "_DANGER_PATTERNS", "_check_safe",
    # 路径
    "_REPORTS_DIR",
]
