"""Kubernetes 查询工具 + K8S MCP 桥接。"""
from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from ._shared import _allowed_k8s_clusters, _find_enabled_mcp, _visible_k8s_clusters


@tool
async def get_k8s_summary(config: RunnableConfig = None) -> str:
    """查询 Kubernetes 集群总览：节点数、Pod 数、Deployment 数、命名空间列表。
    用户询问 k8s 状态、集群情况、容器平台状态时使用。"""
    try:
        from routers.kubernetes import _get_client

        clusters = _visible_k8s_clusters(config)
        if not clusters:
            return "当前权限范围内没有可访问的 K8s 集群"

        def _icon(ok: int, total: int) -> str:
            return "[正常]" if ok == total else f"[{total - ok}个异常]"

        sections: list[str] = []
        for cluster in clusters:
            core_v1, apps_v1 = _get_client(cluster["id"])
            nodes = core_v1.list_node(timeout_seconds=8)
            pods = core_v1.list_pod_for_all_namespaces(timeout_seconds=8)
            deps = apps_v1.list_deployment_for_all_namespaces(timeout_seconds=8)
            namespaces = core_v1.list_namespace(timeout_seconds=8)

            total_nodes = len(nodes.items)
            ready_nodes = sum(
                1
                for node in nodes.items
                if any(cond.type == "Ready" and cond.status == "True" for cond in node.status.conditions)
            )
            total_pods = len(pods.items)
            running_pods = sum(1 for pod in pods.items if (pod.status.phase or "") == "Running")
            total_deps = len(deps.items)
            ready_deps = sum(
                1
                for dep in deps.items
                if (dep.status.ready_replicas or 0) >= (dep.spec.replicas or 1)
            )
            ns_names = [item.metadata.name for item in namespaces.items]
            sections.append(
                "\n".join(
                    [
                        f"**K8s 集群总览 / {cluster['name']}**",
                        f"节点：{ready_nodes}/{total_nodes} 就绪 {_icon(ready_nodes, total_nodes)}",
                        f"Pod：{running_pods}/{total_pods} 运行中 {_icon(running_pods, total_pods)}",
                        f"Deployment：{ready_deps}/{total_deps} 就绪 {_icon(ready_deps, total_deps)}",
                        f"命名空间：{', '.join(ns_names[:12]) or '无'}",
                    ]
                )
            )
        return "\n\n".join(sections)
    except Exception as e:
        return f"K8s 连接失败：{e}（请检查系统配置中的 kubeconfig）"


@tool
async def get_k8s_pods(namespace: str = "", config: RunnableConfig = None) -> str:
    """查询 Kubernetes Pod 列表及运行状态。
    namespace=命名空间（空=全部命名空间）。
    用户询问某个命名空间的 Pod 状态、哪些 Pod 异常/重启时使用。"""
    try:
        from routers.kubernetes import _get_client

        clusters = _visible_k8s_clusters(config)
        if not clusters:
            return "当前权限范围内没有可访问的 K8s 集群"

        pods_data: list[dict] = []
        for cluster in clusters:
            core_v1, _ = _get_client(cluster["id"])
            pods = (
                core_v1.list_namespaced_pod(namespace, timeout_seconds=8)
                if namespace
                else core_v1.list_pod_for_all_namespaces(timeout_seconds=8)
            )
            for pod in pods.items:
                pods_data.append(
                    {
                        "cluster": cluster["name"],
                        "namespace": pod.metadata.namespace,
                        "name": pod.metadata.name,
                        "phase": pod.status.phase or "?",
                        "restarts": sum(cs.restart_count for cs in (pod.status.container_statuses or [])),
                    }
                )

        if not pods_data:
            return f"命名空间 {namespace or '全部'} 下无 Pod"

        pods_data.sort(
            key=lambda item: (
                item["phase"] == "Running",
                item["cluster"],
                item["namespace"],
                item["name"],
            )
        )
        lines = [f"**Pod 列表**（{namespace or '全部命名空间'}，共 {len(pods_data)} 个）\n"]
        for item in pods_data[:50]:
            flag = "" if item["phase"] == "Running" else "[异常] "
            lines.append(
                f"{flag}[{item['cluster']}][{item['namespace']}] {item['name']}  "
                f"状态:{item['phase']}  重启:{item['restarts']}次"
            )
        if len(pods_data) > 50:
            lines.append(f"...（共 {len(pods_data)} 个，仅展示前 50 个）")
        return "\n".join(lines)
    except Exception as e:
        return f"查询 Pod 失败：{e}"


@tool
async def get_k8s_nodes(config: RunnableConfig = None) -> str:
    """查询 Kubernetes 节点列表及状态（CPU/内存分配、是否就绪）。
    用户询问节点健康状态、节点资源时使用。"""
    try:
        from routers.kubernetes import _get_client

        clusters = _visible_k8s_clusters(config)
        if not clusters:
            return "当前权限范围内没有可访问的 K8s 集群"

        nodes_data: list[dict] = []
        for cluster in clusters:
            core_v1, _ = _get_client(cluster["id"])
            nodes = core_v1.list_node(timeout_seconds=8)
            for node in nodes.items:
                nodes_data.append(
                    {
                        "cluster": cluster["name"],
                        "name": node.metadata.name,
                        "ready": next(
                            (cond.status for cond in node.status.conditions if cond.type == "Ready"),
                            "Unknown",
                        ),
                        "cpu": node.status.capacity.get("cpu", "?"),
                        "mem": node.status.capacity.get("memory", "?"),
                    }
                )

        if not nodes_data:
            return "集群无节点"

        lines = [f"**节点列表**（共 {len(nodes_data)} 个）\n"]
        for item in nodes_data:
            flag = "" if item["ready"] == "True" else "[异常] "
            lines.append(
                f"{flag}[{item['cluster']}] {item['name']}  Ready:{item['ready']}  "
                f"CPU:{item['cpu']}  内存:{item['mem']}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"查询节点失败：{e}"


@tool
async def get_k8s_namespaces(config: RunnableConfig = None) -> str:
    """查询 Kubernetes 命名空间列表。"""
    try:
        from routers.kubernetes import _get_client

        clusters = _visible_k8s_clusters(config)
        if not clusters:
            return "当前权限范围内没有可访问的 K8s 集群"

        namespaces: list[dict] = []
        for cluster in clusters:
            core_v1, _ = _get_client(cluster["id"])
            ns_list = core_v1.list_namespace(timeout_seconds=8)
            for item in ns_list.items:
                namespaces.append(
                    {
                        "cluster": cluster["name"],
                        "name": item.metadata.name,
                        "status": item.status.phase or "Active",
                        "age": str(item.metadata.creation_timestamp)[:10] if item.metadata.creation_timestamp else "",
                    }
                )

        if not namespaces:
            return "当前集群没有命名空间数据"

        lines = [f"**命名空间列表**（共 {len(namespaces)} 个）\n"]
        for item in namespaces[:30]:
            lines.append(
                f"[{item.get('cluster', '?')}] {item.get('name', '?')}  "
                f"状态:{item.get('status', '?')}  创建:{item.get('age', '?')}"
            )
        if len(namespaces) > 30:
            lines.append(f"... 共 {len(namespaces)} 个，仅展示前 30 个")
        return "\n".join(lines)
    except Exception as exc:
        return f"查询命名空间失败：{exc}"


@tool
async def get_k8s_deployments(namespace: str = "", config: RunnableConfig = None) -> str:
    """查询 Kubernetes Deployment 列表及就绪状态。namespace=命名空间（空=全部）。"""
    try:
        from routers.kubernetes import _get_client

        clusters = _visible_k8s_clusters(config)
        if not clusters:
            return "当前权限范围内没有可访问的 K8s 集群"

        deployments: list[dict] = []
        for cluster in clusters:
            _, apps = _get_client(cluster["id"])
            items = (
                apps.list_deployment_for_all_namespaces(timeout_seconds=8)
                if not namespace
                else apps.list_namespaced_deployment(namespace, timeout_seconds=8)
            )
            for item in items.items:
                desired = item.spec.replicas or 0
                ready = item.status.ready_replicas or 0
                updated = item.status.updated_replicas or 0
                deployments.append(
                    {
                        "cluster": cluster["name"],
                        "namespace": item.metadata.namespace,
                        "name": item.metadata.name,
                        "desired": desired,
                        "ready": ready,
                        "status": "Ready" if ready == desired and desired > 0 else ("Progressing" if updated < desired else "Degraded"),
                    }
                )

        if not deployments:
            return f"命名空间 {namespace or '全部'} 下无 Deployment"

        lines = [
            f"**Deployment 列表**（{namespace or '全部命名空间'}，共 {len(deployments)} 个）\n"
        ]
        items = sorted(
            deployments,
            key=lambda item: (
                item.get("status") == "Ready",
                item.get("cluster", ""),
                item.get("namespace", ""),
                item.get("name", ""),
            ),
        )
        for item in items[:30]:
            flag = "" if item.get("status") == "Ready" else "[异常] "
            lines.append(
                f"{flag}[{item.get('cluster', '?')}][{item.get('namespace', '?')}] {item.get('name', '?')}  "
                f"状态:{item.get('status', '?')}  副本:{item.get('ready', 0)}/{item.get('desired', 0)}"
            )
        if len(deployments) > 30:
            lines.append(f"... 共 {len(deployments)} 个，仅展示前 30 个")
        return "\n".join(lines)
    except Exception as exc:
        return f"查询 Deployment 失败：{exc}"


@tool
async def get_k8s_services(namespace: str = "", config: RunnableConfig = None) -> str:
    """查询 Kubernetes Service 列表及暴露端口。namespace=命名空间（空=全部）。"""
    try:
        from routers.kubernetes import _get_client

        clusters = _visible_k8s_clusters(config)
        if not clusters:
            return "当前权限范围内没有可访问的 K8s 集群"

        services: list[dict] = []
        for cluster in clusters:
            core_v1, _ = _get_client(cluster["id"])
            items = (
                core_v1.list_service_for_all_namespaces(timeout_seconds=8)
                if not namespace
                else core_v1.list_namespaced_service(namespace, timeout_seconds=8)
            )
            for item in items.items:
                ports = []
                for port in (item.spec.ports or []):
                    entry = f"{port.port}"
                    if port.node_port:
                        entry += f":{port.node_port}"
                    if port.protocol and port.protocol != "TCP":
                        entry += f"/{port.protocol}"
                    ports.append(entry)
                services.append(
                    {
                        "cluster": cluster["name"],
                        "namespace": item.metadata.namespace,
                        "name": item.metadata.name,
                        "type": item.spec.type or "ClusterIP",
                        "clusterIP": item.spec.cluster_ip or "",
                        "ports": ports,
                    }
                )

        if not services:
            return f"命名空间 {namespace or '全部'} 下无 Service"

        lines = [f"**Service 列表**（{namespace or '全部命名空间'}，共 {len(services)} 个）\n"]
        for item in services[:30]:
            ports = ",".join(item.get("ports", []) or []) or "-"
            lines.append(
                f"[{item.get('cluster', '?')}][{item.get('namespace', '?')}] {item.get('name', '?')}  "
                f"类型:{item.get('type', '?')}  ClusterIP:{item.get('clusterIP', '-') or '-'}  端口:{ports}"
            )
        if len(services) > 30:
            lines.append(f"... 共 {len(services)} 个，仅展示前 30 个")
        return "\n".join(lines)
    except Exception as exc:
        return f"查询 Service 失败：{exc}"


@tool
async def call_k8s_mcp(action: str, params: str = "{}", config: RunnableConfig = None) -> str:
    """调用已启用的 Kubernetes / K8S MCP。
    action=工具名，例如 list_pods / list_nodes / list_namespaces / list_deployments / list_services。"""
    if _allowed_k8s_clusters(config) is not None:
        return "当前账号的 K8s 查询已按集群权限控制，不支持直接调用 K8s MCP，请使用内置 K8s 工具"
    mcp = _find_enabled_mcp(
        keywords=("k8s", "kubernetes", "kube"),
        preferred_names=("K8S MCP", "Kubernetes MCP"),
    )
    if not mcp:
        return "未找到已启用的 K8S MCP，请先在智能体配置中添加并启用名称包含 K8S / Kubernetes / Kube 的 MCP。"
    # 延迟 import 避免循环依赖
    from .mcp_bridge import call_mcp_tool

    return await call_mcp_tool.ainvoke(
        {
            "mcp_name": str(mcp.get("name", "")),
            "action": action,
            "params": params,
        },
        config=config,
    )


@tool
async def list_k8s_mcp_tools() -> str:
    """列出已启用 Kubernetes / K8S MCP 支持的工具。"""
    mcp = _find_enabled_mcp(
        keywords=("k8s", "kubernetes", "kube"),
        preferred_names=("K8S MCP", "Kubernetes MCP"),
    )
    if not mcp:
        return "未找到已启用的 K8S MCP，请先在智能体配置中添加并启用名称包含 K8S / Kubernetes / Kube 的 MCP。"
    from .mcp_bridge import list_mcp_tools

    return await list_mcp_tools.ainvoke({"mcp_name": str(mcp.get("name", ""))})


@tool
async def diagnose_k8s_pod(pod_name: str, namespace: str = "", config: RunnableConfig = None) -> str:
    """一键诊断指定 Pod：状态 + 容器就绪/重启原因 + Warning 事件 + 最近错误日志。
    用户报告某个 Pod 异常、CrashLoop、OOM、启动失败、频繁重启时优先使用本工具，
    一次调用拿全证据，不需要分别调 pods/logs/events。pod_name 支持模糊匹配。"""
    import asyncio as _asyncio

    try:
        from routers.kubernetes import _get_client

        clusters = _visible_k8s_clusters(config)
        if not clusters:
            return "当前权限范围内没有可访问的 K8s 集群"
        cluster = clusters[0]
        core_v1, _ = _get_client(cluster["id"])

        def _collect() -> str:
            pods = core_v1.list_pod_for_all_namespaces(timeout_seconds=10).items \
                if not namespace else core_v1.list_namespaced_pod(namespace, timeout_seconds=10).items
            target = next((p for p in pods if pod_name in p.metadata.name), None)
            if target is None:
                return f"未找到名称包含「{pod_name}」的 Pod（命名空间：{namespace or '全部'}）"

            ns = target.metadata.namespace
            name = target.metadata.name
            lines = [
                f"**Pod 诊断 / {name}**（ns={ns}，节点={target.spec.node_name or '-'}，"
                f"状态={target.status.phase}，PodIP={target.status.pod_ip or '-'}）",
            ]

            # 1. 容器状态与重启原因
            bad_container = ""
            for cs in target.status.container_statuses or []:
                state_text = "running"
                if cs.state and cs.state.waiting:
                    state_text = f"waiting({cs.state.waiting.reason or '?'})"
                elif cs.state and cs.state.terminated:
                    state_text = f"terminated({cs.state.terminated.reason or '?'})"
                last_reason = ""
                if cs.last_state and cs.last_state.terminated:
                    t = cs.last_state.terminated
                    last_reason = f"，上次退出：{t.reason or '?'}(exit={t.exit_code})"
                mark = "✅" if cs.ready else "⚠️"
                lines.append(f"- {mark} 容器 {cs.name}：{state_text}，重启 {cs.restart_count} 次{last_reason}")
                if not cs.ready and not bad_container:
                    bad_container = cs.name

            # 2. Warning 事件（最近 8 条）
            try:
                events = core_v1.list_namespaced_event(
                    ns, field_selector=f"involvedObject.name={name}", timeout_seconds=8
                ).items
                warnings = [e for e in events if (e.type or "") == "Warning"][-8:]
                if warnings:
                    lines.append("**Warning 事件：**")
                    for e in warnings:
                        lines.append(f"- [{e.reason}] {(e.message or '')[:160]}（x{e.count or 1}）")
            except Exception as exc:
                lines.append(f"- 事件读取失败：{exc}")

            # 3. 最近日志尾部（未就绪容器优先，看崩溃前日志）
            try:
                if bad_container:
                    try:
                        log_text = core_v1.read_namespaced_pod_log(
                            name, ns, container=bad_container,
                            tail_lines=30, timeout_seconds=8, previous=True)
                        log_label = "上次崩溃前"
                    except Exception:
                        log_text = core_v1.read_namespaced_pod_log(
                            name, ns, container=bad_container,
                            tail_lines=30, timeout_seconds=8)
                        log_label = "当前"
                else:
                    log_text = core_v1.read_namespaced_pod_log(
                        name, ns, tail_lines=30, timeout_seconds=8)
                    log_label = "当前"
                if log_text:
                    lines.append(f"**最近日志（{log_label} 30 行尾部）：**")
                    lines.append("```\n" + log_text.strip()[-1800:] + "\n```")
            except Exception as exc:
                lines.append(f"- 日志读取失败：{exc}")

            return "\n".join(lines)

        return await _asyncio.to_thread(_collect)
    except Exception as e:
        return f"Pod 诊断失败：{e}"


@tool
async def get_k8s_events(namespace: str = "", only_warning: bool = True,
                         config: RunnableConfig = None) -> str:
    """查询 K8s 集群事件（默认只看 Warning）。排查 OOMKilled、镜像拉取失败、
    调度失败、探针失败等问题时使用；namespace 留空查全部命名空间。"""
    import asyncio as _asyncio

    try:
        from routers.kubernetes import _get_client

        clusters = _visible_k8s_clusters(config)
        if not clusters:
            return "当前权限范围内没有可访问的 K8s 集群"
        core_v1, _ = _get_client(clusters[0]["id"])

        def _collect() -> str:
            items = (core_v1.list_namespaced_event(namespace, timeout_seconds=10).items
                     if namespace else
                     core_v1.list_event_for_all_namespaces(timeout_seconds=10).items)
            if only_warning:
                items = [e for e in items if (e.type or "") == "Warning"]
            items = sorted(items, key=lambda e: str(e.last_timestamp or e.event_time or ""))[-20:]
            if not items:
                return f"最近没有{'Warning ' if only_warning else ''}事件（命名空间：{namespace or '全部'}）"
            lines = [f"**K8s {'Warning ' if only_warning else ''}事件（最近 {len(items)} 条）**"]
            for e in items:
                obj = e.involved_object
                ts = str(e.last_timestamp or e.event_time or "")[:19]
                lines.append(
                    f"- {ts} [{e.reason}] {obj.kind}/{obj.name}（ns={obj.namespace or '-'}）："
                    f"{(e.message or '')[:150]}（x{e.count or 1}）")
            return "\n".join(lines)

        return await _asyncio.to_thread(_collect)
    except Exception as e:
        return f"事件查询失败：{e}"


__all__ = [
    "get_k8s_summary", "get_k8s_pods", "get_k8s_nodes",
    "get_k8s_namespaces", "get_k8s_deployments", "get_k8s_services",
    "diagnose_k8s_pod", "get_k8s_events",
    "call_k8s_mcp", "list_k8s_mcp_tools",
]
