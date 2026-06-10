"""MCP 通用调用 / 列举工具。"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from ._shared import (
    _AGENT_CONFIG_PATH,
    _allowed_k8s_clusters,
    _call_es_mcp_list_indices,
    _call_sse_mcp,
    _call_streamable_http_mcp,
    _is_es_mcp,
    _is_k8s_mcp_name,
    _list_sse_mcp_tools_sync,
    _list_streamable_http_mcp_tools_sync,
    _normalize_sse_url,
)


@tool
async def call_mcp_tool(
    mcp_name: str,
    action: str,
    params: str = "{}",
    config: RunnableConfig = None,
) -> str:
    """调用已配置的 MCP（Model Context Protocol）工具执行操作。
    mcp_name=MCP 名称（如 'Prometheus MCP'、'Redis MCP'），
    action=要执行的动作或接口路径（如 'query' / '/metrics'），
    params=JSON 格式参数字符串（如 '{"query":"up"}'）。
    使用前先确认 MCP 已在智能体配置中启用。"""
    try:
        if _is_k8s_mcp_name(mcp_name) and _allowed_k8s_clusters(config) is not None:
            return "当前账号的 K8s 查询已按集群权限控制，不支持直接调用 K8s MCP，请使用内置 K8s 工具"
        with open(_AGENT_CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)

        mcp = next(
            (m for m in cfg.get("mcps", [])
             if m.get("name", "").lower() == mcp_name.lower() and m.get("enabled")),
            None,
        )
        if not mcp:
            enabled_names = [m["name"] for m in cfg.get("mcps", []) if m.get("enabled")]
            return (
                f"MCP '{mcp_name}' 未找到或未启用。\n"
                f"当前已启用的 MCP：{', '.join(enabled_names) or '无'}"
            )

        mcp_type = mcp.get("type", "http")
        url = mcp.get("url", "").rstrip("/")

        try:
            body = json.loads(params) if params.strip() else {}
        except Exception:
            body = {"query": params}

        import httpx

        if mcp_type == "http":
            endpoint = url + ("/" + action.lstrip("/") if action else "")
            async with httpx.AsyncClient(timeout=12) as client:
                resp = await client.post(endpoint, json=body)
                resp.raise_for_status()
                result = resp.text[:2000]
            return f"**MCP [{mcp['name']}] 返回结果**\n{result}"

        if mcp_type == "sse":
            if _is_es_mcp(mcp["name"]) and action in ("list_indices", "cat_indices"):
                return await _call_es_mcp_list_indices(mcp["name"], url, body)
            return await _call_sse_mcp(mcp["name"], url, action, body)

        if mcp_type == "streamable_http":
            return await _call_streamable_http_mcp(mcp["name"], url, action, body)

        return f"MCP 类型 '{mcp_type}' 暂不支持在线调用（支持 http / sse / streamable_http 类型）"

    except FileNotFoundError:
        return "agent_config.json 不存在，请先在智能体配置页面保存配置"
    except Exception as exc:
        return f"调用 MCP 失败：{exc}"


@tool
async def list_mcp_tools(mcp_name: str) -> str:
    """列出指定 MCP 服务器支持的工具（actions）清单，调用前先用此工具发现可用操作。
    mcp_name=MCP 名称（如 'ES MCP'）。"""
    try:
        with open(_AGENT_CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        mcp = next(
            (m for m in cfg.get("mcps", [])
             if m.get("name", "").lower() == mcp_name.lower() and m.get("enabled")),
            None,
        )
        if not mcp:
            return f"MCP '{mcp_name}' 未找到或未启用"

        mcp_type = mcp.get("type", "http")
        url = mcp.get("url", "").rstrip("/")

        if mcp_type == "sse":
            try:
                loop = asyncio.get_event_loop()
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    raw_tools = await loop.run_in_executor(
                        pool, lambda: _list_sse_mcp_tools_sync(_normalize_sse_url(url))
                    )
                tools = [{"name": t.name, "description": t.description or ""} for t in raw_tools]
            except Exception as e:
                return f"获取 SSE MCP 工具列表失败：{e}"
        elif mcp_type == "streamable_http":
            try:
                loop = asyncio.get_event_loop()
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    raw_tools = await loop.run_in_executor(
                        pool, lambda: _list_streamable_http_mcp_tools_sync(url.rstrip("/"))
                    )
                tools = [{"name": t.name, "description": t.description or ""} for t in raw_tools]
            except Exception as e:
                return f"获取 streamable HTTP MCP 工具列表失败：{e}"
        else:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url + "/tools/list", json={})
                resp.raise_for_status()
                data = resp.json()
            tools = data.get("result", {}).get("tools", data.get("tools", []))

        if not tools:
            return f"MCP [{mcp_name}] 工具列表为空"

        lines = [f"**MCP [{mcp_name}] 可用工具（共 {len(tools)} 个）**\n"]
        for t in tools:
            name = t.get("name", "?") if isinstance(t, dict) else t
            desc = t.get("description", "") if isinstance(t, dict) else ""
            lines.append(f"- {name}：{desc}")
        return "\n".join(lines)
    except Exception as exc:
        return f"获取 MCP 工具列表失败：{exc}"


@tool
async def list_available_mcps() -> str:
    """列出当前已配置并启用的 MCP 工具列表，用于了解可用的 MCP 能力后再决定调用哪个。"""
    try:
        with open(_AGENT_CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        mcps = cfg.get("mcps", [])
        enabled = [m for m in mcps if m.get("enabled")]
        if not enabled:
            return "当前无已启用的 MCP，请在智能体配置页面添加并启用 MCP"
        lines = [f"**已启用 MCP（共 {len(enabled)} 个）**\n"]
        for m in enabled:
            t = m.get('type', '?')
            callable_mark = "" if t in ("http", "sse", "streamable_http") else " [不支持在线调用]"
            lines.append(f"- {m['name']}  类型:{t}  地址:{m.get('url','?')}{callable_mark}")
        return "\n".join(lines)
    except Exception as exc:
        return f"读取 MCP 配置失败：{exc}"


__all__ = ["call_mcp_tool", "list_mcp_tools", "list_available_mcps"]
