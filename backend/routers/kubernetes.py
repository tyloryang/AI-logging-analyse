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
    """返回 ISO 8601 完整时间戳（带时区），便于前端按本地时区格式化到秒。
    空值或解析失败返回空字符串。"""
    if not value:
        return ""
    try:
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)
    except Exception:
        return str(value)[:19]


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


def _build_seclevel0_ssl_context(cfg):
    """构造 SECLEVEL=0 + CERT_NONE 的 SSLContext，兼容 K8s 1.18 弱签名证书。
    cfg 为 kubernetes.client.Configuration 实例，提供 cert_file/key_file 路径。

    被 _get_api_client (urllib3 PoolManager) 与 WebSocket exec 共用，
    确保两条 SSL 路径行为一致。
    """
    import ssl
    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_ctx.set_ciphers("DEFAULT@SECLEVEL=0")
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    if getattr(cfg, "cert_file", None) and getattr(cfg, "key_file", None):
        ssl_ctx.load_cert_chain(cfg.cert_file, cfg.key_file)
    return ssl_ctx


def _patch_k8s_websocket_ssl_once() -> None:
    """全局 monkey-patch kubernetes.stream.ws_client.create_websocket，
    让 exec/portforward 等 WebSocket 调用走 SECLEVEL=0 SSLContext。

    SDK 默认的 create_websocket 用 ssl_opts 字典传 cert_reqs/ca_certs/certfile/keyfile，
    内部用系统默认 SSL context (SECLEVEL=2)，对 1.18 集群的 SHA1/MD5 证书拒绝握手。
    这里在每次建连时构造 SECLEVEL=0 SSLContext, 通过 sslopt={'context': ...}
    传给 websocket-client (它会优先使用 context 替代独立字段重建)。

    幂等: 模块全局 patch 一次。代价: 所有 K8s ws 调用都过弱算法 SSL,
    项目只 exec 用 ws, 影响可控。
    """
    import ssl
    try:
        from kubernetes.stream import ws_client as _ws_mod
    except Exception as exc:
        logger.warning("[k8s] kubernetes.stream.ws_client 不可用, 跳过 WebSocket SSL patch: %s", exc)
        return

    if getattr(_ws_mod, "_aiops_patched_seclevel0", False):
        return

    # 保存原版作为应急回退 (本次不调用, 因为原版逻辑会读 cfg 重建受限 SSL ctx)
    _ws_mod._original_create_websocket = _ws_mod.create_websocket

    def _patched_create_websocket(configuration, url, headers=None):
        """重写 create_websocket: 同 SDK 29.0.0 行为, 但注入 SECLEVEL=0 SSLContext。"""
        from websocket import WebSocket, enableTrace
        enableTrace(False)

        header_list: list[str] = []
        if headers and "authorization" in headers:
            header_list.append("authorization: %s" % headers["authorization"])
        if headers and "sec-websocket-protocol" in headers:
            header_list.append("sec-websocket-protocol: %s" % headers["sec-websocket-protocol"])
        else:
            header_list.append("sec-websocket-protocol: v4.channel.k8s.io")

        # 关键: 构造与 urllib3 路径完全一致的 SECLEVEL=0 SSLContext
        ssl_ctx = _build_seclevel0_ssl_context(configuration)
        ssl_opts = {
            "context": ssl_ctx,
            "cert_reqs": ssl.CERT_NONE,
        }
        # 客户端证书也通过 ssl_ctx.load_cert_chain 注入了, 不再传 certfile/keyfile

        ws = WebSocket(sslopt=ssl_opts, skip_utf8_validation=True)
        connect_opt: dict = {"header": header_list}

        # 复刻 SDK 的代理处理
        proxy = getattr(configuration, "proxy", None)
        if proxy:
            from urllib.parse import urlparse
            proxy_url = urlparse(proxy)
            connect_opt["http_proxy_host"] = proxy_url.hostname
            connect_opt["http_proxy_port"] = proxy_url.port
            proxy_headers = getattr(configuration, "proxy_headers", None)
            if proxy_headers:
                connect_opt["http_proxy_auth"] = (
                    proxy_headers.get("proxy-username"),
                    proxy_headers.get("proxy-password"),
                )

        ws.connect(url, **connect_opt)
        return ws

    _ws_mod.create_websocket = _patched_create_websocket
    _ws_mod._aiops_patched_seclevel0 = True
    logger.info("[k8s] WebSocket SSL patched: SECLEVEL=0 + CERT_NONE 已注入")


def _get_api_client(cluster_id: str | None = None):
    from kubernetes import config as k8s_config, client as k8s_client
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # 保证 exec WebSocket 也走 SECLEVEL=0 (模块级幂等 patch)
    _patch_k8s_websocket_ssl_once()

    cluster = _get_cluster(cluster_id)
    paths   = _resolve_runtime_kubeconfig_paths(cluster.get("kubeconfig") or "")
    context = str(cluster.get("context") or "").strip() or None
    if not paths:
        raise RuntimeError(f"集群 [{cluster['name']}] 未配置 kubeconfig 路径")

    config_file = _merge_kubeconfigs(paths) if len(paths) > 1 else paths[0]

    cfg = k8s_client.Configuration()
    k8s_config.load_kube_config(
        config_file=config_file, context=context, client_configuration=cfg,
    )
    cfg.verify_ssl = False
    cfg.ssl_ca_cert = None

    api_client = k8s_client.ApiClient(configuration=cfg)

    # 关键: 重建底层 PoolManager，使用 SECLEVEL=0 的 SSL context (与 ws 路径共用同一构造)
    ssl_ctx = _build_seclevel0_ssl_context(cfg)

    api_client.rest_client.pool_manager = urllib3.PoolManager(
        num_pools=4,
        maxsize=4,
        ssl_context=ssl_ctx,
        cert_reqs="CERT_NONE",
    )

    return api_client


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
            raise HTTPException(status_code=403, detail=f"无权访问 K8s 集群 {cluster_id}")
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
        "configmaps": "configmap",
        "cm": "configmap",   # kubectl 缩写
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
    if normalized_kind == "configmap":
        return v1.read_namespaced_config_map(name=name, namespace=namespace)
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


class K8sKubeconfigTextPayload(BaseModel):
    name: str
    content: str


@router.post("/kubeconfigs/upload-text")
async def upload_kubeconfig_text(
    body: K8sKubeconfigTextPayload, _: User = Depends(require_admin)
):
    """
    接收粘贴的 kubeconfig YAML 文本，校验结构后落盘。
    自动识别支持 *-data (base64 内嵌) 与 *-file (外部文件) 两种证书引用形式。
    返回相对路径，前端可直接填入 cluster.kubeconfig 字段后走 autoDetect。
    """
    import re
    import yaml as _yaml

    name = body.name.strip()
    content = (body.content or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="集群名称不能为空")
    if not content:
        raise HTTPException(status_code=400, detail="kubeconfig 文本不能为空")

    try:
        parsed = _yaml.safe_load(content)
    except _yaml.YAMLError as exc:
        raise HTTPException(status_code=400, detail=f"YAML 解析失败: {exc}")

    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="kubeconfig 顶层必须是对象")

    api_version = str(parsed.get("apiVersion") or "").strip()
    kind = str(parsed.get("kind") or "").strip()
    clusters_list = parsed.get("clusters") or []
    contexts_list = parsed.get("contexts") or []
    users_list = parsed.get("users") or []

    if api_version != "v1" or kind != "Config":
        raise HTTPException(
            status_code=400,
            detail=f"非合法 kubeconfig: apiVersion={api_version or '空'}, kind={kind or '空'}",
        )
    if not (clusters_list and contexts_list and users_list):
        raise HTTPException(
            status_code=400,
            detail="kubeconfig 缺少 clusters / contexts / users 之一",
        )

    server = ""
    first_cluster = clusters_list[0]
    if isinstance(first_cluster, dict):
        server = str((first_cluster.get("cluster") or {}).get("server") or "").strip()
    current_context = str(parsed.get("current-context") or "").strip()

    safe_name = re.sub(r"[^\w\-]", "_", name) or "cluster"
    output_path = _KUBECONFIG_GEN_DIR / f"{safe_name}.yaml"
    _KUBECONFIG_GEN_DIR.mkdir(parents=True, exist_ok=True)
    try:
        output_path.write_text(content, encoding="utf-8")
    except Exception as exc:
        logger.error("[k8s] upload-text write failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"写入 kubeconfig 失败: {exc}")

    logger.info("[k8s] kubeconfig text saved → %s", output_path)
    relative = f"backend/data/kubeconfigs/{safe_name}.yaml"
    return {
        "path": str(output_path),
        "relative": relative,
        "server": server,
        "current_context": current_context,
        "clusters": [c.get("name") for c in clusters_list if isinstance(c, dict)],
        "contexts": [c.get("name") for c in contexts_list if isinstance(c, dict)],
        "users":    [u.get("name") for u in users_list    if isinstance(u, dict)],
    }


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
        data = _serialize_k8s_resource(cluster["id"], resource)
        # 同步返回 yaml 字符串, 让前端不必引入 yaml 库
        import yaml as _yaml
        try:
            yaml_text = _yaml.safe_dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
        except Exception:
            yaml_text = ""
        return {
            "kind": _normalize_resource_kind(kind),
            "name": name,
            "namespace": namespace,
            "data": data,
            "yaml": yaml_text,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[k8s] resource_detail failed kind=%s namespace=%s name=%s error=%s", kind, namespace, name, exc)
        raise HTTPException(502, f"k8s 连接失败: {exc}")


# ── YAML 编辑 + scale (借鉴 jay-codemine/k8s_operation) ──────────────────────

def _replace_k8s_resource(cluster_id: str | None, kind: str, namespace: str, name: str, body: dict):
    """用新 dict 全量替换资源 (PUT 语义), 按 kind 分派对应 SDK 方法。"""
    normalized_kind = _normalize_resource_kind(kind)
    v1, apps = _get_client(cluster_id)
    batch = _get_batch_client(cluster_id)

    if normalized_kind == "pod":
        return v1.replace_namespaced_pod(name=name, namespace=namespace, body=body)
    if normalized_kind == "deployment":
        return apps.replace_namespaced_deployment(name=name, namespace=namespace, body=body)
    if normalized_kind == "daemonset":
        return apps.replace_namespaced_daemon_set(name=name, namespace=namespace, body=body)
    if normalized_kind == "statefulset":
        return apps.replace_namespaced_stateful_set(name=name, namespace=namespace, body=body)
    if normalized_kind == "job":
        return batch.replace_namespaced_job(name=name, namespace=namespace, body=body)
    if normalized_kind == "cronjob":
        return batch.replace_namespaced_cron_job(name=name, namespace=namespace, body=body)
    if normalized_kind == "service":
        return v1.replace_namespaced_service(name=name, namespace=namespace, body=body)
    if normalized_kind == "configmap":
        return v1.replace_namespaced_config_map(name=name, namespace=namespace, body=body)
    if normalized_kind == "node":
        return v1.replace_node(name=name, body=body)
    raise HTTPException(status_code=400, detail=f"不支持的资源类型: {kind}")


class K8sYamlPayload(BaseModel):
    yaml_text: str


@router.put("/resource-yaml")
async def update_resource_yaml(
    body: K8sYamlPayload,
    kind: str = Query(..., description="资源类型"),
    name: str = Query(..., description="资源名称"),
    namespace: str = Query("", description="命名空间"),
    cluster_id: str = Query("", description="集群 ID"),
    user: User = Depends(require_admin),
):
    """以 YAML 文本全量替换 (replace) 一个 K8s 资源。校验 metadata.name/namespace 一致。"""
    import yaml as _yaml

    text = (body.yaml_text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="YAML 文本不能为空")
    try:
        parsed = _yaml.safe_load(text)
    except _yaml.YAMLError as exc:
        raise HTTPException(status_code=400, detail=f"YAML 解析失败: {exc}")
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="YAML 顶层必须是对象")

    meta = parsed.get("metadata") or {}
    if meta.get("name") and meta.get("name") != name:
        raise HTTPException(
            status_code=400,
            detail=f"metadata.name={meta.get('name')} 与 URL name={name} 不一致 (禁止改名)",
        )
    if namespace and meta.get("namespace") and meta.get("namespace") != namespace:
        raise HTTPException(
            status_code=400,
            detail=f"metadata.namespace={meta.get('namespace')} 与 URL namespace={namespace} 不一致",
        )

    try:
        cluster = _resolve_cluster_for_user(user, cluster_id or None)
        updated = _replace_k8s_resource(cluster["id"], kind, namespace, name, parsed)
        return {
            "ok": True,
            "kind": _normalize_resource_kind(kind),
            "name": name,
            "namespace": namespace,
            "data": _serialize_k8s_resource(cluster["id"], updated),
        }
    except HTTPException:
        raise
    except Exception as exc:
        # K8s API 错误通常含 reason / 详细信息 (ApiException.body)
        detail = getattr(exc, "body", None) or str(exc)
        logger.warning("[k8s] update_resource_yaml failed kind=%s ns=%s name=%s: %s", kind, namespace, name, detail)
        raise HTTPException(status_code=400, detail=f"应用 YAML 失败: {detail}")


class K8sScalePayload(BaseModel):
    replicas: int


@router.post("/resource-scale")
async def scale_resource(
    body: K8sScalePayload,
    kind: str = Query(..., description="资源类型: deployment / statefulset"),
    name: str = Query(..., description="资源名称"),
    namespace: str = Query(..., description="命名空间"),
    cluster_id: str = Query("", description="集群 ID"),
    user: User = Depends(require_admin),
):
    """扩缩容 Deployment / StatefulSet (DaemonSet 不支持 scale)。"""
    if body.replicas < 0 or body.replicas > 1000:
        raise HTTPException(status_code=400, detail="replicas 必须在 [0, 1000] 范围")
    normalized = _normalize_resource_kind(kind)
    if normalized not in {"deployment", "statefulset"}:
        raise HTTPException(status_code=400, detail=f"scale 不支持资源类型: {kind}")

    try:
        cluster = _resolve_cluster_for_user(user, cluster_id or None)
        _, apps = _get_client(cluster["id"])
        # 用 patch 改 spec.replicas (比 replace 安全, 不需要传整个对象)
        patch_body = {"spec": {"replicas": body.replicas}}
        if normalized == "deployment":
            apps.patch_namespaced_deployment_scale(name=name, namespace=namespace, body=patch_body)
        else:
            apps.patch_namespaced_stateful_set_scale(name=name, namespace=namespace, body=patch_body)
        return {"ok": True, "kind": normalized, "name": name, "namespace": namespace, "replicas": body.replicas}
    except HTTPException:
        raise
    except Exception as exc:
        detail = getattr(exc, "body", None) or str(exc)
        logger.warning("[k8s] scale_resource failed kind=%s ns=%s name=%s replicas=%s: %s", kind, namespace, name, body.replicas, detail)
        raise HTTPException(status_code=400, detail=f"扩缩容失败: {detail}")


# ── 镜像点击编辑 (Pri 3 借鉴 jay-codemine) ──────────────────────────────────

class K8sImageContainer(BaseModel):
    name: str
    image: str


class K8sImageUpdatePayload(BaseModel):
    containers: list[K8sImageContainer]


@router.post("/resource-image")
async def update_resource_image(
    body: K8sImageUpdatePayload,
    kind: str = Query(..., description="资源类型: deployment/statefulset/daemonset/cronjob"),
    name: str = Query(..., description="资源名称"),
    namespace: str = Query(..., description="命名空间"),
    cluster_id: str = Query("", description="集群 ID"),
    user: User = Depends(require_admin),
):
    """更新工作负载镜像 (触发 rolling update)。
    用 strategic merge patch 改 spec.template.spec.containers[*].image。
    CronJob 改 spec.jobTemplate.spec.template.spec.containers (路径不同)。
    """
    normalized = _normalize_resource_kind(kind)
    if normalized not in {"deployment", "statefulset", "daemonset", "cronjob"}:
        raise HTTPException(status_code=400, detail=f"不支持的镜像更新资源类型: {kind}")
    if not body.containers:
        raise HTTPException(status_code=400, detail="containers 不能为空")

    containers_patch = [{"name": c.name, "image": c.image} for c in body.containers]

    if normalized == "cronjob":
        patch_body = {
            "spec": {"jobTemplate": {"spec": {"template": {"spec": {"containers": containers_patch}}}}}
        }
    else:
        patch_body = {
            "spec": {"template": {"spec": {"containers": containers_patch}}}
        }

    try:
        cluster = _resolve_cluster_for_user(user, cluster_id or None)
        _, apps = _get_client(cluster["id"])
        batch = _get_batch_client(cluster["id"])
        if normalized == "deployment":
            apps.patch_namespaced_deployment(name=name, namespace=namespace, body=patch_body)
        elif normalized == "statefulset":
            apps.patch_namespaced_stateful_set(name=name, namespace=namespace, body=patch_body)
        elif normalized == "daemonset":
            apps.patch_namespaced_daemon_set(name=name, namespace=namespace, body=patch_body)
        else:   # cronjob
            batch.patch_namespaced_cron_job(name=name, namespace=namespace, body=patch_body)
        return {
            "ok": True, "kind": normalized, "name": name, "namespace": namespace,
            "containers": containers_patch,
        }
    except HTTPException:
        raise
    except Exception as exc:
        detail = getattr(exc, "body", None) or str(exc)
        logger.warning("[k8s] update_resource_image failed kind=%s ns=%s name=%s: %s", kind, namespace, name, detail)
        raise HTTPException(status_code=400, detail=f"镜像更新失败: {detail}")


# ── Events 关联 ─────────────────────────────────────────────────────────────

@router.get("/resource-events")
async def resource_events(
    kind: str = Query(..., description="资源类型"),
    name: str = Query(..., description="资源名称"),
    namespace: str = Query("", description="命名空间"),
    cluster_id: str = Query("", description="集群 ID"),
    user: User = Depends(current_user),
):
    """拿对应资源的 K8s events (按时间倒序)。
    用 field_selector 过滤 involvedObject.name + involvedObject.kind。
    """
    normalized = _normalize_resource_kind(kind)
    # 把单数 kind 映射回 K8s 资源 kind (首字母大写驼峰)
    KIND_PASCAL = {
        "pod": "Pod", "deployment": "Deployment", "daemonset": "DaemonSet",
        "statefulset": "StatefulSet", "job": "Job", "cronjob": "CronJob",
        "service": "Service", "node": "Node",
    }
    involved_kind = KIND_PASCAL.get(normalized, normalized)

    try:
        cluster = _resolve_cluster_for_user(user, cluster_id or None)
        v1, _ = _get_client(cluster["id"])
        selector = f"involvedObject.name={name},involvedObject.kind={involved_kind}"
        if namespace:
            events = v1.list_namespaced_event(namespace=namespace, field_selector=selector, limit=200)
        else:
            events = v1.list_event_for_all_namespaces(field_selector=selector, limit=200)

        items = []
        for ev in events.items:
            ts = ev.last_timestamp or ev.event_time or ev.first_timestamp
            items.append({
                "type":     ev.type or "Normal",
                "reason":   ev.reason or "",
                "message":  ev.message or "",
                "count":    ev.count or 1,
                "source":   ev.source.component if ev.source else "",
                "first_ts": ev.first_timestamp.isoformat() if ev.first_timestamp else "",
                "last_ts":  ts.isoformat() if ts else "",
            })
        items.sort(key=lambda x: x["last_ts"], reverse=True)
        return {"kind": normalized, "name": name, "namespace": namespace, "items": items, "total": len(items)}
    except HTTPException:
        raise
    except Exception as exc:
        detail = getattr(exc, "body", None) or str(exc)
        logger.warning("[k8s] resource_events failed kind=%s ns=%s name=%s: %s", kind, namespace, name, detail)
        raise HTTPException(status_code=502, detail=f"events 查询失败: {detail}")


# ── 批量操作 (借鉴 jay-codemine/k8s_operation 浮动操作条) ────────────────────

def _delete_k8s_resource(cluster_id: str | None, kind: str, namespace: str, name: str):
    """按 kind 分派 delete (foreground 级联)。"""
    from kubernetes import client as k8s_client
    normalized = _normalize_resource_kind(kind)
    v1, apps = _get_client(cluster_id)
    batch = _get_batch_client(cluster_id)
    opts = k8s_client.V1DeleteOptions(propagation_policy="Foreground")

    if normalized == "pod":
        return v1.delete_namespaced_pod(name=name, namespace=namespace, body=opts)
    if normalized == "deployment":
        return apps.delete_namespaced_deployment(name=name, namespace=namespace, body=opts)
    if normalized == "daemonset":
        return apps.delete_namespaced_daemon_set(name=name, namespace=namespace, body=opts)
    if normalized == "statefulset":
        return apps.delete_namespaced_stateful_set(name=name, namespace=namespace, body=opts)
    if normalized == "job":
        return batch.delete_namespaced_job(name=name, namespace=namespace, body=opts)
    if normalized == "cronjob":
        return batch.delete_namespaced_cron_job(name=name, namespace=namespace, body=opts)
    if normalized == "service":
        return v1.delete_namespaced_service(name=name, namespace=namespace, body=opts)
    if normalized == "configmap":
        return v1.delete_namespaced_config_map(name=name, namespace=namespace, body=opts)
    raise HTTPException(status_code=400, detail=f"不支持的资源类型删除: {kind}")


def _restart_workload(cluster_id: str | None, kind: str, namespace: str, name: str):
    """重启工作负载:
    - Deployment / StatefulSet / DaemonSet: patch annotation
      spec.template.metadata.annotations.kubectl.kubernetes.io/restartedAt
      = ISO 时间, 触发滚动重启 (kubectl rollout restart 同款)
    - Pod: delete (依赖 controller 重建)
    - 其它资源不支持
    """
    from datetime import datetime, timezone
    normalized = _normalize_resource_kind(kind)
    if normalized == "pod":
        return _delete_k8s_resource(cluster_id, "pod", namespace, name)

    if normalized not in {"deployment", "statefulset", "daemonset"}:
        raise HTTPException(status_code=400, detail=f"不支持重启资源类型: {kind}")

    _, apps = _get_client(cluster_id)
    now_iso = datetime.now(timezone.utc).isoformat()
    patch_body = {
        "spec": {
            "template": {
                "metadata": {
                    "annotations": {
                        "kubectl.kubernetes.io/restartedAt": now_iso,
                    }
                }
            }
        }
    }
    if normalized == "deployment":
        return apps.patch_namespaced_deployment(name=name, namespace=namespace, body=patch_body)
    if normalized == "statefulset":
        return apps.patch_namespaced_stateful_set(name=name, namespace=namespace, body=patch_body)
    if normalized == "daemonset":
        return apps.patch_namespaced_daemon_set(name=name, namespace=namespace, body=patch_body)


class K8sBatchItem(BaseModel):
    kind: str
    namespace: str = ""
    name: str


class K8sBatchPayload(BaseModel):
    action: str   # 'delete' | 'restart'
    items: list[K8sBatchItem]


@router.post("/resource-batch")
async def batch_operate(body: K8sBatchPayload, cluster_id: str = Query("", description="集群 ID"), user: User = Depends(require_admin)):
    """批量执行 delete / restart, 并发处理, 返回 per-item 结果。"""
    if body.action not in {"delete", "restart"}:
        raise HTTPException(status_code=400, detail=f"不支持的批量操作: {body.action}")
    if not body.items:
        raise HTTPException(status_code=400, detail="items 不能为空")
    if len(body.items) > 200:
        raise HTTPException(status_code=400, detail="单次批量上限 200 个资源")

    cluster = _resolve_cluster_for_user(user, cluster_id or None)
    cid = cluster["id"]
    loop = asyncio.get_running_loop()

    def _do_one(item: K8sBatchItem) -> dict:
        try:
            if body.action == "delete":
                _delete_k8s_resource(cid, item.kind, item.namespace, item.name)
            else:
                _restart_workload(cid, item.kind, item.namespace, item.name)
            return {"ok": True, "kind": item.kind, "namespace": item.namespace, "name": item.name}
        except HTTPException as he:
            return {"ok": False, "kind": item.kind, "namespace": item.namespace, "name": item.name, "error": str(he.detail)}
        except Exception as exc:
            detail = getattr(exc, "body", None) or str(exc)
            return {"ok": False, "kind": item.kind, "namespace": item.namespace, "name": item.name, "error": str(detail)}

    # 并发但限制并行度避免压垮 APIServer
    sem = asyncio.Semaphore(8)
    async def _bounded(item: K8sBatchItem) -> dict:
        async with sem:
            return await loop.run_in_executor(None, _do_one, item)

    results = await asyncio.gather(*[_bounded(i) for i in body.items])
    success = sum(1 for r in results if r.get("ok"))
    failed = len(results) - success
    return {
        "action": body.action,
        "total": len(results),
        "success": success,
        "failed": failed,
        "results": results,
    }


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


# ── Round 3: AI 自然语言 K8s 操作 (轻量意图解析 + 高危确认) ─────────────────

import re as _re_k8sai

# 数字/中文数字归一
_CN_NUM = {"一":1, "二":2, "两":2, "三":3, "四":4, "五":5, "六":6, "七":7, "八":8, "九":9, "十":10}

def _parse_int(s: str) -> int | None:
    s = (s or "").strip()
    if not s: return None
    if s.isdigit(): return int(s)
    if s in _CN_NUM: return _CN_NUM[s]
    try: return int(s)
    except Exception: return None

# kind 别名归一 (用户自然语言可能用各种说法)
_AI_KIND_ALIASES = {
    "pod": "pod", "pods": "pod", "容器": "pod",
    "deployment": "deployment", "deployments": "deployment", "deploy": "deployment", "部署": "deployment",
    "statefulset": "statefulset", "statefulsets": "statefulset", "sts": "statefulset", "有状态": "statefulset",
    "daemonset": "daemonset", "daemonsets": "daemonset", "ds": "daemonset", "守护进程": "daemonset",
    "job": "job", "jobs": "job", "任务": "job",
    "cronjob": "cronjob", "cronjobs": "cronjob", "定时任务": "cronjob",
    "service": "service", "services": "service", "svc": "service", "服务": "service",
    "node": "node", "nodes": "node", "节点": "node",
}

# 危险操作集
_DANGER_ACTIONS = {"scale", "restart", "delete", "update_image"}


def _ai_parse_intent(text: str, default_namespace: str = "") -> dict:
    """从自然语言解析意图。返回:
       { action, kind?, name?, namespace?, replicas?, image?, danger: bool, summary: str }
       识别不出返回 { action: 'unknown', summary: ... }
    """
    raw = (text or "").strip()
    if not raw:
        return {"action": "unknown", "summary": "请输入指令"}

    lower = raw.lower()
    ns = default_namespace or ""
    # 提取 namespace: "在 X 命名空间" / "namespace X" / "ns=X"
    ns_match = (
        _re_k8sai.search(r"在\s*([\w\-]+)\s*命名空间", raw) or
        _re_k8sai.search(r"namespace[:=\s]+([\w\-]+)", raw, _re_k8sai.IGNORECASE) or
        _re_k8sai.search(r"\bns[:=\s]+([\w\-]+)", raw, _re_k8sai.IGNORECASE)
    )
    if ns_match:
        ns = ns_match.group(1)

    # 提取 kind (按 key 长度倒序匹配, 避免 "deploy" 错过 "deployment")
    kind = None
    for keyword in sorted(_AI_KIND_ALIASES.keys(), key=len, reverse=True):
        if keyword in lower:
            kind = _AI_KIND_ALIASES[keyword]
            break

    # ── create / deploy / 部署 ── (优先级最高: 含 "部署/创建/新建/deploy/create")
    # 注意: 英文 deploy/create 必须加 \b 边界, 否则 "deployments" 会被误匹配 deploy
    create_hit = (
        _re_k8sai.search(r"创建|新建|部署", raw) or
        _re_k8sai.search(r"\b(deploy|create)\b", raw, _re_k8sai.IGNORECASE)
    )
    if create_hit:
        if kind in {"deployment", "statefulset", "daemonset", "service"}:
            name = _extract_resource_name(raw, kind, exclude_words={"创建","新建","部署","deploy","create","部"})
            # 提取镜像 (image xxx:yyy / 镜像 xxx:yyy)
            img_match = _re_k8sai.search(r"(?:镜像|image)[^\w]*([\w\-./:@]+:[\w\-./@]+)", raw, _re_k8sai.IGNORECASE)
            image = img_match.group(1) if img_match else None
            # 提取副本数 (N 副本 / replicas=N)
            rep_match = (
                _re_k8sai.search(r"(\d+|[一二两三四五六七八九十])\s*副本", raw) or
                _re_k8sai.search(r"replicas?\s*[:=]\s*(\d+)", raw, _re_k8sai.IGNORECASE)
            )
            replicas = _parse_int(rep_match.group(1)) if rep_match else None
            summary_extra = []
            if image: summary_extra.append(f"镜像={image}")
            if replicas: summary_extra.append(f"副本={replicas}")
            return {
                "action": "create", "kind": kind,
                "name": name or "nginx",   # 默认名兜底
                "namespace": ns or "default",
                "image": image, "replicas": replicas,
                "danger": True,
                "summary": f"创建 {kind} {ns or 'default'}/{name or 'nginx'}" + (" " + " ".join(summary_extra) if summary_extra else ""),
            }

    # ── scale (扩容/缩容/扩到 N 副本) ──
    scale_match = (
        _re_k8sai.search(r"(?:扩容|缩容|扩|缩|scale)[^\d]{0,8}(\d+|[一二两三四五六七八九十])\s*副?本?", raw) or
        _re_k8sai.search(r"replicas?\s*[:=]\s*(\d+)", raw, _re_k8sai.IGNORECASE) or
        _re_k8sai.search(r"(?:到|至|=)\s*(\d+)\s*个?", raw)
    )
    if scale_match:
        # 未显式提到 kind 时默认 deployment (最常见扩缩对象)
        scale_kind = kind if kind in {"deployment", "statefulset"} else "deployment"
        replicas = _parse_int(scale_match.group(1))
        name = _extract_resource_name(raw, scale_kind, exclude_words={"扩容","缩容","scale"})
        return {
            "action": "scale", "kind": scale_kind, "name": name, "namespace": ns,
            "replicas": replicas, "danger": True,
            "summary": f"扩缩容 {scale_kind} {ns or '?'}/{name or '?'} 到 {replicas} 副本",
        }

    # ── delete ──
    if _re_k8sai.search(r"删除|删掉", raw) or _re_k8sai.search(r"\b(delete|remove)\b", raw, _re_k8sai.IGNORECASE):
        if kind:
            name = _extract_resource_name(raw, kind, exclude_words={"删除","delete"})
            return {
                "action": "delete", "kind": kind, "name": name, "namespace": ns,
                "danger": True,
                "summary": f"删除 {kind} {ns or '?'}/{name or '?'} (不可恢复)",
            }

    # ── restart ──
    if _re_k8sai.search(r"重启", raw) or _re_k8sai.search(r"\b(restart|rollout)\b", raw, _re_k8sai.IGNORECASE):
        if kind in {"deployment", "statefulset", "daemonset", "pod"}:
            name = _extract_resource_name(raw, kind, exclude_words={"重启","restart","rollout"})
            return {
                "action": "restart", "kind": kind, "name": name, "namespace": ns,
                "danger": True,
                "summary": f"重启 {kind} {ns or '?'}/{name or '?'} (触发滚动重启)",
            }

    # ── update image ──
    # 镜像 URL 模式: 字母开头 + (字母数字 / 横线 / 下划线 / 点 / 斜杠)* + 冒号 + 标签字符
    # 覆盖: nginx:latest / nginx:1.25-alpine / swr.cn-north-4.com/ddn-k8s/docker.io/redash/nginx:latest
    _img_re = r"([a-zA-Z][a-zA-Z0-9_\-./]*:[a-zA-Z0-9_\-.@]+)"
    # 优先匹配 "镜像/image" 紧跟的 URL
    img_match = _re_k8sai.search(rf"(?:镜像|image)[^\w]*{_img_re}", raw, _re_k8sai.IGNORECASE)
    if not img_match:
        # 兜底: 含动作词 (改/换/更新/update/change/set) + 文本里任意 xxx:yyy 形式
        has_img_action = (
            _re_k8sai.search(r"改为|改成|换为|换成|改|换|更新|修改|替换", raw) or
            _re_k8sai.search(r"\b(update|change|set|edit)\b", raw, _re_k8sai.IGNORECASE)
        )
        if has_img_action:
            img_match = _re_k8sai.search(_img_re, raw)
    if img_match and kind in {"deployment", "statefulset", "daemonset"}:
        image = img_match.group(1)
        # 关键: 只在镜像 URL 之前的文本里找 name, 否则 "deployment的nginx 改为 redash/nginx:latest"
        # 会把 nginx 当成镜像内 token 排除。镜像前的文本不含镜像 URL, 无歧义。
        img_idx = raw.find(image)
        search_zone = raw[:img_idx] if img_idx > 0 else raw
        name = _extract_resource_name(
            search_zone, kind,
            exclude_words={"镜像","image","更新","update","change","set","改","换"},
        )
        return {
            "action": "update_image", "kind": kind, "name": name, "namespace": ns,
            "image": image, "danger": True,
            "summary": f"更新 {kind} {ns or '?'}/{name or '?'} 镜像 → {image}",
        }

    # ── list / show / 查 ──
    if _re_k8sai.search(r"列出|查看|查询|显示|有哪些|多少", raw) or _re_k8sai.search(r"\b(list|show|get|ls)\b", raw, _re_k8sai.IGNORECASE):
        if kind:
            return {
                "action": "list", "kind": kind, "namespace": ns, "danger": False,
                "summary": f"列出 {kind}" + (f" (namespace={ns})" if ns else ""),
            }

    # ── inspect (巡检 / 健康检查 / 集群体检) ──
    if (_re_k8sai.search(r"巡检|体检|健康|检查|诊断", raw) or
        _re_k8sai.search(r"\b(inspect|check|health|diagnose|status)\b", raw, _re_k8sai.IGNORECASE)):
        return {
            "action": "inspect", "kind": "cluster", "namespace": ns, "danger": False,
            "summary": "巡检集群健康 (节点 / Pod / 异常 events / 工作负载 Ready)",
        }

    return {
        "action": "unknown", "danger": False,
        "summary": f"无法识别: {raw}",
        "hint": "当前轻量解析器仅识别确定性指令模式 (不是完整 LLM Function Calling).",
        "examples": [
            "部署 deployment nginx 镜像 nginx:1.25 3 副本",
            "扩容 nginx 到 5 副本",
            "重启 deployment web",
            "删除 pod foo",
            "更新 deployment web 镜像 nginx:1.25",
            "列出 deployments",
            "巡检集群",
        ],
    }


def _extract_resource_name(raw: str, kind: str, exclude_words: set[str] | None = None) -> str | None:
    """从文本中提取资源名 (找所有 ASCII 字母开头的 token, 过滤掉 kind / 动作关键字)。

    用 ASCII 字母开头明确限定 (K8s 资源名规范), 避免被中文 \\w 干扰。
    支持中英文连写: "deployment部署nginx" 也能提取出 "nginx"。
    """
    exclude_words = {w.lower() for w in (exclude_words or set())}
    exclude_words.add(kind.lower())
    # K8s 资源名: 小写字母/数字/横线, 必须字母开头, 1-63 字符
    ascii_tokens = _re_k8sai.findall(r"([a-zA-Z][a-zA-Z0-9\-]{0,62})", raw)
    for t in ascii_tokens:
        tl = t.lower()
        if tl in exclude_words:
            continue
        # 过滤掉所有 kind 别名 (避免把 "deploy" 误当 name)
        if tl in _AI_KIND_ALIASES:
            continue
        # 跳过纯数字开头 (不可能是 k8s name)
        return t
    return None


class K8sAIParsePayload(BaseModel):
    text: str
    namespace: str = ""


@router.post("/ai/parse")
async def k8s_ai_parse(body: K8sAIParsePayload, cluster_id: str = Query("", description="集群 ID"), user: User = Depends(current_user)):
    """解析自然语言成 K8s 意图 (不执行, 不需要管理员权限)。
    高危意图前端要弹 confirm 让用户复核。
    """
    intent = _ai_parse_intent(body.text, default_namespace=body.namespace)
    return intent


def _run_cluster_inspect(cluster_id: str) -> dict:
    """集群健康巡检: 节点 / Pod / 工作负载 / 异常 events 汇总。
    返回 markdown 报告 + 关键指标 dict。
    """
    v1, apps = _get_client(cluster_id)
    findings: list[str] = []
    metrics: dict = {}

    # 1. 节点
    try:
        nodes = v1.list_node().items
        ready_count = 0
        not_ready: list[str] = []
        for n in nodes:
            conds = getattr(n.status, "conditions", None) or []
            is_ready = any(c.type == "Ready" and c.status == "True" for c in conds)
            if is_ready:
                ready_count += 1
            else:
                not_ready.append(n.metadata.name)
        metrics["nodes"] = {"total": len(nodes), "ready": ready_count, "not_ready": not_ready}
        findings.append(f"**节点**: {ready_count}/{len(nodes)} Ready" + (f", 异常: {', '.join(not_ready)}" if not_ready else ""))
    except Exception as exc:
        findings.append(f"**节点**: 查询失败 ({exc})")
        metrics["nodes"] = {"error": str(exc)}

    # 2. Pod 统计 + 频繁重启
    try:
        pods = v1.list_pod_for_all_namespaces().items
        phase_count: dict[str, int] = {}
        high_restart_pods: list[dict] = []
        for p in pods:
            ph = p.status.phase or "Unknown"
            phase_count[ph] = phase_count.get(ph, 0) + 1
            total_restart = sum((cs.restart_count or 0) for cs in (p.status.container_statuses or []))
            if total_restart >= 5:
                high_restart_pods.append({
                    "namespace": p.metadata.namespace,
                    "name": p.metadata.name,
                    "restarts": total_restart,
                })
        high_restart_pods.sort(key=lambda x: x["restarts"], reverse=True)
        metrics["pods"] = {
            "total": len(pods),
            "phase": phase_count,
            "high_restart": high_restart_pods[:10],
        }
        findings.append(
            f"**Pod**: 总 {len(pods)} | " +
            " | ".join(f"{k} {v}" for k, v in sorted(phase_count.items()))
        )
        if high_restart_pods:
            top = high_restart_pods[:5]
            findings.append(
                "**频繁重启 (≥5)**: " +
                "; ".join(f"{p['namespace']}/{p['name']} ×{p['restarts']}" for p in top) +
                (f" (还有 {len(high_restart_pods) - 5} 个未显示)" if len(high_restart_pods) > 5 else "")
            )
    except Exception as exc:
        findings.append(f"**Pod**: 查询失败 ({exc})")
        metrics["pods"] = {"error": str(exc)}

    # 3. Deployment / StatefulSet Ready 比例
    try:
        deps = apps.list_deployment_for_all_namespaces().items
        not_full: list[str] = []
        for d in deps:
            spec_replicas = (d.spec.replicas if d.spec.replicas is not None else 0)
            ready_replicas = (d.status.ready_replicas or 0)
            if ready_replicas < spec_replicas:
                not_full.append(f"{d.metadata.namespace}/{d.metadata.name} ({ready_replicas}/{spec_replicas})")
        metrics["deployments"] = {"total": len(deps), "not_full": not_full}
        msg = f"**Deployment**: 总 {len(deps)}"
        if not_full:
            msg += f", 未就绪 {len(not_full)}: " + "; ".join(not_full[:5])
            if len(not_full) > 5: msg += f" (+{len(not_full) - 5})"
        findings.append(msg)
    except Exception as exc:
        findings.append(f"**Deployment**: 查询失败 ({exc})")
        metrics["deployments"] = {"error": str(exc)}

    # 4. 最近 Warning events (跨 namespace, 限 10 条)
    try:
        events = v1.list_event_for_all_namespaces(field_selector="type=Warning", limit=50).items
        warnings: list[dict] = []
        for ev in events:
            ts = ev.last_timestamp or ev.event_time or ev.first_timestamp
            warnings.append({
                "ns": ev.metadata.namespace,
                "involved": f"{ev.involved_object.kind}/{ev.involved_object.name}" if ev.involved_object else "?",
                "reason": ev.reason or "",
                "message": (ev.message or "").strip().split("\n")[0][:200],
                "count": ev.count or 1,
                "ts": ts.isoformat() if ts else "",
            })
        warnings.sort(key=lambda x: x["ts"], reverse=True)
        metrics["warning_events"] = warnings[:10]
        if warnings:
            findings.append(f"**最近 Warning Events**: 共 {len(warnings)}, 最新 5 条:")
            for w in warnings[:5]:
                findings.append(f"  - `{w['ns']}/{w['involved']}` **{w['reason']}** ×{w['count']}: {w['message']}")
        else:
            findings.append("**最近 Warning Events**: 无")
    except Exception as exc:
        findings.append(f"**Events**: 查询失败 ({exc})")
        metrics["warning_events"] = {"error": str(exc)}

    report_md = "## 🔍 集群巡检报告\n\n" + "\n\n".join(findings)
    return {
        "ok": True, "action": "inspect", "report": report_md, "metrics": metrics,
    }


def _generate_k8s_yaml_template(kind: str, name: str, namespace: str, image: str | None, replicas: int | None) -> str:
    """生成 K8s 资源最小可用 YAML 模板 (deployment/statefulset/daemonset/service)。"""
    image = (image or "").strip() or "nginx:latest"
    rep = replicas if isinstance(replicas, int) and replicas > 0 else 1
    name = (name or "").strip() or "ai-created"
    ns = (namespace or "").strip() or "default"

    if kind == "deployment":
        return (
            "apiVersion: apps/v1\nkind: Deployment\n"
            f"metadata:\n  name: {name}\n  namespace: {ns}\n  labels:\n    app: {name}\n"
            f"spec:\n  replicas: {rep}\n"
            f"  selector:\n    matchLabels:\n      app: {name}\n"
            f"  template:\n    metadata:\n      labels:\n        app: {name}\n"
            f"    spec:\n      containers:\n      - name: {name}\n        image: {image}\n        ports:\n        - containerPort: 80\n"
        )
    if kind == "statefulset":
        return (
            "apiVersion: apps/v1\nkind: StatefulSet\n"
            f"metadata:\n  name: {name}\n  namespace: {ns}\n"
            f"spec:\n  serviceName: {name}\n  replicas: {rep}\n"
            f"  selector:\n    matchLabels:\n      app: {name}\n"
            f"  template:\n    metadata:\n      labels:\n        app: {name}\n"
            f"    spec:\n      containers:\n      - name: {name}\n        image: {image}\n"
        )
    if kind == "daemonset":
        return (
            "apiVersion: apps/v1\nkind: DaemonSet\n"
            f"metadata:\n  name: {name}\n  namespace: {ns}\n"
            f"spec:\n  selector:\n    matchLabels:\n      app: {name}\n"
            f"  template:\n    metadata:\n      labels:\n        app: {name}\n"
            f"    spec:\n      containers:\n      - name: {name}\n        image: {image}\n"
        )
    if kind == "service":
        return (
            "apiVersion: v1\nkind: Service\n"
            f"metadata:\n  name: {name}\n  namespace: {ns}\n"
            f"spec:\n  selector:\n    app: {name}\n"
            f"  ports:\n  - port: 80\n    targetPort: 80\n  type: ClusterIP\n"
        )
    raise HTTPException(status_code=400, detail=f"不支持模板生成: {kind}")


def _parse_k8s_api_error(exc) -> dict:
    """从 ApiException / FailToCreateError 提取 reason / message / code, 给前端友好显示。"""
    import json as _json
    body = getattr(exc, "body", None)
    if isinstance(body, str):
        try:
            parsed = _json.loads(body)
            return {
                "reason":  parsed.get("reason", ""),
                "message": parsed.get("message", str(exc)),
                "code":    parsed.get("code", 0),
                "details": parsed.get("details", {}),
            }
        except Exception:
            return {"reason": "", "message": body, "code": 0, "details": {}}
    # FailToCreateError: api_exceptions 是列表
    api_excs = getattr(exc, "api_exceptions", None)
    if api_excs:
        return _parse_k8s_api_error(api_excs[0])
    return {"reason": "", "message": str(exc), "code": 0, "details": {}}


class K8sAIExecPayload(BaseModel):
    action: str
    kind: str = ""
    name: str = ""
    namespace: str = ""
    replicas: int | None = None
    image: str | None = None
    force: bool = False   # create 时 force=true: 已存在则先 delete 再 create


@router.post("/ai/execute")
async def k8s_ai_execute(body: K8sAIExecPayload, cluster_id: str = Query("", description="集群 ID"), user: User = Depends(require_admin)):
    """执行已确认的 AI 解析意图。高危操作需要 admin 权限 + 前端 confirm。
    复用现有 scale/restart/delete/update_image 实现。"""
    if not body.action:
        raise HTTPException(status_code=400, detail="action 必填")
    if not body.kind and body.action != "list":
        raise HTTPException(status_code=400, detail="kind 必填")
    if not body.name and body.action != "list":
        raise HTTPException(status_code=400, detail="name 必填")

    cluster = _resolve_cluster_for_user(user, cluster_id or None)
    cid = cluster["id"]
    try:
        if body.action == "list":
            return {"ok": True, "action": "list", "hint": f"跳转 UI 查看 {body.kind} 列表即可"}
        elif body.action == "inspect":
            return _run_cluster_inspect(cid)
        elif body.action == "create":
            import yaml as _yaml
            try:
                from kubernetes import utils as k8s_utils
            except ImportError:
                raise HTTPException(status_code=500, detail="kubernetes.utils 不可用")
            yaml_text = _generate_k8s_yaml_template(body.kind, body.name, body.namespace, body.image, body.replicas)
            api_client = _get_api_client(cid)
            docs = [d for d in _yaml.safe_load_all(yaml_text) if isinstance(d, dict) and d]
            created = []
            already_exists_items: list[dict] = []
            for doc in docs:
                doc_kind = doc.get("kind", "")
                doc_md = doc.get("metadata", {})
                doc_name = doc_md.get("name", "")
                doc_ns = doc_md.get("namespace", "")
                try:
                    res_list = k8s_utils.create_from_dict(api_client, doc)
                    for res in (res_list if isinstance(res_list, list) else [res_list]):
                        md = getattr(res, "metadata", None)
                        created.append({
                            "kind": getattr(res, "kind", None) or doc_kind,
                            "name": getattr(md, "name", None) if md else doc_name,
                            "namespace": getattr(md, "namespace", None) if md else doc_ns,
                        })
                except Exception as create_exc:
                    err = _parse_k8s_api_error(create_exc)
                    if err.get("reason") == "AlreadyExists":
                        if body.force:
                            # 先 delete 旧资源, 等几秒等 finalizer, 再 create
                            try:
                                _delete_k8s_resource(cid, _normalize_resource_kind(doc_kind), doc_ns, doc_name)
                            except Exception as del_exc:
                                logger.warning("[k8s-ai] force-delete before create failed: %s", del_exc)
                            # 简单轮询: 最多 8s 等资源消失
                            import time as _time
                            v1, apps = _get_client(cid)
                            for _ in range(16):
                                _time.sleep(0.5)
                                try:
                                    _read_k8s_resource(cid, _normalize_resource_kind(doc_kind), doc_ns, doc_name)
                                except Exception:
                                    break   # 读不到 = 已删除
                            # 重试 create
                            try:
                                res_list = k8s_utils.create_from_dict(api_client, doc)
                                for res in (res_list if isinstance(res_list, list) else [res_list]):
                                    md = getattr(res, "metadata", None)
                                    created.append({
                                        "kind": getattr(res, "kind", None) or doc_kind,
                                        "name": getattr(md, "name", None) if md else doc_name,
                                        "namespace": getattr(md, "namespace", None) if md else doc_ns,
                                    })
                            except Exception as retry_exc:
                                rerr = _parse_k8s_api_error(retry_exc)
                                raise HTTPException(
                                    status_code=400,
                                    detail=f"替换失败 ({rerr.get('reason') or 'Error'}): {rerr.get('message') or '未知错误'}",
                                )
                        else:
                            already_exists_items.append({
                                "kind": doc_kind, "name": doc_name, "namespace": doc_ns,
                            })
                    else:
                        # 其它错误 (Invalid / Forbidden / ...) 直接抛友好提示
                        raise HTTPException(
                            status_code=400,
                            detail=f"创建失败 ({err.get('reason') or 'Error'}): {err.get('message') or '未知错误'}",
                        )

            # 没有强制覆盖且发现重名 → 返回结构化错误让前端弹"是否替换"
            if already_exists_items and not body.force:
                item = already_exists_items[0]
                raise HTTPException(
                    status_code=409,
                    detail={
                        "reason": "AlreadyExists",
                        "message": f"{item['kind']} {item['namespace']}/{item['name']} 已存在",
                        "kind": item["kind"],
                        "name": item["name"],
                        "namespace": item["namespace"],
                        "can_force": True,
                    },
                )
            return {"ok": True, "action": "create", "created": created, "yaml": yaml_text}
        elif body.action == "scale":
            if body.replicas is None: raise HTTPException(status_code=400, detail="replicas 必填")
            patch_body = {"spec": {"replicas": body.replicas}}
            _, apps = _get_client(cid)
            if body.kind == "deployment":
                apps.patch_namespaced_deployment_scale(name=body.name, namespace=body.namespace, body=patch_body)
            elif body.kind == "statefulset":
                apps.patch_namespaced_stateful_set_scale(name=body.name, namespace=body.namespace, body=patch_body)
            else:
                raise HTTPException(status_code=400, detail=f"scale 不支持 {body.kind}")
            return {"ok": True, "action": "scale", "replicas": body.replicas}
        elif body.action == "restart":
            _restart_workload(cid, body.kind, body.namespace, body.name)
            return {"ok": True, "action": "restart"}
        elif body.action == "delete":
            _delete_k8s_resource(cid, body.kind, body.namespace, body.name)
            return {"ok": True, "action": "delete"}
        elif body.action == "update_image":
            if not body.image: raise HTTPException(status_code=400, detail="image 必填")
            # 用 K8s SDK 拿当前 containers 列表, 把第一个容器换成新镜像
            resource = _read_k8s_resource(cid, body.kind, body.namespace, body.name)
            api_client = _get_api_client(cid)
            data = _trim_k8s_detail(api_client.sanitize_for_serialization(resource))
            template = (data.get("spec", {}).get("template", {}) if body.kind != "cronjob"
                        else data.get("spec", {}).get("jobTemplate", {}).get("spec", {}).get("template", {}))
            containers = (template.get("spec", {}).get("containers") or [])
            if not containers:
                raise HTTPException(status_code=400, detail="未找到容器列表")
            patch_containers = [{"name": containers[0]["name"], "image": body.image}]
            patch_body = {"spec": {"template": {"spec": {"containers": patch_containers}}}}
            _, apps = _get_client(cid)
            if body.kind == "deployment":
                apps.patch_namespaced_deployment(name=body.name, namespace=body.namespace, body=patch_body)
            elif body.kind == "statefulset":
                apps.patch_namespaced_stateful_set(name=body.name, namespace=body.namespace, body=patch_body)
            else:
                apps.patch_namespaced_daemon_set(name=body.name, namespace=body.namespace, body=patch_body)
            return {"ok": True, "action": "update_image", "image": body.image}
        else:
            raise HTTPException(status_code=400, detail=f"未知 action: {body.action}")
    except HTTPException:
        raise
    except Exception as exc:
        detail = getattr(exc, "body", None) or str(exc)
        logger.warning("[k8s-ai] execute failed action=%s: %s", body.action, detail)
        raise HTTPException(status_code=400, detail=f"执行失败: {detail}")


# ── Round 2: Pod 日志 SSE 流 ─────────────────────────────────────────────────

@router.get("/pod-logs-stream")
async def pod_logs_stream(
    namespace: str = Query(..., description="命名空间"),
    pod_name: str = Query(..., description="Pod 名称"),
    cluster_id: str = Query("", description="集群 ID"),
    container: str = Query("", description="容器名称"),
    tail_lines: int = Query(100, description="启动尾部行数"),
    user: User = Depends(current_user),
):
    """实时 Pod 日志 SSE 流。K8s SDK 用 follow=True 阻塞返回 generator,
    放线程池避免阻塞 asyncio 事件循环。前端用 EventSource 消费。
    """
    import threading
    from fastapi.responses import StreamingResponse

    cluster = _resolve_cluster_for_user(user, cluster_id or None)
    cid = cluster["id"]
    value = max(10, min(int(tail_lines or 100), 1000))

    async def _gen():
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=512)
        stop_event = asyncio.Event()

        def _reader():
            try:
                v1, _ = _get_client(cid)
                w = v1.read_namespaced_pod_log(
                    name=pod_name, namespace=namespace,
                    container=(container or None),
                    tail_lines=value, follow=True, _preload_content=False,
                    timestamps=True,
                )
                for line_bytes in w.stream(amt=None, decode_content=True):
                    if stop_event.is_set():
                        break
                    try:
                        text = line_bytes.decode("utf-8", errors="replace") if isinstance(line_bytes, (bytes, bytearray)) else str(line_bytes)
                    except Exception:
                        text = str(line_bytes)
                    # 投递到 asyncio.Queue (线程安全 via loop.call_soon_threadsafe)
                    try:
                        loop.call_soon_threadsafe(queue.put_nowait, text)
                    except Exception:
                        break
            except Exception as exc:
                err = f"[stream error] {exc}"
                try:
                    loop.call_soon_threadsafe(queue.put_nowait, err)
                except Exception:
                    pass
            finally:
                try:
                    loop.call_soon_threadsafe(queue.put_nowait, None)   # 终止标志
                except Exception:
                    pass

        # 启动读线程
        threading.Thread(target=_reader, name=f"k8s-log-stream-{pod_name}", daemon=True).start()

        try:
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    # heartbeat 避免代理超时断开
                    yield ": keep-alive\n\n"
                    continue
                if msg is None:
                    yield "event: end\ndata: stream closed\n\n"
                    break
                # SSE 帧: 每行 data: 前缀
                for line in str(msg).rstrip("\n").split("\n"):
                    yield f"data: {line}\n"
                yield "\n"
        finally:
            stop_event.set()

    return StreamingResponse(_gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Round 2: 资源创建 (YAML / 多资源) ────────────────────────────────────────

class K8sCreatePayload(BaseModel):
    yaml_text: str


@router.post("/resource-create")
async def create_resource(
    body: K8sCreatePayload,
    cluster_id: str = Query("", description="集群 ID"),
    user: User = Depends(require_admin),
):
    """从 YAML 文本创建一个或多个资源 (--- 分隔多文档)。
    用 kubernetes.utils.create_from_dict 自动按 kind 分派 SDK API。
    """
    import yaml as _yaml
    try:
        from kubernetes import utils as k8s_utils
    except ImportError:
        raise HTTPException(status_code=500, detail="kubernetes.utils 不可用")

    text = (body.yaml_text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="YAML 不能为空")
    try:
        docs = list(_yaml.safe_load_all(text))
    except _yaml.YAMLError as exc:
        raise HTTPException(status_code=400, detail=f"YAML 解析失败: {exc}")
    docs = [d for d in docs if isinstance(d, dict) and d]
    if not docs:
        raise HTTPException(status_code=400, detail="YAML 不含任何有效资源")

    try:
        cluster = _resolve_cluster_for_user(user, cluster_id or None)
        api_client = _get_api_client(cluster["id"])
        created = []
        errors = []
        for doc in docs:
            try:
                # create_from_dict 返回创建的 K8s 资源列表 (通常 1 个)
                res_list = k8s_utils.create_from_dict(api_client, doc)
                for res in (res_list if isinstance(res_list, list) else [res_list]):
                    kind = getattr(res, "kind", None) or doc.get("kind") or ""
                    md = getattr(res, "metadata", None)
                    created.append({
                        "kind": kind,
                        "name": getattr(md, "name", None) if md else doc.get("metadata", {}).get("name"),
                        "namespace": getattr(md, "namespace", None) if md else doc.get("metadata", {}).get("namespace"),
                    })
            except k8s_utils.FailToCreateError as exc:
                errors.append({"kind": doc.get("kind", ""), "name": doc.get("metadata", {}).get("name", ""), "error": str(exc)})
            except Exception as exc:
                errors.append({"kind": doc.get("kind", ""), "name": doc.get("metadata", {}).get("name", ""), "error": getattr(exc, "body", None) or str(exc)})
        return {"created": created, "errors": errors, "total": len(docs)}
    except HTTPException:
        raise
    except Exception as exc:
        detail = getattr(exc, "body", None) or str(exc)
        logger.warning("[k8s] resource_create failed: %s", detail)
        raise HTTPException(status_code=400, detail=f"创建失败: {detail}")


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
                {
                    "name": c.name, "image": c.image, "ready": False, "restarts": 0,
                    # 上次终止信息（来自 lastState.terminated）
                    "last_restart_reason": None,
                    "last_restart_time": None,
                    "last_restart_exit_code": None,
                    # 当前 waiting 原因（如 CrashLoopBackOff / ImagePullBackOff）
                    "waiting_reason": None,
                }
                for c in (pod.spec.containers or [])
            ]
            if pod.status.container_statuses:
                for cs in pod.status.container_statuses:
                    for c in containers:
                        if c["name"] != cs.name:
                            continue
                        c["ready"] = cs.ready or False
                        c["restarts"] = cs.restart_count or 0
                        # 上次终止状态：containerStatuses[*].lastState.terminated
                        last_state = getattr(cs, "last_state", None)
                        terminated = getattr(last_state, "terminated", None) if last_state else None
                        if terminated is not None:
                            c["last_restart_reason"] = terminated.reason or None
                            c["last_restart_exit_code"] = (
                                terminated.exit_code
                                if terminated.exit_code is not None else None
                            )
                            finished_at = getattr(terminated, "finished_at", None)
                            if finished_at:
                                c["last_restart_time"] = finished_at.isoformat() if hasattr(finished_at, "isoformat") else str(finished_at)
                        # 当前 waiting 原因（用于补充 CrashLoopBackOff 这类）
                        cur_state = getattr(cs, "state", None)
                        waiting = getattr(cur_state, "waiting", None) if cur_state else None
                        if waiting is not None and waiting.reason:
                            c["waiting_reason"] = waiting.reason

            # Pod 级汇总：取重启最多的 container 的 last_restart_reason；都为 0 时取首个 waiting_reason
            with_restart = [c for c in containers if c["restarts"] > 0 and c["last_restart_reason"]]
            if with_restart:
                primary = max(with_restart, key=lambda c: c["restarts"])
                pod_last_reason = primary["last_restart_reason"]
                pod_last_time = primary["last_restart_time"]
                pod_last_exit = primary["last_restart_exit_code"]
                pod_last_container = primary["name"]
            else:
                first_waiting = next((c for c in containers if c["waiting_reason"]), None)
                pod_last_reason = first_waiting["waiting_reason"] if first_waiting else None
                pod_last_time = None
                pod_last_exit = None
                pod_last_container = first_waiting["name"] if first_waiting else None

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
                    "last_restart_reason":     pod_last_reason,
                    "last_restart_time":       pod_last_time,
                    "last_restart_exit_code":  pod_last_exit,
                    "last_restart_container":  pod_last_container,
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


# ── ConfigMaps ────────────────────────────────────────────────────────────────

@router.get("/configmaps")
async def list_configmaps(
    namespace: str = Query("", description="命名空间，空=全部"),
    cluster_id: str = Query("", description="集群 ID"),
    user: User = Depends(current_user),
):
    try:
        cluster = _resolve_cluster_for_user(user, cluster_id or None)
        v1, _ = _get_client(cluster["id"])
        items = (
            v1.list_config_map_for_all_namespaces().items
            if not namespace
            else v1.list_namespaced_config_map(namespace).items
        )
        result = []
        for item in items:
            data_keys = list((item.data or {}).keys()) + list((item.binary_data or {}).keys())
            # 大小估算: data values 字符长度 + binary_data base64 长度
            size = sum(len(v or "") for v in (item.data or {}).values()) + sum(
                len(v or "") for v in (item.binary_data or {}).values()
            )
            result.append(
                {
                    "name": item.metadata.name,
                    "namespace": item.metadata.namespace,
                    "keys": data_keys,
                    "keyCount": len(data_keys),
                    "size": size,
                    "age": _safe_age(item.metadata.creation_timestamp),
                }
            )
        return result
    except Exception as exc:
        logger.warning("[k8s] list_configmaps failed: %s", exc)
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
