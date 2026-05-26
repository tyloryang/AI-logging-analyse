"""Kubernetes 集群管理路由 — /api/k8s/*"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import uuid
from pathlib import Path

from cachetools import TTLCache
from fastapi import APIRouter, HTTPException, Query, WebSocket, Depends, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select

from auth.deps import current_user, require_admin
from auth.models import User
from auth.session import get_session
from db import AsyncSessionLocal
from json_snapshot_store import read_json_file, write_json_file
from state import get_user_allowed_k8s_clusters

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/k8s", tags=["kubernetes"])

_DATA_FILE = Path(__file__).parent.parent / "data" / "k8s_clusters.json"
_DEFAULT_KUBECONFIG = os.path.join(os.path.dirname(__file__), "..", "data", "kubeconfig")
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
# In Docker the backend is mounted at /app directly (no project root above it),
# so parents[2] would be "/". Use BACKEND_ROOT as fallback project root.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_KUBECONFIG_PATH_SEPARATOR = os.pathsep
_SUMMARY_CACHE: TTLCache = TTLCache(maxsize=16, ttl=15)
_SUMMARY_LOCKS: dict[str, asyncio.Lock] = {}


def _read_text_auto(path: Path) -> str:
    """读取文件，优先 UTF-8，失败时回退到系统编码（兼容中文 Windows GBK 环境）。"""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        import locale
        fallback = locale.getpreferredencoding(False) or "gbk"
        return path.read_text(encoding=fallback, errors="replace")


class K8sClusterPayload(BaseModel):
    name: str
    kubeconfig: str
    context: str = ""
    description: str = ""


def _settings() -> dict:
    try:
        p = Path(__file__).parent.parent / "data" / "settings.json"
        data = read_json_file(p, default={})
        if isinstance(data, dict):
            return data
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
    write_json_file(_DATA_FILE, clusters, ensure_parent=True)


def _resolve_single_runtime_kubeconfig_path(raw_path: str) -> str:
    path_value = str(raw_path or "").strip()
    if not path_value:
        return ""

    # Use pathlib for expanduser to avoid os.path encoding issues on Windows with Chinese paths.
    # Fall back to os.path.expandvars only when the string actually contains '%' (env var markers).
    try:
        expanded = str(Path(path_value).expanduser())
    except Exception:
        expanded = path_value
    if "%" in expanded or "$" in expanded:
        try:
            expanded = os.path.expandvars(expanded)
        except Exception:
            pass
    if not expanded:
        return ""

    if os.name != "nt" and Path(expanded).is_absolute():
        return str(Path(expanded))

    if expanded.startswith("/"):
        return expanded

    # Handle Windows absolute paths (e.g. C:\Users\...) even on Linux containers.
    import re as _re
    if _re.match(r"^[A-Za-z]:[/\\]", expanded):
        return expanded

    if Path(expanded).is_absolute():
        return str(Path(expanded))

    candidates: list[Path] = []
    seen: set[str] = set()

    # In Docker the backend/ directory is mounted as the app root (e.g. /app).
    # Allow "backend/data/..." to resolve as "data/..." relative to _BACKEND_ROOT.
    docker_alias: list[tuple[Path, str]] = []
    for prefix in ("backend/", "backend\\"):
        if expanded.startswith(prefix):
            docker_alias.append((_BACKEND_ROOT, expanded[len(prefix):]))

    for base, rel in [(Path.cwd(), expanded), (_PROJECT_ROOT, expanded), (_BACKEND_ROOT, expanded)] + docker_alias:
        candidate = (base / rel).resolve(strict=False)
        candidate_key = str(candidate).lower()
        if candidate_key in seen:
            continue
        seen.add(candidate_key)
        candidates.append(candidate)
        if candidate.exists():
            return str(candidate)

    return str((_PROJECT_ROOT / expanded).resolve(strict=False))


def _split_kubeconfig_value(raw_path: str) -> list[str]:
    path_value = str(raw_path or "").strip()
    if not path_value:
        return []
    return [part.strip() for part in path_value.split(_KUBECONFIG_PATH_SEPARATOR) if part.strip()]


def _resolve_runtime_kubeconfig_paths(raw_path: str) -> list[str]:
    return [_resolve_single_runtime_kubeconfig_path(part) for part in _split_kubeconfig_value(raw_path)]


def _resolve_runtime_kubeconfig_path(raw_path: str) -> str:
    return _KUBECONFIG_PATH_SEPARATOR.join(_resolve_runtime_kubeconfig_paths(raw_path))


def _resolve_kubeconfig_ref_path(raw_path: str, kubeconfig_path: str) -> str:
    path_value = str(raw_path or "").strip()
    if not path_value:
        return ""

    expanded = os.path.expandvars(os.path.expanduser(path_value))
    if not expanded:
        return ""

    expanded_path = Path(expanded)
    if expanded.startswith("/") or expanded_path.is_absolute():
        return str(expanded_path.resolve(strict=False))

    base_dir = Path(kubeconfig_path).resolve(strict=False).parent
    return str((base_dir / expanded_path).resolve(strict=False))


def _find_named_kubeconfig_entry(items: list[dict] | None, name: str) -> dict:
    if not name:
        return {}
    for item in items or []:
        if isinstance(item, dict) and str(item.get("name") or "") == name:
            return item
    return {}


def _build_kubectl_command(cluster_id: str | None = None) -> str:
    cluster = _get_cluster(cluster_id)
    kubeconfig_paths = _resolve_runtime_kubeconfig_paths(cluster.get("kubeconfig") or "")
    if not kubeconfig_paths:
        return "kubectl"

    parts = ["kubectl"]
    kubeconfig_path = kubeconfig_paths[0]
    kubeconfig_value = _KUBECONFIG_PATH_SEPARATOR.join(kubeconfig_paths)
    if len(kubeconfig_paths) == 1:
        parts.extend(["--kubeconfig", kubeconfig_path])

    try:
        import yaml

        content = yaml.safe_load(_read_text_auto(Path(kubeconfig_path))) or {}
        selected_context_name = str(cluster.get("context") or "").strip() or str(content.get("current-context") or "").strip()
        if selected_context_name:
            parts.extend(["--context", selected_context_name])

        context_entry = _find_named_kubeconfig_entry(content.get("contexts"), selected_context_name)
        context_data = context_entry.get("context") if isinstance(context_entry, dict) else {}
        cluster_name = str((context_data or {}).get("cluster") or "")
        user_name = str((context_data or {}).get("user") or "")

        cluster_entry = _find_named_kubeconfig_entry(content.get("clusters"), cluster_name)
        cluster_data = cluster_entry.get("cluster") if isinstance(cluster_entry, dict) else {}
        user_entry = _find_named_kubeconfig_entry(content.get("users"), user_name)
        user_data = user_entry.get("user") if isinstance(user_entry, dict) else {}

        ca_path = _resolve_kubeconfig_ref_path((cluster_data or {}).get("certificate-authority") or "", kubeconfig_path)
        if ca_path:
            parts.extend(["--certificate-authority", ca_path])
        if (cluster_data or {}).get("insecure-skip-tls-verify") is True:
            parts.append("--insecure-skip-tls-verify=true")

        client_cert_path = _resolve_kubeconfig_ref_path((user_data or {}).get("client-certificate") or "", kubeconfig_path)
        if client_cert_path:
            parts.extend(["--client-certificate", client_cert_path])
        client_key_path = _resolve_kubeconfig_ref_path((user_data or {}).get("client-key") or "", kubeconfig_path)
        if client_key_path:
            parts.extend(["--client-key", client_key_path])
    except Exception as exc:
        logger.debug("[k8s] build kubectl command failed for %s: %s", kubeconfig_path, exc)

    command = " ".join(shlex.quote(part) for part in parts)
    if len(kubeconfig_paths) > 1:
        return f"KUBECONFIG={shlex.quote(kubeconfig_value)} {command}"
    return command


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
    try:
        data = read_json_file(_DATA_FILE, default=[])
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


def _merge_kubeconfigs(paths: list[str]) -> str:
    """把多个 kubeconfig 文件合并到一个临时文件，返回临时文件路径。"""
    import tempfile
    import yaml

    merged: dict = {
        "apiVersion": "v1", "kind": "Config",
        "clusters": [], "users": [], "contexts": [],
        "current-context": "", "preferences": {},
    }
    for path in paths:
        try:
            data = yaml.safe_load(_read_text_auto(Path(path))) or {}
        except Exception as exc:
            logger.warning("[k8s] 跳过无法读取的 kubeconfig %s: %s", path, exc)
            continue
        for key in ("clusters", "users", "contexts"):
            existing = {item.get("name") for item in merged[key]}
            for item in data.get(key) or []:
                if item.get("name") not in existing:
                    merged[key].append(item)
        if not merged["current-context"] and data.get("current-context"):
            merged["current-context"] = data["current-context"]

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    )
    yaml.dump(merged, tmp, default_flow_style=False, allow_unicode=True)
    tmp.close()
    return tmp.name


def _get_api_client(cluster_id: str | None = None):
    from kubernetes import config as k8s_config

    cluster     = _get_cluster(cluster_id)
    paths       = _resolve_runtime_kubeconfig_paths(cluster.get("kubeconfig") or "")
    context     = str(cluster.get("context") or "").strip() or None

    if not paths:
        raise RuntimeError(f"集群 [{cluster['name']}] 未配置 kubeconfig 路径")

    try:
        if len(paths) == 1:
            return k8s_config.new_client_from_config(config_file=paths[0], context=context)

        # 多文件合并
        merged_path = _merge_kubeconfigs(paths)
        try:
            return k8s_config.new_client_from_config(config_file=merged_path, context=context)
        finally:
            try:
                Path(merged_path).unlink(missing_ok=True)
            except Exception:
                pass
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


def _fetch_core_summary_resources(cluster_id: str):
    v1, _ = _get_client(cluster_id)
    return v1.list_pod_for_all_namespaces(), v1.list_node()


def _fetch_apps_summary_resources(cluster_id: str):
    _, apps = _get_client(cluster_id)
    return (
        apps.list_deployment_for_all_namespaces(),
        apps.list_daemon_set_for_all_namespaces(),
        apps.list_stateful_set_for_all_namespaces(),
    )


def _fetch_batch_summary_resources(cluster_id: str):
    batch = _get_batch_client(cluster_id)
    return batch.list_job_for_all_namespaces(), batch.list_cron_job_for_all_namespaces()


def _build_cluster_summary_payload(
    cluster: dict,
    pods,
    deps,
    daemonsets,
    statefulsets,
    jobs,
    cronjobs,
    nodes,
) -> dict:
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

_CA_DIR             = Path(__file__).resolve().parents[1] / "data" / "ca"
_KUBECONFIG_GEN_DIR = Path(__file__).resolve().parents[1] / "data" / "kubeconfigs"


# ── 证书文件管理 ──────────────────────────────────────────────────────────────

@router.get("/certs")
async def list_certs(_: User = Depends(current_user)):
    """列出 data/ca/ 目录下所有证书/密钥文件。"""
    _CA_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    for f in sorted(_CA_DIR.iterdir()):
        if f.is_file():
            files.append({
                "name":     f.name,
                "relative": f"backend/data/ca/{f.name}",
                "abs":      str(f),
                "size":     f.stat().st_size,
            })
    return {"data": files}


@router.post("/certs/upload")
async def upload_cert(
    file: UploadFile = File(...),
    cert_type: str = "ca",
    _: User = Depends(require_admin),
):
    """上传证书/密钥文件到 data/ca/ 目录。cert_type: ca | client-cert | client-key"""
    _CA_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename).name.replace(" ", "_")
    dest = _CA_DIR / safe_name
    content = await file.read()
    dest.write_bytes(content)
    return {
        "name":     safe_name,
        "relative": f"backend/data/ca/{safe_name}",
        "abs":      str(dest),
    }


class CertKubeconfigPayload(BaseModel):
    name:                    str
    server:                  str
    ca_cert:                 str = ""   # 相对路径，如 backend/data/ca/ca.pem；insecure 模式可留空
    client_cert:             str = ""  # 证书认证
    client_key:              str = ""  # 证书认证
    token:                   str = ""  # token 认证（与 cert 二选一）
    context:                 str = "default"
    description:             str = ""
    insecure_skip_tls_verify: bool = False


@router.post("/generate-kubeconfig")
async def generate_kubeconfig(
    body: CertKubeconfigPayload,
    _: User = Depends(require_admin),
):
    """从证书/token 参数生成 kubeconfig 文件，保存到 data/kubeconfig/ 目录。"""
    import re
    try:
        import yaml as _yaml
    except ImportError:
        raise HTTPException(status_code=500, detail="缺少依赖：pip install pyyaml")

    logger.info("[k8s] generate-kubeconfig name=%s server=%s ca=%s token=%s cert=%s",
                body.name, body.server, body.ca_cert, bool(body.token), body.client_cert)

    try:
        _KUBECONFIG_GEN_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"无法创建输出目录: {e}")

    def _resolve_cert(raw: str, label: str) -> str:
        """解析证书路径，支持绝对路径和相对路径，路径不存在时给出明确提示。"""
        if not raw or not raw.strip():
            raise HTTPException(status_code=400, detail=f"{label} 路径不能为空")
        p = Path(raw.strip())
        # 绝对路径直接使用
        if p.is_absolute():
            if not p.exists():
                raise HTTPException(status_code=400, detail=f"{label} 文件不存在: {raw}")
            return str(p)
        # 相对路径走通用解析
        resolved = _resolve_single_runtime_kubeconfig_path(raw.strip())
        if not resolved or not Path(resolved).exists():
            raise HTTPException(status_code=400,
                detail=f"{label} 文件不存在: {raw}（解析后: {resolved or '空'}）")
        return resolved

    cluster_block: dict = {"server": body.server.strip()}
    if body.insecure_skip_tls_verify:
        cluster_block["insecure-skip-tls-verify"] = True
    else:
        ca_path = _resolve_cert(body.ca_cert, "CA 证书")
        cluster_block["certificate-authority"] = ca_path

    if body.token and body.token.strip():
        user_block = {"token": body.token.strip()}
    else:
        cert_path = _resolve_cert(body.client_cert, "客户端证书")
        key_path  = _resolve_cert(body.client_key,  "客户端私钥")
        user_block = {"client-certificate": cert_path, "client-key": key_path}

    kubeconfig = {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters":  [{"name": body.name, "cluster": cluster_block}],
        "users":     [{"name": body.name, "user": user_block}],
        "contexts":  [{"name": body.context, "context": {
            "cluster": body.name, "user": body.name,
        }}],
        "current-context": body.context,
    }

    safe_name   = re.sub(r"[^\w\-]", "_", body.name.strip()) or "cluster"
    output_path = _KUBECONFIG_GEN_DIR / f"{safe_name}.yaml"
    try:
        output_path.write_text(
            _yaml.dump(kubeconfig, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )
    except Exception as e:
        logger.error("[k8s] generate-kubeconfig write failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"写入 kubeconfig 失败: {e}")

    logger.info("[k8s] generated kubeconfig → %s", output_path)
    relative = f"backend/data/kubeconfigs/{safe_name}.yaml"
    return {"path": str(output_path), "relative": relative}


# ── 集群列表 ──────────────────────────────────────────────────────────────────

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


def _parse_cert_detail(path_or_data: str, is_data: bool = False) -> dict:
    """解析 PEM 证书，返回 subject/issuer/有效期（失败返回空 dict）。"""
    import subprocess, base64, tempfile
    try:
        if is_data:
            raw = base64.b64decode(path_or_data)
            with tempfile.NamedTemporaryFile(suffix=".crt", delete=False) as tmp:
                tmp.write(raw); tmp_path = tmp.name
            pem_path = tmp_path
        else:
            pem_path = path_or_data
            if not Path(pem_path).exists():
                return {"error": f"文件不存在: {pem_path}"}

        r = subprocess.run(
            ["openssl", "x509", "-noout", "-subject", "-issuer",
             "-startdate", "-enddate", "-in", pem_path],
            capture_output=True, text=True, timeout=5,
        )
        if is_data:
            Path(pem_path).unlink(missing_ok=True)
        if r.returncode != 0:
            return {"error": r.stderr.strip()}
        info = {}
        for line in r.stdout.splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                info[k.strip().lower().replace(" ", "_")] = v.strip()
        return info
    except Exception as e:
        return {"error": str(e)}


def _detect_kubeconfig_auth(kubeconfig_path: str) -> dict:
    """
    解析 kubeconfig 文件，自动识别认证类型，返回结构化 auth 信息。
    支持：certificate | token | exec | basic | unknown
    """
    import yaml

    paths = _resolve_runtime_kubeconfig_paths(kubeconfig_path)
    if not paths:
        return {"error": "kubeconfig 路径为空"}

    results = []
    for path in paths:
        if not Path(path).exists():
            results.append({"path": path, "error": "文件不存在"})
            continue
        try:
            data = yaml.safe_load(_read_text_auto(Path(path))) or {}
        except Exception as e:
            results.append({"path": path, "error": f"解析失败: {e}"})
            continue

        current_ctx_name = str(data.get("current-context") or "")
        contexts  = {c["name"]: c.get("context", {}) for c in (data.get("contexts") or []) if isinstance(c, dict)}
        clusters  = {c["name"]: c.get("cluster", {}) for c in (data.get("clusters") or []) if isinstance(c, dict)}
        users_map = {u["name"]: u.get("user", {})    for u in (data.get("users")    or []) if isinstance(u, dict)}

        ctx_data     = contexts.get(current_ctx_name, {})
        cluster_name = ctx_data.get("cluster", "")
        user_name    = ctx_data.get("user", "")
        cluster_data = clusters.get(cluster_name, {})
        user_data    = users_map.get(user_name, {})

        def _resolve_ref(raw: str) -> str:
            """证书路径：先尝试 kubeconfig 同目录，再走通用解析。"""
            if not raw:
                return ""
            resolved = _resolve_kubeconfig_ref_path(raw, path)
            if resolved and Path(resolved).exists():
                return resolved
            # 兜底：通用路径解析
            return _resolve_single_runtime_kubeconfig_path(raw)

        # ── 识别认证类型 ────────────────────────────────────────
        if user_data.get("exec"):
            exec_cfg = user_data["exec"]
            auth = {
                "type":        "exec",
                "command":     exec_cfg.get("command"),
                "args":        exec_cfg.get("args", []),
                "api_version": exec_cfg.get("apiVersion"),
                "env":         exec_cfg.get("env"),
            }
        elif user_data.get("token") or user_data.get("tokenFile"):
            token_val = user_data.get("token", "")
            auth = {
                "type":          "token",
                "token_preview": (token_val[:32] + "...") if len(token_val) > 32 else token_val,
                "token_file":    user_data.get("tokenFile"),
            }
        elif user_data.get("client-certificate") or user_data.get("client-certificate-data"):
            raw_cert = user_data.get("client-certificate", "")
            cert_data = user_data.get("client-certificate-data", "")
            raw_key  = user_data.get("client-key", "")
            cert_path = _resolve_ref(raw_cert)
            key_path  = _resolve_ref(raw_key)
            cert_detail = (_parse_cert_detail(cert_path) if cert_path
                           else _parse_cert_detail(cert_data, is_data=True) if cert_data
                           else {})
            auth = {
                "type":               "certificate",
                "client_certificate": cert_path or raw_cert or "(embedded)",
                "client_key":         key_path  or raw_key  or "(embedded)",
                "cert_embedded":      bool(cert_data),
                "cert_detail":        cert_detail,
            }
        elif user_data.get("username"):
            auth = {
                "type":     "basic",
                "username": user_data.get("username"),
            }
        else:
            auth = {"type": "unknown", "raw_user": user_data}

        # ── CA 信息 ─────────────────────────────────────────────
        raw_ca  = cluster_data.get("certificate-authority", "")
        ca_data = cluster_data.get("certificate-authority-data", "")
        ca_path = _resolve_ref(raw_ca)
        ca_detail = (_parse_cert_detail(ca_path) if ca_path
                     else _parse_cert_detail(ca_data, is_data=True) if ca_data
                     else {})

        results.append({
            "path":            path,
            "current_context": current_ctx_name,
            "server":          cluster_data.get("server", ""),
            "cluster_name":    cluster_name,
            "user_name":       user_name,
            "insecure":        bool(cluster_data.get("insecure-skip-tls-verify")),
            "ca":              ca_path or raw_ca or ("(embedded)" if ca_data else "(none)"),
            "ca_detail":       ca_detail,
            "auth":            auth,
            "all_contexts":    list(contexts.keys()),
        })

    return {"files": results, "total": len(results)}


class InspectKubeconfigPayload(BaseModel):
    path: str


@router.post("/inspect-kubeconfig")
async def inspect_kubeconfig(
    body: InspectKubeconfigPayload,
    _: User = Depends(current_user),
):
    """解析指定 kubeconfig 文件，自动识别认证类型和证书信息。"""
    return _detect_kubeconfig_auth(body.path)


@router.get("/clusters/{cluster_id}/test")
async def test_cluster(cluster_id: str, _: User = Depends(require_admin)):
    try:
        cluster = _get_cluster(cluster_id)
        v1, _ = _get_client(cluster_id)
        nodes = v1.list_node().items
        node_names = [item.metadata.name for item in nodes]
        auth_info = _detect_kubeconfig_auth(cluster.get("kubeconfig", ""))
        return {
            "ok": True,
            "cluster_id": cluster["id"],
            "cluster_name": cluster["name"],
            "kubeconfig": cluster["kubeconfig"],
            "resolved_kubeconfig": _resolve_runtime_kubeconfig_path(cluster.get("kubeconfig", "")),
            "context": cluster.get("context", ""),
            "kubectl_command": _build_kubectl_command(cluster_id),
            "node_count": len(node_names),
            "nodes": node_names[:10],
            "auth_info": auth_info,
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
            "kubectl_command": _build_kubectl_command(cluster_id) if cluster else "kubectl",
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
        cache_key = cluster["id"]
        cached = _SUMMARY_CACHE.get(cache_key)
        if cached is not None:
            return cached

        lock = _SUMMARY_LOCKS.setdefault(cache_key, asyncio.Lock())
        async with lock:
            cached = _SUMMARY_CACHE.get(cache_key)
            if cached is not None:
                return cached

            core_task = asyncio.to_thread(_fetch_core_summary_resources, cluster["id"])
            apps_task = asyncio.to_thread(_fetch_apps_summary_resources, cluster["id"])
            batch_task = asyncio.to_thread(_fetch_batch_summary_resources, cluster["id"])

            (pods, nodes), \
            (deps, daemonsets, statefulsets), \
            (jobs, cronjobs) = await asyncio.gather(core_task, apps_task, batch_task)

            payload = _build_cluster_summary_payload(
                cluster,
                pods,
                deps,
                daemonsets,
                statefulsets,
                jobs,
                cronjobs,
                nodes,
            )
            _SUMMARY_CACHE[cache_key] = payload
            return payload
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
