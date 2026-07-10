"""Validation and secure storage for kubeconfig text pasted by an administrator."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yaml


class KubeconfigImportError(ValueError):
    """Raised when pasted text is not a usable kubeconfig."""


def parse_and_store_kubeconfig(
    content: str,
    requested_name: str,
    output_dir: Path,
) -> dict:
    normalized_content = (content or "").strip()
    if not normalized_content:
        raise KubeconfigImportError("kubeconfig 文本不能为空")

    try:
        parsed = yaml.safe_load(normalized_content)
    except yaml.YAMLError as exc:
        raise KubeconfigImportError(f"YAML 解析失败: {exc}") from exc

    if not isinstance(parsed, dict):
        raise KubeconfigImportError("kubeconfig 顶层必须是对象")

    api_version = str(parsed.get("apiVersion") or "").strip()
    kind = str(parsed.get("kind") or "").strip()
    clusters_list = parsed.get("clusters") or []
    contexts_list = parsed.get("contexts") or []
    users_list = parsed.get("users") or []

    if api_version != "v1" or kind != "Config":
        raise KubeconfigImportError(
            f"非合法 kubeconfig: apiVersion={api_version or '空'}, kind={kind or '空'}"
        )
    if not (clusters_list and contexts_list and users_list):
        raise KubeconfigImportError("kubeconfig 缺少 clusters / contexts / users 之一")

    first_cluster = clusters_list[0]
    if not isinstance(first_cluster, dict):
        raise KubeconfigImportError("kubeconfig clusters[0] 格式无效")
    first_cluster_name = str(first_cluster.get("name") or "").strip()
    server = str((first_cluster.get("cluster") or {}).get("server") or "").strip()
    if not server:
        raise KubeconfigImportError("kubeconfig clusters[0] 缺少 API Server 地址")

    current_context = str(parsed.get("current-context") or "").strip()
    selected_context = next(
        (
            item
            for item in contexts_list
            if isinstance(item, dict)
            and str(item.get("name") or "").strip() == current_context
        ),
        contexts_list[0],
    )
    context_data = selected_context.get("context") or {} if isinstance(selected_context, dict) else {}
    namespace = str(context_data.get("namespace") or "").strip()
    suggested_name = requested_name.strip() or first_cluster_name or current_context or "k8s-cluster"

    safe_name = re.sub(r"[^\w\-]", "_", suggested_name) or "cluster"
    content_hash = hashlib.sha256(normalized_content.encode("utf-8")).hexdigest()[:10]
    filename = f"{safe_name}-{content_hash}.yaml"
    output_path = output_dir / filename
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        output_path.write_text(normalized_content, encoding="utf-8")
        try:
            output_path.chmod(0o600)
        except OSError:
            pass
    except OSError as exc:
        raise KubeconfigImportError(f"写入 kubeconfig 失败: {exc}") from exc

    return {
        "path": str(output_path),
        "filename": filename,
        "server": server,
        "current_context": current_context,
        "namespace": namespace,
        "suggested_name": suggested_name,
        "clusters": [item.get("name") for item in clusters_list if isinstance(item, dict)],
        "contexts": [item.get("name") for item in contexts_list if isinstance(item, dict)],
        "users": [item.get("name") for item in users_list if isinstance(item, dict)],
    }
