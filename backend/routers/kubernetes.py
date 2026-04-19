"""Kubernetes 集群管理路由 — /api/k8s/*"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/k8s", tags=["kubernetes"])


def _settings() -> dict:
    try:
        import json
        from pathlib import Path
        p = Path(__file__).parent.parent / "data" / "settings.json"
        if p.exists():
            return json.loads(p.read_text())
    except Exception:
        pass
    return {}


_DEFAULT_KUBECONFIG = (
    os.path.join(os.path.dirname(__file__), "..", "data", "kubeconfig")
)


def _resolve_kubeconfig() -> str:
    """kubeconfig 查找顺序：
    1. settings.json 中 k8s_kubeconfig 字段
    2. 环境变量 K8S_KUBECONFIG
    3. 项目内置路径 backend/data/kubeconfig（推荐直接放这里）
    4. 系统默认 ~/.kube/config
    """
    from pathlib import Path
    explicit = _settings().get("k8s_kubeconfig") or os.getenv("K8S_KUBECONFIG", "")
    if explicit:
        return explicit
    builtin = Path(_DEFAULT_KUBECONFIG).resolve()
    if builtin.exists():
        return str(builtin)
    return os.path.expanduser("~/.kube/config")


def _get_client():
    """返回 (v1_core, apps_v1) 客户端，支持 kubeconfig 路径配置。"""
    from kubernetes import client, config as k8s_config

    kubeconfig = _resolve_kubeconfig()
    try:
        k8s_config.load_kube_config(config_file=kubeconfig or None)
    except Exception:
        try:
            k8s_config.load_incluster_config()
        except Exception as exc:
            raise RuntimeError(f"无法加载 kubeconfig: {exc}") from exc

    return client.CoreV1Api(), client.AppsV1Api()


def _phase_class(phase: str) -> str:
    return {"Running": "ok", "Succeeded": "ok", "Pending": "warn",
            "Failed": "err", "Unknown": "err"}.get(phase, "warn")


def _pod_status(pod) -> str:
    phase = pod.status.phase or "Unknown"
    if phase == "Running":
        not_ready = [c for c in (pod.status.conditions or [])
                     if c.type == "Ready" and c.status != "True"]
        if not_ready:
            return "NotReady"
    return phase


# ── Namespaces ────────────────────────────────────────────────────────────────

@router.get("/namespaces")
async def list_namespaces():
    try:
        v1, _ = _get_client()
        ns_list = v1.list_namespace()
        return [
            {
                "name": ns.metadata.name,
                "status": ns.status.phase or "Active",
                "age": str(ns.metadata.creation_timestamp)[:10] if ns.metadata.creation_timestamp else "",
                "labels": ns.metadata.labels or {},
            }
            for ns in ns_list.items
        ]
    except Exception as exc:
        logger.warning("[k8s] list_namespaces failed: %s", exc)
        raise HTTPException(502, f"k8s 连接失败: {exc}")


# ── Pods ─────────────────────────────────────────────────────────────────────

@router.get("/pods")
async def list_pods(namespace: str = Query("", description="命名空间，空=全部")):
    try:
        v1, _ = _get_client()
        pods = (
            v1.list_pod_for_all_namespaces()
            if not namespace
            else v1.list_namespaced_pod(namespace)
        )
        result = []
        for pod in pods.items:
            status = _pod_status(pod)
            containers = [
                {
                    "name": c.name,
                    "image": c.image,
                    "ready": False,
                    "restarts": 0,
                }
                for c in (pod.spec.containers or [])
            ]
            if pod.status.container_statuses:
                for cs in pod.status.container_statuses:
                    for c in containers:
                        if c["name"] == cs.name:
                            c["ready"] = cs.ready or False
                            c["restarts"] = cs.restart_count or 0
            result.append({
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "status": status,
                "statusClass": _phase_class(status),
                "node": pod.spec.node_name or "",
                "ip": pod.status.pod_ip or "",
                "containers": containers,
                "restarts": sum(c["restarts"] for c in containers),
                "age": str(pod.metadata.creation_timestamp)[:10] if pod.metadata.creation_timestamp else "",
            })
        return result
    except Exception as exc:
        logger.warning("[k8s] list_pods failed: %s", exc)
        raise HTTPException(502, f"k8s 连接失败: {exc}")


# ── Deployments ───────────────────────────────────────────────────────────────

@router.get("/deployments")
async def list_deployments(namespace: str = Query("", description="命名空间，空=全部")):
    try:
        _, apps = _get_client()
        deps = (
            apps.list_deployment_for_all_namespaces()
            if not namespace
            else apps.list_namespaced_deployment(namespace)
        )
        result = []
        for d in deps.items:
            desired  = d.spec.replicas or 0
            ready    = (d.status.ready_replicas or 0)
            updated  = (d.status.updated_replicas or 0)
            avail    = (d.status.available_replicas or 0)
            ok = ready == desired and desired > 0
            result.append({
                "name":      d.metadata.name,
                "namespace": d.metadata.namespace,
                "desired":   desired,
                "ready":     ready,
                "updated":   updated,
                "available": avail,
                "status":    "Ready" if ok else ("Progressing" if updated < desired else "Degraded"),
                "statusClass": "ok" if ok else "warn",
                "age": str(d.metadata.creation_timestamp)[:10] if d.metadata.creation_timestamp else "",
                "images": [c.image for c in (d.spec.template.spec.containers or [])],
            })
        return result
    except Exception as exc:
        logger.warning("[k8s] list_deployments failed: %s", exc)
        raise HTTPException(502, f"k8s 连接失败: {exc}")


# ── Services ──────────────────────────────────────────────────────────────────

@router.get("/services")
async def list_services(namespace: str = Query("", description="命名空间，空=全部")):
    try:
        v1, _ = _get_client()
        svcs = (
            v1.list_service_for_all_namespaces()
            if not namespace
            else v1.list_namespaced_service(namespace)
        )
        result = []
        for s in svcs.items:
            ports = []
            for p in (s.spec.ports or []):
                entry = f"{p.port}"
                if p.node_port:
                    entry += f":{p.node_port}"
                if p.protocol and p.protocol != "TCP":
                    entry += f"/{p.protocol}"
                ports.append(entry)
            result.append({
                "name":       s.metadata.name,
                "namespace":  s.metadata.namespace,
                "type":       s.spec.type or "ClusterIP",
                "clusterIP":  s.spec.cluster_ip or "",
                "externalIP": ", ".join(s.spec.external_i_ps or []) or (
                    s.status.load_balancer.ingress[0].ip
                    if s.status.load_balancer and s.status.load_balancer.ingress
                    else ""
                ),
                "ports":  ports,
                "age": str(s.metadata.creation_timestamp)[:10] if s.metadata.creation_timestamp else "",
            })
        return result
    except Exception as exc:
        logger.warning("[k8s] list_services failed: %s", exc)
        raise HTTPException(502, f"k8s 连接失败: {exc}")


# ── Nodes ─────────────────────────────────────────────────────────────────────

@router.get("/nodes")
async def list_nodes():
    try:
        v1, _ = _get_client()
        nodes = v1.list_node()
        result = []
        for n in nodes.items:
            ready = "Unknown"
            for cond in (n.status.conditions or []):
                if cond.type == "Ready":
                    ready = "Ready" if cond.status == "True" else "NotReady"
            info = n.status.node_info or {}
            result.append({
                "name":    n.metadata.name,
                "status":  ready,
                "statusClass": "ok" if ready == "Ready" else "err",
                "roles":   ", ".join(
                    k.split("/")[-1]
                    for k in (n.metadata.labels or {})
                    if k.startswith("node-role.kubernetes.io/")
                ) or "worker",
                "version": getattr(info, "kubelet_version", ""),
                "os":      getattr(info, "os_image", ""),
                "arch":    getattr(info, "architecture", ""),
                "age": str(n.metadata.creation_timestamp)[:10] if n.metadata.creation_timestamp else "",
            })
        return result
    except Exception as exc:
        logger.warning("[k8s] list_nodes failed: %s", exc)
        raise HTTPException(502, f"k8s 连接失败: {exc}")


# ── Summary ───────────────────────────────────────────────────────────────────

@router.get("/summary")
async def cluster_summary():
    try:
        v1, apps = _get_client()
        import asyncio

        pods    = v1.list_pod_for_all_namespaces()
        deps    = apps.list_deployment_for_all_namespaces()
        nodes   = v1.list_node()

        total_pods   = len(pods.items)
        running_pods = sum(1 for p in pods.items if _pod_status(p) == "Running")
        total_deps   = len(deps.items)
        ready_deps   = sum(1 for d in deps.items
                          if (d.status.ready_replicas or 0) == (d.spec.replicas or 0) and d.spec.replicas)
        total_nodes  = len(nodes.items)
        ready_nodes  = sum(1 for n in nodes.items
                          if any(c.type == "Ready" and c.status == "True"
                                 for c in (n.status.conditions or [])))
        return {
            "pods":        {"total": total_pods,  "running": running_pods},
            "deployments": {"total": total_deps,  "ready":   ready_deps},
            "nodes":       {"total": total_nodes, "ready":   ready_nodes},
        }
    except Exception as exc:
        logger.warning("[k8s] summary failed: %s", exc)
        raise HTTPException(502, f"k8s 连接失败: {exc}")
