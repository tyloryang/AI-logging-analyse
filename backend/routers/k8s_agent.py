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
        "description": "列出 K8s 资源 (Pod / Deployment / Service / Node 等). 用于查询集群中的资源.",
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "description": "资源类型: pod/deployment/daemonset/statefulset/job/cronjob/service/node"},
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
]


def _tool_handler(cluster_id: str, tool_name: str, tool_input: dict) -> str:
    """执行单个工具调用, 返回字符串结果 (失败返回错误描述)。"""
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

        return f"未知工具: {tool_name}"

    except HTTPException as he:
        return f"✗ 工具执行失败: {he.detail}"
    except Exception as exc:
        detail = getattr(exc, "body", None) or str(exc)
        return f"✗ 工具执行异常: {detail}"


# ── Anthropic tool_use loop ────────────────────────────────────────────────

SYSTEM_PROMPT = """你是 SxDevOps AIOps 平台的 K8s 运维助手. 你的工作是帮用户完成 Kubernetes 集群操作.

可用工具 (7 个): k8s_list_resources / k8s_get_resource / k8s_scale_workload / k8s_restart_workload / k8s_delete_resource / k8s_update_image / k8s_inspect_cluster

规则:
1. 用户的自然语言指令可能模糊, 你需要先查询 (list/get/inspect) 确认目标资源再操作.
2. 高危操作 (scale/restart/delete/update_image) 执行前必须先 list/get 确认目标真的存在, 防止误操作.
3. 默认 namespace 是 default, 用户没说就用 default.
4. 给用户简洁的中文回复, 关键信息用 **粗体** 或 `代码` 突出.
5. 完成任务后用 1-2 句话总结做了什么.
6. 工具失败时尝试通过其他工具排查 (例如 list 看资源是否真的存在), 但不要无限循环.
"""


class K8sAgentChatPayload(BaseModel):
    message: str
    cluster_id: str = ""
    namespace: str = ""


@router.post("/ai-chat")
async def k8s_ai_chat(body: K8sAgentChatPayload, user: User = Depends(require_admin)):
    """Phase 1: 一次性 tool_use loop, 最多 5 轮, 同步返回最终结果 + tool calls history。"""
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="message 不能为空")

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=500, detail="未配置 ANTHROPIC_API_KEY, 智能模式不可用")

    model = os.getenv("ANTHROPIC_MODEL") or os.getenv("AI_MODEL") or "claude-opus-4-7"

    try:
        import anthropic
    except ImportError:
        raise HTTPException(status_code=500, detail="anthropic SDK 未安装")

    cluster = _resolve_cluster_for_user(user, body.cluster_id or None)
    cid = cluster["id"]

    client = anthropic.AsyncAnthropic(api_key=api_key)
    messages: list[dict] = [{
        "role": "user",
        "content": (
            f"[集群上下文: {cluster.get('name', cid)}, 默认 namespace={body.namespace or 'default'}]\n\n"
            f"{body.message}"
        ),
    }]

    history: list[dict] = []   # 记录每一步 (tool_call / tool_result)
    final_text = ""
    max_rounds = 5

    for _ in range(max_rounds):
        try:
            resp = await client.messages.create(
                model=model,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )
        except Exception as exc:
            logger.error("[k8s-agent] anthropic call failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=502, detail=f"Claude 调用失败: {exc}")

        # 收集 LLM 输出的所有 content block
        assistant_content: list[dict] = []
        tool_uses: list[dict] = []
        text_parts: list[str] = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                tool_uses.append({"id": block.id, "name": block.name, "input": block.input})
                assistant_content.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})

        if text_parts:
            history.append({"type": "assistant_text", "content": "\n".join(text_parts)})
            final_text = "\n".join(text_parts)

        # 没有 tool_use → 对话结束
        if not tool_uses:
            break

        # 执行每个 tool_use, 收集结果
        messages.append({"role": "assistant", "content": assistant_content})
        tool_results: list[dict] = []
        for tu in tool_uses:
            result_text = _tool_handler(cid, tu["name"], tu["input"])
            history.append({
                "type": "tool_use",
                "name": tu["name"],
                "input": tu["input"],
                "result": result_text,
            })
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu["id"],
                "content": result_text,
            })
        messages.append({"role": "user", "content": tool_results})

        if resp.stop_reason != "tool_use":
            break
    else:
        history.append({"type": "warning", "content": f"已达 {max_rounds} 轮工具调用上限, 强制结束"})

    return {
        "ok": True,
        "final_text": final_text,
        "history": history,
        "model": model,
    }
