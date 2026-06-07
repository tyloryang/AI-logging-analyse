"""K8s AI Agent — Phase 1 spike.

LLM Tool Use 接口, 让 Claude 自主决定调哪些 K8s 工具完成用户的运维指令.
- 工具列表: list / get / scale / restart / delete / update_image / inspect (7 个)
- 多轮 tool_use loop, max 5 轮防止失控
- 直接复用 routers.kubernetes 里已有的实现, 不重复造轮子
- 复用现有 ai_analyzer Anthropic 配置, 不重新读 env

Phase 2 计划:
- MCP server 接入 (工具优先来自 MCP, 失败降级到本地)
- 多 agent 编排 (规划 agent + 执行 agent)
- SSE 流式响应 (当前 Phase 1 是同步, 一次性返回)
"""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel

from auth.deps import current_user, require_admin
from auth.models import User
from routers.kubernetes import (
    _resolve_cluster_for_user, _get_client, _read_k8s_resource,
    _delete_k8s_resource, _restart_workload, _serialize_k8s_resource,
    _run_cluster_inspect, _normalize_resource_kind, _trim_k8s_detail,
    _pod_brief,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ── 工具定义 (Claude tool_use schema) ───────────────────────────────────────

TOOLS: list[dict] = [
    {
        "name": "k8s_list_resources",
        "description": "列出 K8s 资源 (Pod / Deployment / Service / ConfigMap / Node 等). 用于查询集群中的资源.",
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "description": "资源类型: pod/deployment/daemonset/statefulset/job/cronjob/service/configmap/node"},
                "namespace": {"type": "string", "description": "命名空间, 留空查所有"},
            },
            "required": ["kind"],
        },
    },
    {
        "name": "k8s_get_resource",
        "description": "获取单个 K8s 资源的详细信息.",
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "description": "资源类型"},
                "name": {"type": "string", "description": "资源名"},
                "namespace": {"type": "string", "description": "命名空间"},
            },
            "required": ["kind", "name"],
        },
    },
    {
        "name": "k8s_scale_workload",
        "description": "扩缩容 Deployment / StatefulSet. ⚠️ 高危: 会改变服务实例数.",
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["deployment", "statefulset"]},
                "name": {"type": "string"},
                "namespace": {"type": "string"},
                "replicas": {"type": "integer", "minimum": 0, "maximum": 1000},
            },
            "required": ["kind", "name", "namespace", "replicas"],
        },
    },
    {
        "name": "k8s_restart_workload",
        "description": "重启工作负载 (rollout restart). Deploy/STS/DS 走 patch annotation, Pod 走 delete.",
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["pod", "deployment", "statefulset", "daemonset"]},
                "name": {"type": "string"},
                "namespace": {"type": "string"},
            },
            "required": ["kind", "name", "namespace"],
        },
    },
    {
        "name": "k8s_delete_resource",
        "description": "删除 K8s 资源. ⚠️ 极高危: 不可恢复. 务必确认.",
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string"},
                "name": {"type": "string"},
                "namespace": {"type": "string"},
            },
            "required": ["kind", "name", "namespace"],
        },
    },
    {
        "name": "k8s_update_image",
        "description": "更新工作负载镜像 (rolling update).",
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["deployment", "statefulset", "daemonset"]},
                "name": {"type": "string"},
                "namespace": {"type": "string"},
                "image": {"type": "string", "description": "新镜像 URL: nginx:1.25 / registry.example.com/foo/bar:v1"},
            },
            "required": ["kind", "name", "namespace", "image"],
        },
    },
    {
        "name": "k8s_inspect_cluster",
        "description": "巡检集群健康: 节点 / Pod 状态 / 频繁重启 / Deployment 就绪 / Warning events.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "k8s_get_configmap_data",
        "description": (
            "查看 ConfigMap 的 data 内容 (key/value 键值对). "
            "排查应用配置错误 / 验证配置项 / 找环境变量值时用. "
            "比 k8s_get_resource 输出更精简, 只返回 data 部分."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "ConfigMap 名"},
                "namespace": {"type": "string", "description": "命名空间"},
                "key": {"type": "string", "description": "只看某个 key 的 value (可选), 留空返回所有 keys 的预览"},
            },
            "required": ["name", "namespace"],
        },
    },
    {
        "name": "k8s_get_pod_logs",
        "description": (
            "查看 Pod 容器日志. 排查 CrashLoopBackOff / Error / OOMKilled / 应用异常时首选. "
            "如果 Pod 在 CrashLoopBackOff 或重启循环, 设 previous=true 看上次崩溃前的日志 (当前进程的日志可能还没写出来)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Pod 名"},
                "namespace": {"type": "string", "description": "命名空间"},
                "container": {"type": "string", "description": "容器名 (多容器 Pod 必填, 单容器可空)"},
                "tail_lines": {"type": "integer", "description": "尾行数, 默认 100, 上限 500", "minimum": 1, "maximum": 500},
                "previous": {"type": "boolean", "description": "true=取上次崩溃前的日志 (--previous), 默认 false"},
            },
            "required": ["name", "namespace"],
        },
    },
    {
        "name": "k8s_update_configmap",
        "description": (
            "更新 ConfigMap 的 data (键值对). 高危: 配置改动会影响所有挂载该 CM 的 Pod, "
            "通常需要重启 Pod 才会真正生效. 平台会先呈现 key 级别的 diff 给用户审批, 用户批准后才实际下发. "
            "默认 merge=true (局部更新, 保留其它 key); 只有用户明确说『清空 / 全量替换』才传 merge=false."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "ConfigMap 名"},
                "namespace": {"type": "string", "description": "命名空间"},
                "data": {
                    "type": "object",
                    "description": "要写入的 key→value 键值对. merge=true 时只覆盖这些 key, merge=false 时全量替换整个 data.",
                    "additionalProperties": {"type": "string"},
                },
                "merge": {
                    "type": "boolean",
                    "description": "true=只覆盖传入的 keys 保留其它 (推荐, 默认 true); false=全量替换 data (危险)",
                },
            },
            "required": ["name", "namespace", "data"],
        },
    },
]


# ── 安全边界: 写工具集合 (需要用户二次审批才执行) ────────────────────────────
MUTATION_TOOLS: set[str] = {
    "k8s_scale_workload",
    "k8s_restart_workload",
    "k8s_delete_resource",
    "k8s_update_image",
    "k8s_update_configmap",
}
# 只读工具 (可直接执行, 不影响集群状态)
READONLY_TOOLS: set[str] = {
    "k8s_list_resources",
    "k8s_get_resource",
    "k8s_inspect_cluster",
    "k8s_get_pod_logs",
    "k8s_get_configmap_data",
}


def _tool_handler(cluster_id: str, tool_name: str, tool_input: dict) -> str:
    """执行单个工具调用, 返回字符串结果 (失败返回错误描述)。
    注意: 此函数不做边界检查, 调用方需先判断 tool_name 是否在 MUTATION_TOOLS, 是的话
    应该走 approve 流程而非直接调用此函数。
    """
    try:
        if tool_name == "k8s_list_resources":
            kind = _normalize_resource_kind(tool_input.get("kind", ""))
            ns = tool_input.get("namespace") or ""
            v1, apps = _get_client(cluster_id)
            if kind == "pod":
                items = v1.list_pod_for_all_namespaces().items if not ns else v1.list_namespaced_pod(ns).items
                brief = [_pod_brief(p) for p in items[:50]]
                return f"找到 {len(items)} 个 Pod (展示前 50): " + "\n".join(
                    f"- {p['namespace']}/{p['name']} status={p['status']}" for p in brief
                )
            if kind == "deployment":
                deps = apps.list_deployment_for_all_namespaces().items if not ns else apps.list_namespaced_deployment(ns).items
                return f"找到 {len(deps)} 个 Deployment: " + "\n".join(
                    f"- {d.metadata.namespace}/{d.metadata.name} ready={d.status.ready_replicas or 0}/{d.spec.replicas or 0}"
                    for d in deps[:30]
                )
            if kind == "service":
                svcs = v1.list_service_for_all_namespaces().items if not ns else v1.list_namespaced_service(ns).items
                return f"找到 {len(svcs)} 个 Service: " + "\n".join(
                    f"- {s.metadata.namespace}/{s.metadata.name} type={s.spec.type}" for s in svcs[:30]
                )
            if kind == "configmap":
                cms = v1.list_config_map_for_all_namespaces().items if not ns else v1.list_namespaced_config_map(ns).items
                return f"找到 {len(cms)} 个 ConfigMap (展示前 30): " + "\n".join(
                    f"- {c.metadata.namespace}/{c.metadata.name} keys={len((c.data or {}))+len((c.binary_data or {}))}"
                    for c in cms[:30]
                )
            if kind == "node":
                nodes = v1.list_node().items
                return f"找到 {len(nodes)} 个 Node: " + "\n".join(
                    f"- {n.metadata.name} " +
                    ("Ready" if any(c.type == "Ready" and c.status == "True" for c in (n.status.conditions or [])) else "NotReady")
                    for n in nodes
                )
            return f"暂不支持 list {kind}"

        if tool_name == "k8s_get_resource":
            kind = tool_input.get("kind", "")
            name = tool_input.get("name", "")
            ns = tool_input.get("namespace", "") or ""
            resource = _read_k8s_resource(cluster_id, kind, ns, name)
            data = _serialize_k8s_resource(cluster_id, resource)
            # 截短输出避免压垮 LLM context
            import json as _json
            text = _json.dumps(data, ensure_ascii=False, indent=2)
            return text if len(text) < 4000 else text[:4000] + "\n... (已截断)"

        if tool_name == "k8s_scale_workload":
            kind = tool_input.get("kind", "")
            name = tool_input.get("name", "")
            ns = tool_input.get("namespace", "")
            replicas = int(tool_input.get("replicas", 0))
            _, apps = _get_client(cluster_id)
            patch = {"spec": {"replicas": replicas}}
            if kind == "deployment":
                apps.patch_namespaced_deployment_scale(name=name, namespace=ns, body=patch)
            else:
                apps.patch_namespaced_stateful_set_scale(name=name, namespace=ns, body=patch)
            return f"✓ {kind} {ns}/{name} 已扩缩到 {replicas} 副本"

        if tool_name == "k8s_restart_workload":
            kind = tool_input.get("kind", "")
            name = tool_input.get("name", "")
            ns = tool_input.get("namespace", "")
            _restart_workload(cluster_id, kind, ns, name)
            return f"✓ 已下发 {kind} {ns}/{name} 重启 (rolling update)"

        if tool_name == "k8s_delete_resource":
            kind = tool_input.get("kind", "")
            name = tool_input.get("name", "")
            ns = tool_input.get("namespace", "")
            _delete_k8s_resource(cluster_id, kind, ns, name)
            return f"✓ 已删除 {kind} {ns}/{name}"

        if tool_name == "k8s_update_image":
            kind = tool_input.get("kind", "")
            name = tool_input.get("name", "")
            ns = tool_input.get("namespace", "")
            image = tool_input.get("image", "")
            resource = _read_k8s_resource(cluster_id, kind, ns, name)
            data = _trim_k8s_detail(_get_client(cluster_id)[0].api_client.sanitize_for_serialization(resource))
            containers = data.get("spec", {}).get("template", {}).get("spec", {}).get("containers") or []
            if not containers:
                return f"✗ 未找到容器列表"
            _, apps = _get_client(cluster_id)
            patch = {"spec": {"template": {"spec": {"containers": [{"name": containers[0]["name"], "image": image}]}}}}
            if kind == "deployment":
                apps.patch_namespaced_deployment(name=name, namespace=ns, body=patch)
            elif kind == "statefulset":
                apps.patch_namespaced_stateful_set(name=name, namespace=ns, body=patch)
            else:
                apps.patch_namespaced_daemon_set(name=name, namespace=ns, body=patch)
            return f"✓ {kind} {ns}/{name} 容器 {containers[0]['name']} 镜像 → {image}"

        if tool_name == "k8s_inspect_cluster":
            result = _run_cluster_inspect(cluster_id)
            return result.get("report", "巡检完成但报告为空")

        if tool_name == "k8s_get_configmap_data":
            name = (tool_input.get("name") or "").strip()
            ns = (tool_input.get("namespace") or "").strip()
            key = (tool_input.get("key") or "").strip()
            if not name or not ns:
                return "✗ 缺少必填参数 name / namespace"
            v1, _ = _get_client(cluster_id)
            try:
                cm = v1.read_namespaced_config_map(name=name, namespace=ns)
            except Exception as exc:
                body = getattr(exc, "body", None) or str(exc)
                return f"✗ 读取 ConfigMap 失败: {body}"
            data = dict(cm.data or {})
            bin_keys = list((cm.binary_data or {}).keys())
            if key:
                if key not in data:
                    return f"✗ ConfigMap {ns}/{name} 中不存在 key={key}. 已有 keys: {list(data.keys()) + bin_keys}"
                val = data.get(key, "")
                MAX = 3500
                if len(val) > MAX:
                    val = val[: MAX - 60] + "\n...(已截断, 原始长度 " + str(len(data.get(key, ""))) + ")"
                return f"ConfigMap {ns}/{name} key={key}:\n```\n{val}\n```"
            # 概览: 列 keys + 每个 value 前 200 字符预览
            if not data and not bin_keys:
                return f"ConfigMap {ns}/{name} 是空的 (data / binary_data 都为空)"
            lines = [f"ConfigMap {ns}/{name} 共 {len(data) + len(bin_keys)} 个 key:"]
            for k, v in data.items():
                preview = (v or "").replace("\n", " ⏎ ")
                if len(preview) > 200:
                    preview = preview[:200] + "..."
                lines.append(f"- `{k}` ({len(v or '')} 字符): {preview}")
            for k in bin_keys:
                lines.append(f"- `{k}` (二进制, base64)")
            lines.append("\n(如需看某个 key 完整内容, 用 key 参数再调一次本工具)")
            return "\n".join(lines)

        if tool_name == "k8s_update_configmap":
            name = (tool_input.get("name") or "").strip()
            ns = (tool_input.get("namespace") or "").strip()
            new_data = dict(tool_input.get("data") or {})
            merge = tool_input.get("merge", True)
            if not name or not ns:
                return "✗ 缺少必填参数 name / namespace"
            if not isinstance(new_data, dict):
                return "✗ data 必须是对象 (key→value)"
            # 值必须可序列化为 string (ConfigMap data 是 map<string,string>)
            for k, v in list(new_data.items()):
                if not isinstance(v, str):
                    new_data[k] = "" if v is None else str(v)

            v1, _ = _get_client(cluster_id)
            try:
                cm = v1.read_namespaced_config_map(name=name, namespace=ns)
            except Exception as exc:
                body = getattr(exc, "body", None) or str(exc)
                return f"✗ 读取 ConfigMap 失败 (无法更新): {body}"

            before = dict(cm.data or {})
            after = {**before, **new_data} if merge else dict(new_data)
            # 计算 diff 用于回执消息
            added = [k for k in after if k not in before]
            removed = [k for k in before if k not in after]
            changed = [k for k in after if k in before and before[k] != after[k]]
            if not added and not removed and not changed:
                return f"ConfigMap {ns}/{name} 无变化, 已跳过"

            cm.data = after
            try:
                v1.replace_namespaced_config_map(name=name, namespace=ns, body=cm)
            except Exception as exc:
                body = getattr(exc, "body", None) or str(exc)
                return f"✗ 更新 ConfigMap 失败: {body}"
            return (
                f"✓ ConfigMap {ns}/{name} 已更新: "
                f"+{len(added)} ~{len(changed)} −{len(removed)} "
                f"(用 merge={merge}). 提示: 挂载该 CM 的 Pod 可能需要重启才能加载新配置."
            )

        if tool_name == "k8s_get_pod_logs":
            name = tool_input.get("name", "").strip()
            ns = (tool_input.get("namespace") or "").strip()
            container = (tool_input.get("container") or "").strip() or None
            tail = int(tool_input.get("tail_lines") or 100)
            tail = max(20, min(tail, 500))
            previous = bool(tool_input.get("previous", False))
            if not name or not ns:
                return "✗ 缺少必填参数 name / namespace"
            v1, _ = _get_client(cluster_id)
            try:
                logs = v1.read_namespaced_pod_log(
                    name=name,
                    namespace=ns,
                    container=container,
                    tail_lines=tail,
                    timestamps=True,
                    previous=previous,
                )
            except Exception as exc:
                # 多容器 Pod 不指定 container 时 k8s API 会报错, 给一个友好提示
                body = getattr(exc, "body", None) or str(exc)
                if "a container name must be specified" in str(body) or "must be specified" in str(body):
                    return (
                        f"✗ Pod {ns}/{name} 是多容器 Pod, 请在 container 参数指定容器名后重试. "
                        f"先用 k8s_get_resource 查 spec.containers[*].name."
                    )
                return f"✗ 读取日志失败: {body}"

            logs = (logs or "").strip()
            if not logs:
                tip = "(空) 可能容器刚启动 / 没输出 stdout. 试试 previous=true 看上次崩溃前的日志."
                return f"Pod {ns}/{name}{' [' + container + ']' if container else ''} {'previous ' if previous else ''}日志:\n{tip}"

            # 截短: 头 + 尾, 中间省略, 比纯尾部对 LLM 更有用 (启动信息往往在头部)
            MAX = 3500
            if len(logs) > MAX:
                head_len = MAX // 3
                tail_len = MAX - head_len - 60
                logs = logs[:head_len] + "\n...(中间已省略)...\n" + logs[-tail_len:]
            header = f"Pod {ns}/{name}{' [' + container + ']' if container else ''} {'previous ' if previous else ''}最近 {tail} 行日志:"
            return f"{header}\n```\n{logs}\n```"

        return f"未知工具: {tool_name}"

    except HTTPException as he:
        return f"✗ 工具执行失败: {he.detail}"
    except Exception as exc:
        detail = getattr(exc, "body", None) or str(exc)
        return f"✗ 工具执行异常: {detail}"


# ── Anthropic tool_use loop ────────────────────────────────────────────────

SYSTEM_PROMPT = """你是 AIOps 平台的 K8s 运维助手. 你的工作是帮用户完成 Kubernetes 集群操作.
（自我介绍时不要主动说"基于大语言模型构建"或类似话术，直接说"我是 AIOps K8s 运维助手"即可）.

可用工具 (10 个):
- 只读: k8s_list_resources / k8s_get_resource / k8s_get_pod_logs / k8s_get_configmap_data / k8s_inspect_cluster
- 写 (需审批): k8s_scale_workload / k8s_restart_workload / k8s_delete_resource / k8s_update_image / k8s_update_configmap

**重要安全边界**:
- 只读工具 (list / get / logs / configmap / inspect): 你可以直接调用, 平台立即返回结果.
- 写工具 (scale / restart / delete / update_image): 平台**不会立即执行**, 而是收集为待审批操作, 等用户在 UI 上一对一确认后才真的下发到集群.
- 你看到写工具返回 "[PENDING_APPROVAL] ..." 时, 这表示已经提交给用户审核, 不要重试也不要尝试绕过.
- 用户拒绝某项操作后会有对应消息, 你应该尊重决定, 不要重复尝试同一操作.

排障常用套路:
- 用户说"Pod X 起不来 / CrashLoopBackOff / 一直重启 / 报错": 先 k8s_get_resource 查 status+events, 再 k8s_get_pod_logs 看应用日志; 如果当前进程没日志或刚启动, 加 previous=true 看上次崩溃前的日志.
- 多容器 Pod 取日志前先用 k8s_get_resource 看 spec.containers[*].name, 然后在 container 参数指定.
- 用户说"看 configmap / 查配置": 用 k8s_get_configmap_data 直接看 data 键值, 不要用 k8s_get_resource (后者返回的对象太大不利于 LLM 抓重点).
- 用户说"改 configmap / 把 X 改成 Y / 修改配置": 用 k8s_update_configmap. 默认 merge=true 只覆盖你传入的 keys, 别的 key 不动 — 这是更安全的默认; 只有用户明确说"清空 / 全量替换 / 只留这些"才传 merge=false. 平台会自动给用户呈现 key 级 diff 让其审批, 你不用自己呈现 diff. 改完提醒用户: 挂载该 CM 的 Pod 可能需要重启才能加载新配置.
- 用户说"集群有什么问题 / 巡检一下": 直接调 k8s_inspect_cluster.

规则:
1. 用户的自然语言指令可能模糊, 你需要先用只读工具 (list/get/logs/inspect) 确认目标资源再生成写操作.
2. 默认 namespace 是 default, 用户没说就用 default.
3. 给用户简洁的中文回复, 关键信息用 **粗体** 或 `代码` 突出. 日志内容直接转述关键错误行, 不要照搬整段.
4. 一次回复里最多生成 3 个写操作待审批, 不要一口气提交一大批.
5. 完成只读查询后用 1-2 句话总结发现, 再提议下一步写操作 (如果需要).
"""


class K8sAgentChatPayload(BaseModel):
    message: str
    cluster_id: str = ""
    namespace: str = ""


# ── LLM provider 抽象 (复用 ai_analyzer 的 AI_PROVIDER/AI_MODEL/AI_BASE_URL/AI_API_KEY) ────

def _get_llm_config() -> dict:
    """从「智能体配置」(系统设置 → AI Agent → 模型) 拿激活模型配置.

    优先级:
    1. agent_config.json 里 active=True 的模型 (系统设置页可改)
    2. fallback: env (AI_PROVIDER / AI_MODEL / ...) — 兼容老配置

    管理 UI: /aiops/config (前端) → /api/agent-config/models (后端)
    """
    # 先尝试从系统模型设置读
    try:
        from routers.agent_config import _load as _load_agent_config, _get_active_model, _normalize_model_record
        cfg = _load_agent_config()
        active = _get_active_model(cfg)
        if active:
            normalized, _ = _normalize_model_record(active)
            provider = (normalized.get("runtime_provider") or "").strip().lower()
            model = (normalized.get("runtime_model") or normalized.get("name") or "").strip()
            api_key = (normalized.get("api_key") or "").strip()
            base_url = (normalized.get("base_url") or "").strip()

            if provider == "anthropic":
                if not api_key:
                    raise HTTPException(
                        status_code=500,
                        detail=f"系统设置的激活模型「{normalized.get('name', '?')}」缺少 API key. 请到 /aiops/config 补填.",
                    )
                if not model:
                    raise HTTPException(status_code=500, detail=f"激活模型「{normalized.get('name', '?')}」缺少 runtime_model")
                return {"provider": "anthropic", "api_key": api_key, "model": model, "source": "agent_config"}

            if provider in {"openai", "local", "ollama", "vllm", "oneapi", "qwen", "deepseek", "gemini", "gpt"}:
                if not base_url:
                    raise HTTPException(
                        status_code=500,
                        detail=f"系统设置的激活模型「{normalized.get('name', '?')}」缺少 base_url. 请到 /aiops/config 补填.",
                    )
                if not model:
                    raise HTTPException(status_code=500, detail=f"激活模型「{normalized.get('name', '?')}」缺少 runtime_model")
                return {
                    "provider": "openai",
                    "base_url": base_url,
                    "api_key": api_key or "EMPTY",
                    "model": model,
                    "source": "agent_config",
                }
            # provider 不认识 → 落到 env fallback
    except HTTPException:
        raise
    except Exception as exc:
        # agent_config 出问题不阻塞, 尝试 env 兜底
        logger.warning("[k8s-agent] 读取 agent_config 失败, 尝试 env fallback: %s", exc)

    # Fallback: 环境变量 (兼容老配置 / Docker compose 注入)
    provider = (os.getenv("AI_PROVIDER", "") or "").strip().lower()
    model = (os.getenv("AI_MODEL", "") or "").strip()

    if not provider:
        raise HTTPException(
            status_code=500,
            detail=(
                "智能模式不可用: 未配置激活模型. "
                "请到 系统设置 → AIOps → 智能配置 (/aiops/config) 添加并激活一个模型, "
                "或在 backend/.env 设置 AI_PROVIDER + AI_MODEL"
            ),
        )

    if provider == "anthropic":
        api_key = (os.getenv("ANTHROPIC_API_KEY", "") or "").strip()
        if not api_key:
            raise HTTPException(status_code=500, detail="AI_PROVIDER=anthropic 时必须设置 ANTHROPIC_API_KEY")
        return {"provider": "anthropic", "api_key": api_key, "model": model or "claude-opus-4-7", "source": "env"}

    if provider == "openai":
        base_url = (os.getenv("AI_BASE_URL", "") or "").strip()
        api_key = (os.getenv("AI_API_KEY", "") or "EMPTY").strip()
        if not base_url:
            raise HTTPException(status_code=500, detail="AI_PROVIDER=openai 时必须设置 AI_BASE_URL")
        if not model:
            raise HTTPException(status_code=500, detail="AI_PROVIDER=openai 时必须设置 AI_MODEL")
        return {"provider": "openai", "base_url": base_url, "api_key": api_key or "EMPTY", "model": model, "source": "env"}

    raise HTTPException(status_code=500, detail=f"暂不支持的 AI_PROVIDER: {provider} (仅支持 anthropic / openai 兼容)")


def _tools_for_openai() -> list[dict]:
    """把 Anthropic 风格 (input_schema) 的 TOOLS 转成 OpenAI Function Calling 风格."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in TOOLS
    ]


async def _call_anthropic(client, model: str, system: str, messages: list[dict]) -> dict:
    """统一返回 { text, tool_calls: [{id, name, input}], stop_reason }."""
    resp = await client.messages.create(
        model=model, max_tokens=2048, system=system, tools=TOOLS, messages=messages,
    )
    text_parts: list[str] = []
    tool_calls: list[dict] = []
    assistant_content: list[dict] = []
    for block in resp.content:
        if block.type == "text":
            text_parts.append(block.text)
            assistant_content.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            tool_calls.append({"id": block.id, "name": block.name, "input": block.input})
            assistant_content.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})
    return {
        "text": "\n".join(text_parts),
        "tool_calls": tool_calls,
        "stop_reason": resp.stop_reason,
        "_assistant_content": assistant_content,   # Anthropic 续轮要回填这个
    }


async def _call_openai(client, model: str, system: str, messages: list[dict]) -> dict:
    """OpenAI 兼容: 返回相同的 { text, tool_calls, stop_reason } 格式."""
    import json as _json
    # OpenAI messages 第一条是 system
    oa_messages = [{"role": "system", "content": system}] + messages
    resp = await client.chat.completions.create(
        model=model, messages=oa_messages, tools=_tools_for_openai(),
        tool_choice="auto", max_tokens=2048,
    )
    choice = resp.choices[0]
    msg = choice.message
    text = msg.content or ""
    tool_calls: list[dict] = []
    for tc in (msg.tool_calls or []):
        try:
            inp = _json.loads(tc.function.arguments) if tc.function.arguments else {}
        except Exception:
            inp = {}
        tool_calls.append({"id": tc.id, "name": tc.function.name, "input": inp})
    return {
        "text": text,
        "tool_calls": tool_calls,
        "stop_reason": choice.finish_reason,   # 'tool_calls' / 'stop' / 'length'
        "_oa_assistant": {
            "role": "assistant",
            "content": text,
            "tool_calls": [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in (msg.tool_calls or [])
            ],
        },
    }


@router.post("/ai-chat")
async def k8s_ai_chat(body: K8sAgentChatPayload, user: User = Depends(require_admin)):
    """Phase 1: tool_use loop, max 5 轮, 同步返回. 支持 Anthropic 和 OpenAI 兼容 provider."""
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="message 不能为空")

    cfg = _get_llm_config()   # 拿 provider 配置, 缺失抛 user-friendly 错

    # 初始化 client
    if cfg["provider"] == "anthropic":
        try:
            import anthropic
        except ImportError:
            raise HTTPException(status_code=500, detail="anthropic SDK 未安装")
        client = anthropic.AsyncAnthropic(api_key=cfg["api_key"])
    else:
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise HTTPException(status_code=500, detail="openai SDK 未安装")
        client = AsyncOpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"])

    cluster = _resolve_cluster_for_user(user, body.cluster_id or None)
    cid = cluster["id"]

    initial_user_msg = (
        f"[集群上下文: {cluster.get('name', cid)}, 默认 namespace={body.namespace or 'default'}]\n\n"
        f"{body.message}"
    )
    messages: list[dict] = [{"role": "user", "content": initial_user_msg}]

    history: list[dict] = []
    final_text = ""
    pending_actions: list[dict] = []
    max_rounds = 5

    for _ in range(max_rounds):
        try:
            if cfg["provider"] == "anthropic":
                result = await _call_anthropic(client, cfg["model"], SYSTEM_PROMPT, messages)
            else:
                result = await _call_openai(client, cfg["model"], SYSTEM_PROMPT, messages)
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("[k8s-agent] LLM call failed (provider=%s): %s", cfg["provider"], exc, exc_info=True)
            raise HTTPException(status_code=502, detail=f"{cfg['provider']} 调用失败: {exc}")

        text = result["text"]
        tool_calls = result["tool_calls"]

        if text:
            history.append({"type": "assistant_text", "content": text})
            final_text = text

        if not tool_calls:
            break

        # 把 assistant 回复回填到 messages
        if cfg["provider"] == "anthropic":
            messages.append({"role": "assistant", "content": result["_assistant_content"]})
        else:
            messages.append(result["_oa_assistant"])

        # 分流: 只读直接执行, 写收集 pending
        tool_results_for_anthropic: list[dict] = []
        for tu in tool_calls:
            if tu["name"] in MUTATION_TOOLS:
                pending = {
                    "tool_use_id": tu["id"],
                    "name": tu["name"],
                    "input": tu["input"],
                    "cluster_id": cid,
                }
                # ConfigMap 更新: 预读 before, 计算 key 级 diff, 注入 preview 让前端高亮
                if tu["name"] == "k8s_update_configmap":
                    try:
                        cm_name = (tu["input"].get("name") or "").strip()
                        cm_ns = (tu["input"].get("namespace") or "").strip()
                        if cm_name and cm_ns:
                            v1, _ = _get_client(cid)
                            cm_obj = v1.read_namespaced_config_map(name=cm_name, namespace=cm_ns)
                            before = dict(cm_obj.data or {})
                        else:
                            before = {}
                    except Exception as exc:
                        # 读不到 (新建场景或权限不足) 不阻塞, 把 before 当空字典
                        logger.info("[k8s-agent] read_configmap for diff preview failed: %s", exc)
                        before = {}
                    new_data = dict(tu["input"].get("data") or {})
                    merge_flag = tu["input"].get("merge", True)
                    after = {**before, **new_data} if merge_flag else dict(new_data)
                    pending["preview"] = {
                        "type": "configmap_diff",
                        "before": before,
                        "after": after,
                        "merge": bool(merge_flag),
                        "added":   [k for k in after if k not in before],
                        "removed": [k for k in before if k not in after],
                        "changed": [k for k in after if k in before and before[k] != after[k]],
                    }
                pending_actions.append(pending)
                placeholder = (
                    f"[PENDING_APPROVAL] 此写操作 ({tu['name']}) 已提交用户审批, "
                    f"用户决定后才会执行. 请不要重试, 等待用户操作."
                )
                history.append({
                    "type": "pending_action",
                    "name": tu["name"], "input": tu["input"], "result": placeholder,
                    "preview": pending.get("preview"),
                })
                result_text = placeholder
            else:
                result_text = _tool_handler(cid, tu["name"], tu["input"])
                history.append({
                    "type": "tool_use",
                    "name": tu["name"], "input": tu["input"], "result": result_text,
                })

            if cfg["provider"] == "anthropic":
                tool_results_for_anthropic.append({
                    "type": "tool_result", "tool_use_id": tu["id"], "content": result_text,
                })
            else:
                # OpenAI: 每个 tool result 是一条独立 message
                messages.append({
                    "role": "tool", "tool_call_id": tu["id"], "content": result_text,
                })

        if cfg["provider"] == "anthropic":
            messages.append({"role": "user", "content": tool_results_for_anthropic})

        if pending_actions:
            break

        # OpenAI: stop_reason='stop' 也退出; Anthropic: != 'tool_use' 退出
        if cfg["provider"] == "anthropic" and result["stop_reason"] != "tool_use":
            break
        if cfg["provider"] == "openai" and result["stop_reason"] not in ("tool_calls", None):
            break
    else:
        history.append({"type": "warning", "content": f"已达 {max_rounds} 轮工具调用上限, 强制结束"})

    return {
        "ok": True,
        "final_text": final_text,
        "history": history,
        "pending_actions": pending_actions,
        "provider": cfg["provider"],
        "model": cfg["model"],
        "config_source": cfg.get("source", "env"),   # 'agent_config' | 'env'
    }


# ── Approve 端点 (用户在 UI 上确认每一个 pending action 后调用) ────────────

class K8sAgentApprovePayload(BaseModel):
    pending_action: dict   # { name, input, cluster_id, tool_use_id }
    approve: bool          # True=执行, False=拒绝


@router.post("/ai-chat/approve")
async def k8s_ai_chat_approve(body: K8sAgentApprovePayload, user: User = Depends(require_admin)):
    """用户在 UI 上对单个 pending action 做最终决定."""
    name = body.pending_action.get("name", "")
    inp = body.pending_action.get("input", {})
    cluster_id = body.pending_action.get("cluster_id", "")
    if not name or not cluster_id:
        raise HTTPException(status_code=400, detail="pending_action 字段不完整")
    if name not in MUTATION_TOOLS:
        raise HTTPException(status_code=400, detail=f"非可审批操作: {name}")

    # 二次校验集群可访问
    _resolve_cluster_for_user(user, cluster_id)

    if not body.approve:
        return {
            "ok": True,
            "approved": False,
            "tool_name": name,
            "result": f"用户拒绝执行 {name}({inp})",
        }

    # 真正执行
    result = _tool_handler(cluster_id, name, inp)
    failed = result.startswith("✗")
    logger.info("[k8s-agent] approved %s on cluster=%s result=%s", name, cluster_id, "OK" if not failed else "FAILED")
    return {
        "ok": not failed,
        "approved": True,
        "tool_name": name,
        "input": inp,
        "result": result,
    }
