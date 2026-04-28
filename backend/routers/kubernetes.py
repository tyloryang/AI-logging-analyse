"""Kubernetes 集群管理路由 — /api/k8s/*"""
from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, WebSocket, Depends
from pydantic import BaseModel
from sqlalchemy import select

from auth.deps import current_user, require_admin
from auth.models import User
from auth.session import get_session
from db import AsyncSessionLocal
from state import get_user_allowed_k8s_clusters

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/k8s", tags=["kubernetes"])

_DATA_FILE = Path(__file__).parent.parent / "data" / "k8s_clusters.json"
_DEFAULT_KUBECONFIG = os.path.join(os.path.dirname(__file__), "..", "data", "kubeconfig")
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class K8sClusterPayload(BaseModel):
    name: str
    kubeconfig: str
    context: str = ""
    description: str = ""


def _settings() -> dict:
    try:
        p = Path(__file__).parent.parent / "data" / "settings.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _safe_age(value) -> str:
    return str(value)[:10] if value else ""


def _normalize_cluster(item: dict) -> dict:
    return {
        "id": str(item.get("id") or str(uuid.uuid4())[:8]),
        "name": str(item.get("name") or "未命名集群"),
        "kubeconfig": str(item.get("kubeconfig") or ""),
        "context": str(item.get("context") or ""),
        "description": str(item.get("description") or ""),
        "is_default": bool(item.get("is_default", False)),
    }


def _apply_default_cluster(clusters: list[dict], target_id: str | None = None) -> tuple[list[dict], bool]:
    if not clusters:
        return clusters, False

    changed = False
    if target_id:
        found = False
        for item in clusters:
            should_default = item["id"] == target_id
            found = found or should_default
            if item.get("is_default", False) != should_default:
                item["is_default"] = should_default
                changed = True
        if found:
            return clusters, changed

    default_indexes = [index for index, item in enumerate(clusters) if item.get("is_default")]
    if not default_indexes:
        clusters[0]["is_default"] = True
        changed = True
    elif len(default_indexes) > 1:
        first = default_indexes[0]
        for index in default_indexes[1:]:
            clusters[index]["is_default"] = False
            changed = True
        if not clusters[first].get("is_default"):
            clusters[first]["is_default"] = True
            changed = True

    return clusters, changed


def _save_clusters(clusters: list[dict]) -> None:
    _DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    _DATA_FILE.write_text(
        json.dumps(clusters, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _resolve_runtime_kubeconfig_path(raw_path: str) -> str:
    path_value = str(raw_path or "").strip()
    if not path_value:
        return ""

    expanded = os.path.expandvars(os.path.expanduser(path_value))
    if not expanded:
        return ""

    if os.name != "nt" and Path(expanded).is_absolute():
        return str(Path(expanded))

    if expanded.startswith("/"):
        return expanded

    if Path(expanded).is_absolute():
        return str(Path(expanded))

    candidates: list[Path] = []
    seen: set[str] = set()
    for base in (Path.cwd(), _PROJECT_ROOT, _BACKEND_ROOT):
        candidate = (base / expanded).resolve(strict=False)
        candidate_key = str(candidate).lower()
        if candidate_key in seen:
            continue
        seen.add(candidate_key)
        candidates.append(candidate)
        if candidate.exists():
            return str(candidate)

    return str((_PROJECT_ROOT / expanded).resolve(strict=False))


def _resolve_legacy_kubeconfig() -> str:
    explicit = str(_settings().get("k8s_kubeconfig") or os.getenv("K8S_KUBECONFIG", "")).strip()
    if explicit:
        return _resolve_runtime_kubeconfig_path(explicit)

    builtin = Path(_DEFAULT_KUBECONFIG).resolve()
    if builtin.exists():
        return str(builtin)

    home = Path(os.path.expanduser("~/.kube/config")).expanduser()
    if home.exists():
        return str(home)

    return ""


def _seed_clusters_from_legacy() -> list[dict]:
    kubeconfig = _resolve_legacy_kubeconfig()
    if not kubeconfig:
        return []
    return [
        {
            "id": "default",
            "name": "默认集群",
            "kubeconfig": kubeconfig,
            "context": "",
            "description": "由系统原有单集群 kubeconfig 自动迁移生成",
            "is_default": True,
        }
    ]


def _load_clusters() -> list[dict]:
    if _DATA_FILE.exists():
        try:
            data = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                clusters = [_normalize_cluster(item) for item in data]
                clusters, changed = _apply_default_cluster(clusters)
                if changed:
                    _save_clusters(clusters)
                return clusters
        except Exception as exc:
            logger.warning("[k8s] 读取集群配置失败，回退默认配置: %s", exc)

    clusters = _seed_clusters_from_legacy()
    if clusters:
        _save_clusters(clusters)
    return clusters


def _get_cluster(cluster_id: str | None = None) -> dict:
    clusters = _load_clusters()
    if not clusters:
        raise HTTPException(status_code=404, detail="未配置 Kubernetes 集群，请先在容器管理中添加集群")
    if cluster_id:
        cluster = next((item for item in clusters if item["id"] == cluster_id), None)
        if not cluster:
            raise HTTPException(status_code=404, detail=f"集群 {cluster_id} 不存在")
        return cluster
    return next((item for item in clusters if item.get("is_default")), clusters[0])


def _resolve_kubeconfig(cluster_id: str | None = None) -> str:
    if cluster_id:
        return _resolve_runtime_kubeconfig_path(_get_cluster(cluster_id).get("kubeconfig", ""))

    clusters = _load_clusters()
    if clusters:
        return _resolve_runtime_kubeconfig_path(_get_cluster().get("kubeconfig", ""))
    return _resolve_legacy_kubeconfig()


def _get_client(cluster_id: str | None = None):
    """返回 (v1_core, apps_v1) 客户端，支持多集群 kubeconfig/context 切换。"""
    from kubernetes import client

    api_client = _get_api_client(cluster_id)
    return client.CoreV1Api(api_client), client.AppsV1Api(api_client)


def _get_api_client(cluster_id: str | None = None):
    from kubernetes import config as k8s_config

    cluster = _get_cluster(cluster_id)
    kubeconfig = _resolve_runtime_kubeconfig_path(cluster.get("kubeconfig") or "")
    context = str(cluster.get("context") or "").strip() or None

    if not kubeconfig:
        raise RuntimeError(f"集群 [{cluster['name']}] 未配置 kubeconfig 路径")

    try:
        return k8s_config.new_client_from_config(config_file=kubeconfig, context=context)
    except Exception as exc:
        raise RuntimeError(f"无法加载集群 [{cluster['name']}] 的 kubeconfig: {exc}") from exc


def _get_batch_client(cluster_id: str | None = None):
    from kubernetes import client

    return client.BatchV1Api(_get_api_client(cluster_id))


def _user_allowed_cluster_ids(user: User) -> list[str] | None:
    if user.is_superuser:
        return None
    return get_user_allowed_k8s_clusters(user.id) or []


def _visible_clusters_for_user(user: User) -> list[dict]:
    clusters = _load_clusters()
    allowed_ids = _user_allowed_cluster_ids(user)
    if allowed_ids is None:
        return clusters
    return [cluster for cluster in clusters if cluster.get("id") in allowed_ids]


def _resolve_cluster_for_user(user: User, cluster_id: str | None = None) -> dict:
    visible_clusters = _visible_clusters_for_user(user)
    if not visible_clusters:
        raise HTTPException(status_code=403, detail="当前用户未获得 Kubernetes 集群权限")

    if cluster_id:
        cluster = next((item for item in visible_clusters if item["id"] == cluster_id), None)
        if not cluster:
            raise HTTPException(status_code=403, detail=f"鏃犳潈璁块棶 K8s 闆嗙兢 {cluster_id}")
        return cluster

    return next((item for item in visible_clusters if item.get("is_default")), visible_clusters[0])


async def _get_ws_user(ws: WebSocket) -> User | None:
    session_id = ws.cookies.get("session_id")
    if not session_id:
        return None
    session = await get_session(session_id)
    if not session:
        return None

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == session.get("user_id")))
        user = result.scalar_one_or_none()
        if not user or user.status != "active":
            return None
        return user


def _phase_class(phase: str) -> str:
    return {
        "Running": "ok",
        "Succeeded": "ok",
        "Ready": "ok",
        "Pending": "warn",
        "Progressing": "warn",
        "Active": "ok",
        "Idle": "ok",
        "Complete": "ok",
        "Suspended": "warn",
        "NotReady": "err",
        "Failed": "err",
        "Unknown": "err",
        "Degraded": "err",
    }.get(phase, "warn")


def _pod_status(pod) -> str:
    phase = pod.status.phase or "Unknown"
    if phase == "Running":
        not_ready = [c for c in (pod.status.conditions or []) if c.type == "Ready" and c.status != "True"]
        if not_ready:
            return "NotReady"
    return phase


def _workload_status(ready: int, desired: int, updated: int | None = None) -> str:
    if desired == 0:
        return "Ready"
    if ready == desired:
        return "Ready"
    if updated is not None and updated < desired:
        return "Progressing"
    return "Degraded"


def _container_images(template) -> list[str]:
    spec = getattr(template, "spec", None)
    return [c.image for c in (getattr(spec, "containers", None) or [])]


def _job_status(item) -> str:
    for cond in item.status.conditions or []:
        if cond.status == "True" and cond.type in ("Complete", "Failed"):
            return cond.type
    if item.status.active:
        return "Running"
    if item.status.succeeded:
        return "Complete"
    return "Pending"


def _normalize_resource_kind(kind: str) -> str:
    value = str(kind or "").strip().lower().replace("-", "").replace("_", "")
    aliases = {
        "pods": "pod",
        "deployments": "deployment",
        "daemonsets": "daemonset",
        "statefulsets": "statefulset",
        "jobs": "job",
        "cronjobs": "cronjob",
        "services": "service",
        "nodes": "node",
    }
    return aliases.get(value, value)


def _labels_to_selector(labels: dict | None) -> str:
    if not labels:
        return ""
    return ",".join(f"{key}={value}" for key, value in labels.items() if value not in (None, ""))


def _resource_selector_labels(item) -> dict:
    selector = getattr(getattr(item, "spec", None), "selector", None)
    match_labels = getattr(selector, "match_labels", None) or {}
    if match_labels:
        return dict(match_labels)
    template_meta = getattr(getattr(getattr(item, "spec", None), "template", None), "metadata", None)
    return dict(getattr(template_meta, "labels", None) or {})


def _pod_brief(pod) -> dict:
    return {
        "name": pod.metadata.name,
        "namespace": pod.metadata.namespace,
        "status": _pod_status(pod),
        "statusClass": _phase_class(_pod_status(pod)),
        "node": pod.spec.node_name or "",
        "age": _safe_age(pod.metadata.creation_timestamp),
        "containers": [
            {
                "name": container.name,
                "image": container.image,
            }
            for container in (pod.spec.containers or [])
        ],
    }


def _sort_pods(items: list) -> list:
    return sorted(items, key=lambda pod: getattr(pod.metadata, "creation_timestamp", None) or 0, reverse=True)


def _trim_k8s_detail(value):
    if isinstance(value, dict):
        return {
            key: _trim_k8s_detail(item)
            for key, item in value.items()
            if key != "managedFields"
        }
    if isinstance(value, list):
        return [_trim_k8s_detail(item) for item in value]
    return value


def _serialize_k8s_resource(cluster_id: str | None, resource) -> dict:
    api_client = _get_api_client(cluster_id)
    return _trim_k8s_detail(api_client.sanitize_for_serialization(resource))


def _read_k8s_resource(cluster_id: str | None, kind: str, namespace: str, name: str):
    normalized_kind = _normalize_resource_kind(kind)
    v1, apps = _get_client(cluster_id)
    batch = _get_batch_client(cluster_id)

    if normalized_kind == "pod":
        return v1.read_namespaced_pod(name=name, namespace=namespace)
    if normalized_kind == "deployment":
        return apps.read_namespaced_deployment(name=name, namespace=namespace)
    if normalized_kind == "daemonset":
        return apps.read_namespaced_daemon_set(name=name, namespace=namespace)
    if normalized_kind == "statefulset":
        return apps.read_namespaced_stateful_set(name=name, namespace=namespace)
    if normalized_kind == "job":
        return batch.read_namespaced_job(name=name, namespace=namespace)
    if normalized_kind == "cronjob":
        return batch.read_namespaced_cron_job(name=name, namespace=namespace)
    if normalized_kind == "service":
        return v1.read_namespaced_service(name=name, namespace=namespace)
    if normalized_kind == "node":
        return v1.read_node(name=name)
    raise HTTPException(status_code=400, detail=f"不支持的资源类型: {kind}")


def _list_resource_pods(cluster_id: str | None, kind: str, namespace: str, name: str) -> list[dict]:
    normalized_kind = _normalize_resource_kind(kind)
    v1, _ = _get_client(cluster_id)

    if normalized_kind == "pod":
        pod = v1.read_namespaced_pod(name=name, namespace=namespace)
        return [_pod_brief(pod)]

    if normalized_kind in {"deployment", "daemonset", "statefulset", "job"}:
        resource = _read_k8s_resource(cluster_id, normalized_kind, namespace, name)
        selector = _labels_to_selector(_resource_selector_labels(resource))
        if selector:
            pods = v1.list_namespaced_pod(namespace=namespace, label_selector=selector).items
        else:
            pods = []
        if normalized_kind == "job" and not pods:
            pods = [
                pod
                for pod in v1.list_namespaced_pod(namespace=namespace).items
                if any(ref.kind == "Job" and ref.name == name for ref in (pod.metadata.owner_references or []))
                or (pod.metadata.labels or {}).get("job-name") == name
            ]
        return [_pod_brief(pod) for pod in _sort_pods(pods)]

    if normalized_kind == "cronjob":
        batch = _get_batch_client(cluster_id)
        jobs = batch.list_namespaced_job(namespace=namespace).items
        job_names = {
            job.metadata.name
            for job in jobs
            if any(ref.kind == "CronJob" and ref.name == name for ref in (job.metadata.owner_references or []))
        }
        if not job_names:
            cronjob = batch.read_namespaced_cron_job(name=name, namespace=namespace)
            job_names = {ref.name for ref in (cronjob.status.active or []) if ref.name}
        if not job_names:
            return []
        pods = [
            pod
            for pod in v1.list_namespaced_pod(namespace=namespace).items
            if any(ref.kind == "Job" and ref.name in job_names for ref in (pod.metadata.owner_references or []))
            or (pod.metadata.labels or {}).get("job-name") in job_names
        ]
        return [_pod_brief(pod) for pod in _sort_pods(pods)]

    return []


# ── 集群 CRUD ────────────────────────────────────────────────────────────────

@router.get("/clusters")
async def list_clusters(user: User = Depends(current_user)):
    return _visible_clusters_for_user(user)


@router.post("/clusters")
async def add_cluster(body: K8sClusterPayload, _: User = Depends(require_admin)):
    name = body.name.strip()
    kubeconfig = body.kubeconfig.strip()
    if not name:
        raise HTTPException(status_code=400, detail="集群名称不能为空")
    if not kubeconfig:
        raise HTTPException(status_code=400, detail="kubeconfig 路径不能为空")

    clusters = _load_clusters()
    cluster = {
        "id": str(uuid.uuid4())[:8],
        "name": name,
        "kubeconfig": kubeconfig,
        "context": body.context.strip(),
        "description": body.description.strip(),
        "is_default": not clusters,
    }
    clusters.append(cluster)
    clusters, _ = _apply_default_cluster(clusters)
    _save_clusters(clusters)
    return cluster


@router.put("/clusters/{cluster_id}")
async def update_cluster(cluster_id: str, body: K8sClusterPayload, _: User = Depends(require_admin)):
    clusters = _load_clusters()
    idx = next((i for i, item in enumerate(clusters) if item["id"] == cluster_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="集群不存在")

    name = body.name.strip()
    kubeconfig = body.kubeconfig.strip()
    if not name:
        raise HTTPException(status_code=400, detail="集群名称不能为空")
    if not kubeconfig:
        raise HTTPException(status_code=400, detail="kubeconfig 路径不能为空")

    clusters[idx].update(
        {
            "name": name,
            "kubeconfig": kubeconfig,
            "context": body.context.strip(),
            "description": body.description.strip(),
        }
    )
    clusters, _ = _apply_default_cluster(clusters)
    _save_clusters(clusters)
    return clusters[idx]


@router.delete("/clusters/{cluster_id}")
async def delete_cluster(cluster_id: str, _: User = Depends(require_admin)):
    clusters = _load_clusters()
    if not any(item["id"] == cluster_id for item in clusters):
        raise HTTPException(status_code=404, detail="集群不存在")
    clusters = [item for item in clusters if item["id"] != cluster_id]
    clusters, _ = _apply_default_cluster(clusters)
    _save_clusters(clusters)
    return {"ok": True}


@router.post("/clusters/{cluster_id}/default")
async def set_default_cluster(cluster_id: str, _: User = Depends(require_admin)):
    clusters = _load_clusters()
    if not any(item["id"] == cluster_id for item in clusters):
        raise HTTPException(status_code=404, detail="集群不存在")
    clusters, _ = _apply_default_cluster(clusters, cluster_id)
    _save_clusters(clusters)
    return next(item for item in clusters if item["id"] == cluster_id)


@router.get("/clusters/{cluster_id}/test")
async def test_cluster(cluster_id: str, _: User = Depends(require_admin)):
    try:
        cluster = _get_cluster(cluster_id)
        v1, _ = _get_client(cluster_id)
        nodes = v1.list_node().items
        node_names = [item.metadata.name for item in nodes]
        return {
            "ok": True,
            "cluster_id": cluster["id"],
            "cluster_name": cluster["name"],
            "kubeconfig": cluster["kubeconfig"],
            "resolved_kubeconfig": _resolve_runtime_kubeconfig_path(cluster.get("kubeconfig", "")),
            "context": cluster.get("context", ""),
            "node_count": len(node_names),
            "nodes": node_names[:10],
        }
    except Exception as exc:
        logger.warning("[k8s] test_cluster failed: %s", exc)
        cluster = next((item for item in _load_clusters() if item["id"] == cluster_id), None)
        return {
            "ok": False,
            "cluster_id": cluster_id,
            "cluster_name": cluster.get("name", "") if cluster else "",
            "kubeconfig": cluster.get("kubeconfig", "") if cluster else "",
            "resolved_kubeconfig": _resolve_runtime_kubeconfig_path(cluster.get("kubeconfig", "")) if cluster else "",
            "context": cluster.get("context", "") if cluster else "",
            "error": str(exc),
        }


@router.get("/resource-detail")
async def resource_detail(
    kind: str = Query(..., description="资源类型"),
    name: str = Query(..., description="资源名称"),
    namespace: str = Query("", description="命名空间"),
    cluster_id: str = Query("", description="集群 ID"),
    user: User = Depends(current_user),
):
    try:
        cluster = _resolve_cluster_for_user(user, cluster_id or None)
        resource = _read_k8s_resource(cluster["id"], kind, namespace, name)
        return {
            "kind": _normalize_resource_kind(kind),
            "name": name,
            "namespace": namespace,
            "data": _serialize_k8s_resource(cluster["id"], resource),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[k8s] resource_detail failed kind=%s namespace=%s name=%s error=%s", kind, namespace, name, exc)
        raise HTTPException(502, f"k8s 连接失败: {exc}")


@router.get("/resource-pods")
async def resource_pods(
    kind: str = Query(..., description="资源类型"),
    name: str = Query(..., description="资源名称"),
    namespace: str = Query("", description="命名空间"),
    cluster_id: str = Query("", description="集群 ID"),
    user: User = Depends(current_user),
):
    try:
        cluster = _resolve_cluster_for_user(user, cluster_id or None)
        pods = _list_resource_pods(cluster["id"], kind, namespace, name)
        return {
            "kind": _normalize_resource_kind(kind),
            "name": name,
            "namespace": namespace,
            "pods": pods,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[k8s] resource_pods failed kind=%s namespace=%s name=%s error=%s", kind, namespace, name, exc)
        raise HTTPException(502, f"k8s 连接失败: {exc}")


@router.get("/pod-logs")
async def pod_logs(
    namespace: str = Query(..., description="命名空间"),
    pod_name: str = Query(..., description="Pod 名称"),
    cluster_id: str = Query("", description="集群 ID"),
    container: str = Query("", description="容器名称"),
    tail_lines: int = Query(200, description="日志行数"),
    user: User = Depends(current_user),
):
    try:
        cluster = _resolve_cluster_for_user(user, cluster_id or None)
        v1, _ = _get_client(cluster["id"])
        value = max(20, min(int(tail_lines or 200), 2000))
        logs = v1.read_namespaced_pod_log(
            name=pod_name,
            namespace=namespace,
            container=(container or None),
            tail_lines=value,
            timestamps=True,
        )
        return {
            "namespace": namespace,
            "podName": pod_name,
            "container": container,
            "tailLines": value,
            "logs": logs or "",
        }
    except Exception as exc:
        logger.warning("[k8s] pod_logs failed namespace=%s pod=%s container=%s error=%s", namespace, pod_name, container, exc)
        raise HTTPException(502, f"k8s 日志读取失败: {exc}")


# ── Namespaces ────────────────────────────────────────────────────────────────

@router.get("/namespaces")
async def list_namespaces(
    cluster_id: str = Query("", description="集群 ID"),
    user: User = Depends(current_user),
):
    try:
        cluster = _resolve_cluster_for_user(user, cluster_id or None)
        v1, _ = _get_client(cluster["id"])
        ns_list = v1.list_namespace()
        return [
            {
                "name": ns.metadata.name,
                "status": ns.status.phase or "Active",
                "age": _safe_age(ns.metadata.creation_timestamp),
                "labels": ns.metadata.labels or {},
            }
            for ns in ns_list.items
        ]
    except Exception as exc:
        logger.warning("[k8s] list_namespaces failed: %s", exc)
        raise HTTPException(502, f"k8s 连接失败: {exc}")


# ── Pods ──────────────────────────────────────────────────────────────────────

@router.get("/pods")
async def list_pods(
    namespace: str = Query("", description="命名空间，空=全部"),
    cluster_id: str = Query("", description="集群 ID"),
    user: User = Depends(current_user),
):
    try:
        cluster = _resolve_cluster_for_user(user, cluster_id or None)
        v1, _ = _get_client(cluster["id"])
        pods = v1.list_pod_for_all_namespaces() if not namespace else v1.list_namespaced_pod(namespace)
        result = []
        for pod in pods.items:
            status = _pod_status(pod)
            containers = [
                {"name": c.name, "image": c.image, "ready": False, "restarts": 0}
                for c in (pod.spec.containers or [])
            ]
            if pod.status.container_statuses:
                for cs in pod.status.container_statuses:
                    for c in containers:
                        if c["name"] == cs.name:
                            c["ready"] = cs.ready or False
                            c["restarts"] = cs.restart_count or 0
            result.append(
                {
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "status": status,
                    "statusClass": _phase_class(status),
                    "node": pod.spec.node_name or "",
                    "ip": pod.status.pod_ip or "",
                    "containers": containers,
                    "restarts": sum(c["restarts"] for c in containers),
                    "age": _safe_age(pod.metadata.creation_timestamp),
                }
            )
        return result
    except Exception as exc:
        logger.warning("[k8s] list_pods failed: %s", exc)
        raise HTTPException(502, f"k8s 连接失败: {exc}")


# ── Deployments ───────────────────────────────────────────────────────────────

@router.get("/deployments")
async def list_deployments(
    namespace: str = Query("", description="命名空间，空=全部"),
    cluster_id: str = Query("", description="集群 ID"),
    user: User = Depends(current_user),
):
    try:
        cluster = _resolve_cluster_for_user(user, cluster_id or None)
        _, apps = _get_client(cluster["id"])
        deps = apps.list_deployment_for_all_namespaces() if not namespace else apps.list_namespaced_deployment(namespace)
        result = []
        for item in deps.items:
            desired = item.spec.replicas or 0
            ready = item.status.ready_replicas or 0
            updated = item.status.updated_replicas or 0
            avail = item.status.available_replicas or 0
            ok = ready == desired and desired > 0
            status = "Ready" if ok else ("Progressing" if updated < desired else "Degraded")
            result.append(
                {
                    "name": item.metadata.name,
                    "namespace": item.metadata.namespace,
                    "desired": desired,
                    "ready": ready,
                    "updated": updated,
                    "available": avail,
                    "status": status,
                    "statusClass": _phase_class(status),
                    "age": _safe_age(item.metadata.creation_timestamp),
                    "images": [c.image for c in (item.spec.template.spec.containers or [])],
                }
            )
        return result
    except Exception as exc:
        logger.warning("[k8s] list_deployments failed: %s", exc)
        raise HTTPException(502, f"k8s 连接失败: {exc}")


# ── DaemonSets ────────────────────────────────────────────────────────────────

@router.get("/daemonsets")
async def list_daemonsets(
    namespace: str = Query("", description="命名空间，空=全部"),
    cluster_id: str = Query("", description="集群 ID"),
    user: User = Depends(current_user),
):
    try:
        cluster = _resolve_cluster_for_user(user, cluster_id or None)
        _, apps = _get_client(cluster["id"])
        items = apps.list_daemon_set_for_all_namespaces() if not namespace else apps.list_namespaced_daemon_set(namespace)
        result = []
        for item in items.items:
            desired = item.status.desired_number_scheduled or 0
            ready = item.status.number_ready or 0
            updated = item.status.updated_number_scheduled or 0
            available = item.status.number_available or 0
            current = item.status.current_number_scheduled or 0
            status = _workload_status(ready, desired, updated)
            result.append(
                {
                    "name": item.metadata.name,
                    "namespace": item.metadata.namespace,
                    "desired": desired,
                    "current": current,
                    "ready": ready,
                    "updated": updated,
                    "available": available,
                    "status": status,
                    "statusClass": _phase_class(status),
                    "age": _safe_age(item.metadata.creation_timestamp),
                    "images": _container_images(item.spec.template),
                }
            )
        return result
    except Exception as exc:
        logger.warning("[k8s] list_daemonsets failed: %s", exc)
        raise HTTPException(502, f"k8s 连接失败: {exc}")


# ── StatefulSets ──────────────────────────────────────────────────────────────

@router.get("/statefulsets")
async def list_statefulsets(
    namespace: str = Query("", description="命名空间，空=全部"),
    cluster_id: str = Query("", description="集群 ID"),
    user: User = Depends(current_user),
):
    try:
        cluster = _resolve_cluster_for_user(user, cluster_id or None)
        _, apps = _get_client(cluster["id"])
        items = apps.list_stateful_set_for_all_namespaces() if not namespace else apps.list_namespaced_stateful_set(namespace)
        result = []
        for item in items.items:
            desired = item.spec.replicas or 0
            ready = item.status.ready_replicas or 0
            current = item.status.current_replicas or 0
            updated = item.status.updated_replicas or 0
            status = _workload_status(ready, desired, updated)
            result.append(
                {
                    "name": item.metadata.name,
                    "namespace": item.metadata.namespace,
                    "desired": desired,
                    "ready": ready,
                    "current": current,
                    "updated": updated,
                    "status": status,
                    "statusClass": _phase_class(status),
                    "age": _safe_age(item.metadata.creation_timestamp),
                    "images": _container_images(item.spec.template),
                }
            )
        return result
    except Exception as exc:
        logger.warning("[k8s] list_statefulsets failed: %s", exc)
        raise HTTPException(502, f"k8s 连接失败: {exc}")


# ── Jobs ─────────────────────────────────────────────────────────────────────

@router.get("/jobs")
async def list_jobs(
    namespace: str = Query("", description="命名空间，空=全部"),
    cluster_id: str = Query("", description="集群 ID"),
    user: User = Depends(current_user),
):
    try:
        cluster = _resolve_cluster_for_user(user, cluster_id or None)
        batch = _get_batch_client(cluster["id"])
        items = batch.list_job_for_all_namespaces() if not namespace else batch.list_namespaced_job(namespace)
        result = []
        for item in items.items:
            status = _job_status(item)
            result.append(
                {
                    "name": item.metadata.name,
                    "namespace": item.metadata.namespace,
                    "status": status,
                    "statusClass": _phase_class(status),
                    "completions": item.spec.completions or 0,
                    "parallelism": item.spec.parallelism or 0,
                    "active": item.status.active or 0,
                    "succeeded": item.status.succeeded or 0,
                    "failed": item.status.failed or 0,
                    "age": _safe_age(item.metadata.creation_timestamp),
                    "images": _container_images(item.spec.template),
                }
            )
        return result
    except Exception as exc:
        logger.warning("[k8s] list_jobs failed: %s", exc)
        raise HTTPException(502, f"k8s 连接失败: {exc}")


# ── CronJobs ─────────────────────────────────────────────────────────────────

@router.get("/cronjobs")
async def list_cronjobs(
    namespace: str = Query("", description="命名空间，空=全部"),
    cluster_id: str = Query("", description="集群 ID"),
    user: User = Depends(current_user),
):
    try:
        cluster = _resolve_cluster_for_user(user, cluster_id or None)
        batch = _get_batch_client(cluster["id"])
        items = batch.list_cron_job_for_all_namespaces() if not namespace else batch.list_namespaced_cron_job(namespace)
        result = []
        for item in items.items:
            active_refs = item.status.active or []
            suspend = bool(item.spec.suspend)
            status = "Suspended" if suspend else ("Active" if active_refs else "Idle")
            last_successful = getattr(item.status, "last_successful_time", None)
            result.append(
                {
                    "name": item.metadata.name,
                    "namespace": item.metadata.namespace,
                    "schedule": item.spec.schedule or "",
                    "suspend": suspend,
                    "active": len(active_refs),
                    "activeJobs": [ref.name for ref in active_refs if ref.name],
                    "lastScheduleTime": _safe_age(item.status.last_schedule_time),
                    "lastSuccessfulTime": _safe_age(last_successful),
                    "status": status,
                    "statusClass": _phase_class(status),
                    "age": _safe_age(item.metadata.creation_timestamp),
                }
            )
        return result
    except Exception as exc:
        logger.warning("[k8s] list_cronjobs failed: %s", exc)
        raise HTTPException(502, f"k8s 连接失败: {exc}")


# ── Services ──────────────────────────────────────────────────────────────────

@router.get("/services")
async def list_services(
    namespace: str = Query("", description="命名空间，空=全部"),
    cluster_id: str = Query("", description="集群 ID"),
    user: User = Depends(current_user),
):
    try:
        cluster = _resolve_cluster_for_user(user, cluster_id or None)
        v1, _ = _get_client(cluster["id"])
        svcs = v1.list_service_for_all_namespaces() if not namespace else v1.list_namespaced_service(namespace)
        result = []
        for item in svcs.items:
            ports = []
            for port in (item.spec.ports or []):
                entry = f"{port.port}"
                if port.node_port:
                    entry += f":{port.node_port}"
                if port.protocol and port.protocol != "TCP":
                    entry += f"/{port.protocol}"
                ports.append(entry)
            result.append(
                {
                    "name": item.metadata.name,
                    "namespace": item.metadata.namespace,
                    "type": item.spec.type or "ClusterIP",
                    "clusterIP": item.spec.cluster_ip or "",
                    "externalIP": ", ".join(item.spec.external_i_ps or [])
                    or (
                        item.status.load_balancer.ingress[0].ip
                        if item.status.load_balancer and item.status.load_balancer.ingress
                        else ""
                    ),
                    "ports": ports,
                    "age": _safe_age(item.metadata.creation_timestamp),
                }
            )
        return result
    except Exception as exc:
        logger.warning("[k8s] list_services failed: %s", exc)
        raise HTTPException(502, f"k8s 连接失败: {exc}")


# ── Nodes ─────────────────────────────────────────────────────────────────────

@router.get("/nodes")
async def list_nodes(
    cluster_id: str = Query("", description="集群 ID"),
    user: User = Depends(current_user),
):
    try:
        cluster = _resolve_cluster_for_user(user, cluster_id or None)
        v1, _ = _get_client(cluster["id"])
        nodes = v1.list_node()
        result = []
        for item in nodes.items:
            ready = "Unknown"
            for cond in (item.status.conditions or []):
                if cond.type == "Ready":
                    ready = "Ready" if cond.status == "True" else "NotReady"
            info = item.status.node_info or {}
            result.append(
                {
                    "name": item.metadata.name,
                    "status": ready,
                    "statusClass": _phase_class(ready),
                    "roles": ", ".join(
                        key.split("/")[-1]
                        for key in (item.metadata.labels or {})
                        if key.startswith("node-role.kubernetes.io/")
                    )
                    or "worker",
                    "version": getattr(info, "kubelet_version", ""),
                    "os": getattr(info, "os_image", ""),
                    "arch": getattr(info, "architecture", ""),
                    "age": _safe_age(item.metadata.creation_timestamp),
                }
            )
        return result
    except Exception as exc:
        logger.warning("[k8s] list_nodes failed: %s", exc)
        raise HTTPException(502, f"k8s 连接失败: {exc}")


# ── Summary ───────────────────────────────────────────────────────────────────

@router.get("/summary")
async def cluster_summary(
    cluster_id: str = Query("", description="集群 ID"),
    user: User = Depends(current_user),
):
    try:
        cluster = _resolve_cluster_for_user(user, cluster_id or None)
        v1, apps = _get_client(cluster["id"])
        batch = _get_batch_client(cluster["id"])
        pods = v1.list_pod_for_all_namespaces()
        deps = apps.list_deployment_for_all_namespaces()
        daemonsets = apps.list_daemon_set_for_all_namespaces()
        statefulsets = apps.list_stateful_set_for_all_namespaces()
        jobs = batch.list_job_for_all_namespaces()
        cronjobs = batch.list_cron_job_for_all_namespaces()
        nodes = v1.list_node()

        total_pods = len(pods.items)
        running_pods = sum(1 for item in pods.items if _pod_status(item) == "Running")
        total_deps = len(deps.items)
        ready_deps = sum(
            1
            for item in deps.items
            if (item.status.ready_replicas or 0) == (item.spec.replicas or 0) and item.spec.replicas
        )
        total_nodes = len(nodes.items)
        ready_nodes = sum(
            1
            for item in nodes.items
            if any(cond.type == "Ready" and cond.status == "True" for cond in (item.status.conditions or []))
        )
        total_daemonsets = len(daemonsets.items)
        ready_daemonsets = sum(
            1
            for item in daemonsets.items
            if (item.status.number_ready or 0) == (item.status.desired_number_scheduled or 0)
        )
        total_statefulsets = len(statefulsets.items)
        ready_statefulsets = sum(
            1
            for item in statefulsets.items
            if (item.status.ready_replicas or 0) == (item.spec.replicas or 0)
        )
        total_jobs = len(jobs.items)
        complete_jobs = sum(1 for item in jobs.items if _job_status(item) == "Complete")
        total_cronjobs = len(cronjobs.items)
        active_cronjobs = sum(1 for item in cronjobs.items if item.status.active)
        suspended_cronjobs = sum(1 for item in cronjobs.items if item.spec.suspend)

        return {
            "cluster": {
                "id": cluster["id"],
                "name": cluster["name"],
                "context": cluster.get("context", ""),
                "kubeconfig": cluster.get("kubeconfig", ""),
            },
            "pods": {"total": total_pods, "running": running_pods},
            "deployments": {"total": total_deps, "ready": ready_deps},
            "daemonSets": {"total": total_daemonsets, "ready": ready_daemonsets},
            "statefulSets": {"total": total_statefulsets, "ready": ready_statefulsets},
            "jobs": {"total": total_jobs, "complete": complete_jobs},
            "cronJobs": {
                "total": total_cronjobs,
                "active": active_cronjobs,
                "suspended": suspended_cronjobs,
            },
            "nodes": {"total": total_nodes, "ready": ready_nodes},
        }
    except Exception as exc:
        logger.warning("[k8s] summary failed: %s", exc)
        raise HTTPException(502, f"k8s 连接失败: {exc}")


# ── Container Exec WebSocket ──────────────────────────────────────────────────

@router.websocket("/exec")
async def ws_k8s_exec(
    ws: WebSocket,
    cluster_id: str = Query(None),
    namespace: str = Query("default"),
    pod: str = Query(...),
    container: str = Query(""),
    shell: str = Query("/bin/sh"),
):
    """WebSocket 容器终端：桥接 kubectl exec 到浏览器 xterm.js。

    输入直接透传；发送 \\x1b[RESIZE:cols,rows] 触发终端 resize。
    所有阻塞的 kubernetes.stream 调用均在 ThreadPoolExecutor 中运行，
    不阻塞 asyncio 事件循环。
    """
    import asyncio
    import json as _json
    import threading
    from concurrent.futures import ThreadPoolExecutor

    user = await _get_ws_user(ws)
    if not user:
        await ws.close(code=4401, reason="未登录")
        return

    try:
        cluster = _resolve_cluster_for_user(user, cluster_id or None)
    except HTTPException as exc:
        await ws.close(code=4403, reason=str(exc.detail))
        return

    await ws.accept()

    # ── 1. 建立 exec 连接（阻塞，放入线程池）──────────────────────
    try:
        from kubernetes import client as k8s_client
        from kubernetes.stream import stream as k8s_stream

        api_client = _get_api_client(cluster["id"])
        v1 = k8s_client.CoreV1Api(api_client)
        exec_kwargs: dict = dict(
            command=[shell],
            stderr=True, stdin=True, stdout=True, tty=True,
            _preload_content=False,
        )
        if container:
            exec_kwargs["container"] = container

        loop = asyncio.get_running_loop()
        exec_resp = await loop.run_in_executor(
            None,
            lambda: k8s_stream(
                v1.connect_get_namespaced_pod_exec,
                pod, namespace, **exec_kwargs,
            ),
        )
    except Exception as exc:
        try:
            await ws.send_text(f"\x1b[31m连接失败: {exc}\x1b[0m\r\n")
            await ws.close()
        except Exception:
            pass
        return

    await ws.send_text(
        f"\x1b[32m已连接到 {pod}/{container or '<default>'}\x1b[0m\r\n"
    )

    # 专用线程池：exec 读写均在此执行，与事件循环隔离
    _exec_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="k8s_exec")
    output_q: asyncio.Queue[str | None] = asyncio.Queue(maxsize=256)
    _stop = asyncio.Event()

    # ── 2. 后台线程：持续读取 stdout/stderr → 放入队列 ────────────
    def _reader() -> None:
        try:
            while exec_resp.is_open() and not _stop.is_set():
                # timeout=0.5：减少空转，最大延迟 500ms 可接受
                exec_resp.update(timeout=0.5)
                for peek_fn, read_fn in (
                    (exec_resp.peek_stdout, exec_resp.read_stdout),
                    (exec_resp.peek_stderr, exec_resp.read_stderr),
                ):
                    if peek_fn():
                        chunk = read_fn()
                        if chunk:
                            loop.call_soon_threadsafe(output_q.put_nowait, chunk)
        except Exception:
            pass
        finally:
            loop.call_soon_threadsafe(output_q.put_nowait, None)

    reader_future = _exec_pool.submit(_reader)

    # ── 3. 协程：从队列取数据发给浏览器 ────────────────────────────
    async def _forward_output() -> None:
        try:
            while True:
                chunk = await output_q.get()
                if chunk is None:
                    break
                await ws.send_text(chunk)
        except Exception:
            pass
        finally:
            _stop.set()

    # ── 4. 协程：接收浏览器输入，阻塞写操作放入线程池 ──────────────
    async def _forward_input() -> None:
        try:
            while True:
                msg = await ws.receive_text()
                if msg.startswith("\x1b[RESIZE:"):
                    parts = msg[9:].split(",")
                    if len(parts) == 2:
                        try:
                            cols, rows = int(parts[0]), int(parts[1])
                            resize_payload = _json.dumps({"Width": cols, "Height": rows})
                            await loop.run_in_executor(
                                _exec_pool,
                                lambda p=resize_payload: exec_resp.write_channel(4, p),
                            )
                        except Exception:
                            pass
                else:
                    await loop.run_in_executor(
                        _exec_pool,
                        lambda m=msg: exec_resp.write_stdin(m),
                    )
        except Exception:
            pass
        finally:
            _stop.set()

    # ── 5. 并发运行，任意一方结束则取消另一方 ───────────────────────
    t_out = asyncio.create_task(_forward_output())
    t_in  = asyncio.create_task(_forward_input())

    def _cancel_peer(done_task: asyncio.Task) -> None:
        peer = t_in if done_task is t_out else t_out
        if not peer.done():
            peer.cancel()

    t_out.add_done_callback(_cancel_peer)
    t_in.add_done_callback(_cancel_peer)

    try:
        await asyncio.gather(t_out, t_in, return_exceptions=True)
    finally:
        _stop.set()
        try:
            exec_resp.close()
        except Exception:
            pass
        reader_future.cancel()
        _exec_pool.shutdown(wait=False)
        try:
            await ws.close()
        except Exception:
            pass
