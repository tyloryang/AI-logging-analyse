"""Kubernetes quick actions for deterministic chat, CLI and Feishu handling."""

from __future__ import annotations

import json
import re

_K8S_KEYWORDS = (
    "k8s",
    "kubernetes",
    "kube",
    "kubectl",
    "pod",
    "pods",
    "node",
    "nodes",
    "节点",
    "namespace",
    "namespaces",
    "命名空间",
    "deployment",
    "deployments",
    "svc",
)

_DESTRUCTIVE_KEYWORDS = (
    "删除",
    "重启",
    "扩容",
    "缩容",
    "修改",
    "创建",
    "delete",
    "restart",
    "scale",
    "patch",
    "apply",
    "create",
    "exec",
)

_KIND_KEYWORDS = {
    "nodes": ("node", "nodes", "节点", "node状态", "节点状态"),
    "namespaces": ("namespace", "namespaces", "命名空间", "ns"),
    "deployments": ("deployment", "deployments", "deploy", "工作负载", "副本"),
    "services": ("service", "services", "svc", "服务"),
    "pods": ("pod", "pods", "容器"),
}

_MCP_ACTION_CANDIDATES = {
    "summary": (
        "cluster_summary",
        "get_cluster_summary",
        "summary",
        "cluster_info",
        "get_cluster_info",
    ),
    "nodes": ("list_nodes", "get_nodes", "nodes"),
    "namespaces": ("list_namespaces", "get_namespaces", "namespaces"),
    "deployments": ("list_deployments", "get_deployments", "deployments"),
    "services": ("list_services", "get_services", "services"),
    "pods": ("list_pods", "get_pods", "pods"),
}


def mentions_k8s(text: str) -> bool:
    lower = text.lower()
    return any(keyword in lower for keyword in _K8S_KEYWORDS)


def is_readonly_k8s_question(text: str) -> bool:
    lower = text.lower()
    if not mentions_k8s(text):
        return False
    return not any(keyword in lower for keyword in _DESTRUCTIVE_KEYWORDS)


def detect_k8s_kind(text: str) -> str:
    lower = text.lower()
    for kind, keywords in _KIND_KEYWORDS.items():
        if any(keyword in lower for keyword in keywords):
            return kind
    return "summary"


def extract_namespace(text: str) -> str:
    stripped = text.strip()
    patterns = (
        r"(?:命名空间|namespace|namespaces|ns)[\s:：=`'\"]+([a-zA-Z0-9_.-]+)",
        r"(?:-n|--namespace)[\s=`'\"]+([a-zA-Z0-9_.-]+)",
        r"[`'\"]([a-zA-Z0-9_.-]+)[`'\"]\s*(?:命名空间|namespace|ns)",
    )
    for pattern in patterns:
        match = re.search(pattern, stripped, flags=re.IGNORECASE)
        if not match:
            continue
        value = (match.group(1) or "").strip()
        if value and value.lower() not in {"k8s", "kubernetes", "namespace", "ns"}:
            return value
    return ""


def _looks_like_failure(result: str) -> bool:
    lower = result.lower()
    return any(
        marker in lower
        for marker in (
            "调用 mcp 失败",
            "sse mcp 调用失败",
            "未找到已启用",
            "tool not found",
            "unknown tool",
            "invalid tool",
            "no such tool",
            "not supported",
            "connection refused",
            "timed out",
            "traceback",
            "exception",
            "404",
            "500 internal",
        )
    )


async def _try_k8s_mcp(kind: str, namespace: str) -> tuple[str | None, str]:
    from agent.tools import call_k8s_mcp

    params: dict[str, str] = {}
    if namespace and kind in {"pods", "deployments", "services"}:
        params["namespace"] = namespace

    last_error = ""
    for action in _MCP_ACTION_CANDIDATES.get(kind, ()):
        result = await call_k8s_mcp.ainvoke(
            {
                "action": action,
                "params": json.dumps(params, ensure_ascii=False),
            }
        )
        text = str(result)
        if not _looks_like_failure(text):
            ns_hint = f"（namespace={namespace}）" if namespace else ""
            return f"【执行的操作】\n通过 K8S MCP 调用 {action}{ns_hint}。\n\n【关键结果】\n{text}", ""
        last_error = text
    return None, last_error


async def _fallback_builtin(kind: str, namespace: str) -> str:
    from agent.tools import (
        get_k8s_deployments,
        get_k8s_namespaces,
        get_k8s_nodes,
        get_k8s_pods,
        get_k8s_services,
        get_k8s_summary,
    )

    if kind == "nodes":
        return str(await get_k8s_nodes.ainvoke({}))
    if kind == "namespaces":
        return str(await get_k8s_namespaces.ainvoke({}))
    if kind == "deployments":
        return str(await get_k8s_deployments.ainvoke({"namespace": namespace}))
    if kind == "services":
        return str(await get_k8s_services.ainvoke({"namespace": namespace}))
    if kind == "pods":
        return str(await get_k8s_pods.ainvoke({"namespace": namespace}))
    return str(await get_k8s_summary.ainvoke({}))


async def get_k8s_quick_reply(text: str) -> str | None:
    if not is_readonly_k8s_question(text):
        return None

    kind = detect_k8s_kind(text)
    namespace = extract_namespace(text)

    mcp_reply, mcp_error = await _try_k8s_mcp(kind, namespace)
    if mcp_reply:
        return mcp_reply

    fallback = await _fallback_builtin(kind, namespace)
    if not mcp_error:
        return fallback

    return (
        "【K8S MCP】未获得可用结果，已切换为本地 kubeconfig 兜底查询。\n"
        f"失败信息：{mcp_error[:500]}\n\n"
        "【兜底结果】\n"
        f"{fallback}"
    )
