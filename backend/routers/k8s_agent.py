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


# ── 安全边界: 写工具集合 (需要用户二次审批才执行) ────────────────────────────
MUTATION_TOOLS: set[str] = {
    "k8s_scale_workload",
    "k8s_restart_workload",
    "k8s_delete_resource",
    "k8s_update_image",
}
# 只读工具 (可直接执行, 不影响集群状态)
READONLY_TOOLS: set[str] = {
    "k8s_list_resources",
    "k8s_get_resource",
    "k8s_inspect_cluster",
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

**重要安全边界**:
- 只读工具 (list / get / inspect): 你可以直接调用, 平台立即返回结果.
- 写工具 (scale / restart / delete / update_image): 平台**不会立即执行**, 而是收集为待审批操作, 等用户在 UI 上一对一确认后才真的下发到集群.
- 你看到写工具返回 "[PENDING_APPROVAL] ..." 时, 这表示已经提交给用户审核, 不要重试也不要尝试绕过.
- 用户拒绝某项操作后会有对应消息, 你应该尊重决定, 不要重复尝试同一操作.

规则:
1. 用户的自然语言指令可能模糊, 你需要先用只读工具 (list/get/inspect) 确认目标资源再生成写操作.
2. 默认 namespace 是 default, 用户没说就用 default.
3. 给用户简洁的中文回复, 关键信息用 **粗体** 或 `代码` 突出.
4. 一次回复里最多生成 3 个写操作待审批, 不要一口气提交一大批.
5. 完成只读查询后用 1-2 句话总结发现, 再提议下一步写操作 (如果需要).
"""


class K8sAgentChatPayload(BaseModel):
    message: str
    cluster_id: str = ""
    namespace: str = ""


# ── LLM provider 抽象 (复用 ai_analyzer 的 AI_PROVIDER/AI_MODEL/AI_BASE_URL/AI_API_KEY) ────

def _get_llm_config() -> dict:
    """从 env 拿 LLM 配置. 复用项目标准变量, 不再硬编码 ANTHROPIC_API_KEY。

    支持的 AI_PROVIDER:
      - anthropic (默认): ANTHROPIC_API_KEY + AI_MODEL
      - openai 兼容: AI_BASE_URL + AI_API_KEY + AI_MODEL
        (本地 Qwen / 通义千问 / DeepSeek / OpenRouter / Ollama 等)
    """
    provider = (os.getenv("AI_PROVIDER", "") or "").strip().lower()
    model = (os.getenv("AI_MODEL", "") or "").strip()

    if not provider:
        raise HTTPException(
            status_code=500,
            detail=(
                "未配置 AI_PROVIDER, 智能模式不可用. "
                "请在 backend/.env 设置 AI_PROVIDER=anthropic 或 openai, "
                "并配套设置 AI_MODEL + 对应 API key/base_url"
            ),
        )

    if provider == "anthropic":
        api_key = (os.getenv("ANTHROPIC_API_KEY", "") or "").strip()
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="AI_PROVIDER=anthropic 时必须设置 ANTHROPIC_API_KEY",
            )
        return {
            "provider": "anthropic",
            "api_key": api_key,
            "model": model or "claude-opus-4-7",
        }

    if provider == "openai":
        base_url = (os.getenv("AI_BASE_URL", "") or "").strip()
        api_key = (os.getenv("AI_API_KEY", "") or "EMPTY").strip()   # 本地模型可无 key
        if not base_url:
            raise HTTPException(
                status_code=500,
                detail="AI_PROVIDER=openai 时必须设置 AI_BASE_URL (本地或远程的 OpenAI 兼容端点)",
            )
        if not model:
            raise HTTPException(status_code=500, detail="AI_PROVIDER=openai 时必须设置 AI_MODEL")
        return {
            "provider": "openai",
            "base_url": base_url,
            "api_key": api_key or "EMPTY",
            "model": model,
        }

    raise HTTPException(status_code=500, detail=f"暂不支持的 AI_PROVIDER: {provider} (仅支持 anthropic / openai)")


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
                pending_actions.append(pending)
                placeholder = (
                    f"[PENDING_APPROVAL] 此写操作 ({tu['name']}) 已提交用户审批, "
                    f"用户决定后才会执行. 请不要重试, 等待用户操作."
                )
                history.append({
                    "type": "pending_action",
                    "name": tu["name"], "input": tu["input"], "result": placeholder,
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
