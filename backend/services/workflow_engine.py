"""工作流真实执行引擎（替换原模拟执行）。

按节点类型映射到平台真实能力：
  trigger/input — 记录触发信息与输入
  metrics       — Prometheus 采集 CMDB 主机指标并汇总异常
  log           — Loki 扫描最近 1 小时错误日志（按服务分布）
  check         — Prometheus up 目标健康检查
  agent         — AI 分析：把前序节点输出作为上下文交给 LLM
  approval      — 审批（当前自动通过并留痕，可扩展人工审批）
  action        — 执行处置命令：ansible / ssh 到目标主机（agent_configs.action_command）
  notify        — 飞书 webhook 推送执行摘要（FEISHU_WEBHOOK）
  report        — 汇总所有节点输出生成执行报告

执行为后台任务：逐节点更新 store 中的 task（node_results/current_node_id/logs），
前端轮询任务详情即可看到进度。节点失败则任务失败并停止后续节点。
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_NODE_TIMEOUTS = {
    "agent": 120.0,
    "action": 300.0,
    "notify": 20.0,
}
_DEFAULT_NODE_TIMEOUT = 60.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ordered_nodes(workflow: dict) -> list[dict]:
    """按 edges 链式排序节点；无法排序时按 nodes 原顺序。"""
    nodes = list(workflow.get("nodes") or [])
    edges = workflow.get("edges") or []
    if not nodes:
        return []
    next_map = {str(e.get("source")): str(e.get("target")) for e in edges}
    has_incoming = {str(e.get("target")) for e in edges}
    node_map = {str(n.get("id")): n for n in nodes}

    start = next((n for n in nodes if str(n.get("id")) not in has_incoming), None)
    if start is None:
        return nodes
    ordered, seen = [], set()
    current: dict | None = start
    while current is not None and str(current.get("id")) not in seen:
        ordered.append(current)
        seen.add(str(current.get("id")))
        current = node_map.get(next_map.get(str(current.get("id")), ""))
    # 图不连通时补上剩余节点
    ordered.extend(n for n in nodes if str(n.get("id")) not in seen)
    return ordered


def _summarize_outputs(ctx: dict, max_chars: int = 3000) -> str:
    parts = []
    for node_id, item in ctx["outputs"].items():
        label = item.get("label") or node_id
        output = str(item.get("output") or "").strip()
        if output:
            parts.append(f"【{label}】\n{output}")
    return "\n\n".join(parts)[:max_chars]


# ── 各类型节点执行器（返回输出文本；抛异常 = 节点失败） ────────────────────

async def _node_trigger(node: dict, ctx: dict) -> str:
    wf = ctx["workflow"]
    lines = [f"工作流「{wf.get('name')}」由 {ctx.get('trigger', 'manual')} 触发"]
    if ctx.get("input"):
        lines.append(f"输入：{ctx['input']}")
    if ctx.get("context"):
        lines.append(f"上下文：{ctx['context']}")
    return "\n".join(lines)


async def _node_metrics(node: dict, ctx: dict) -> str:
    from routers.observability import _get_host_metrics

    hosts = await _get_host_metrics()
    if not hosts:
        return "未获取到主机指标（Prometheus 未配置或 CMDB 为空）"
    online = [h for h in hosts if h.get("has_data")]
    offline = [h for h in hosts if not h.get("has_data")]
    issues = []
    for h in online:
        problems = []
        if (h.get("cpu") or 0) > 80:
            problems.append(f"CPU {h['cpu']:.0f}%")
        if (h.get("mem") or 0) > 85:
            problems.append(f"内存 {h['mem']:.0f}%")
        if (h.get("disk_root") or 0) > 85:
            problems.append(f"磁盘 {h['disk_root']:.0f}%")
        if problems:
            issues.append(f"{h['hostname']}({h['ip']}): {' / '.join(problems)}")
    lines = [f"在线主机 {len(online)} 台，离线/无数据 {len(offline)} 台"]
    if issues:
        lines.append("异常主机：")
        lines.extend(f"  - {item}" for item in issues[:8])
    else:
        lines.append("全部主机指标正常（CPU<80% 内存<85% 磁盘<85%）")
    top = sorted(online, key=lambda h: -(h.get("cpu") or 0))[:3]
    if top:
        lines.append("CPU Top3: " + ", ".join(
            f"{h['hostname']} {h.get('cpu') or 0:.0f}%" for h in top))
    return "\n".join(lines)


async def _node_log(node: dict, ctx: dict) -> str:
    from routers.observability import _get_loki_error_count

    total, breakdown = await _get_loki_error_count(1, raise_on_error=True)
    lines = [f"最近 1 小时错误日志共 {total} 条"]
    for item in sorted(breakdown, key=lambda x: -x["count"])[:8]:
        lines.append(f"  - {item['service']}: {item['count']} 条")
    if not breakdown:
        lines.append("无服务产生错误日志")
    return "\n".join(lines)


async def _node_check(node: dict, ctx: dict) -> str:
    from state import prom

    result = await prom.query_instant("up", timeout=10)
    up, down = 0, []
    for item in result:
        try:
            value = float(item.get("value", [0, "0"])[1])
        except Exception:
            value = 0
        labels = item.get("metric", {})
        if value >= 1:
            up += 1
        else:
            down.append(f"{labels.get('job', '?')}/{labels.get('instance', '?')}")
    lines = [f"Prometheus 采集目标：{up} up / {len(down)} down"]
    if down:
        lines.append("异常目标：" + ", ".join(down[:8]))
    return "\n".join(lines)


async def _node_agent(node: dict, ctx: dict) -> str:
    from state import analyzer

    context_text = _summarize_outputs(ctx) or "（暂无前序节点数据）"
    question = ctx.get("input") or "评估当前状态，指出风险并给出处理建议"
    prompt = (
        "你是资深 SRE。以下是运维工作流前序节点的采集结果，"
        "请给出简明分析（要点式，不超过 8 行）。\n\n"
        f"{context_text}\n\n任务：{question}"
    )
    chunks = []
    async for chunk in analyzer.provider.stream(prompt, max_tokens=800):
        chunks.append(chunk)
    text = "".join(chunks).strip()
    if not text:
        raise RuntimeError("AI 分析返回为空")
    return text


async def _node_approval(node: dict, ctx: dict) -> str:
    cfg = (ctx["workflow"].get("agent_configs") or {})
    if str(cfg.get("risk") or "").lower() in ("approval", "manual"):
        return "审批策略为人工（当前版本自动放行并留痕，人工审批待接入工单系统）"
    return "自动审批通过（未配置人工审批策略）"


async def _node_action(node: dict, ctx: dict) -> str:
    cfg = (ctx["workflow"].get("agent_configs") or {})
    node_cfg = node.get("config") or {}
    command = str(node_cfg.get("command") or cfg.get("action_command") or "").strip()
    host_group = str(node_cfg.get("host_group") or cfg.get("action_host_group") or "").strip()
    host_ids = node_cfg.get("host_ids") or cfg.get("action_host_ids") or []
    if not command:
        return "未配置处置命令（在工作流 agent_configs.action_command 配置），已跳过执行"

    from state import load_hosts_list
    all_hosts = load_hosts_list()
    if host_group:
        hosts = [h for h in all_hosts if h.get("group") == host_group]
    elif host_ids:
        hosts = [h for h in all_hosts if h.get("id") in host_ids]
    else:
        hosts = []
    if not hosts:
        return f"处置命令未执行：目标主机为空（host_group={host_group or '-'}）"

    from services import ansible_runner
    result = await ansible_runner.run_adhoc(hosts, command, timeout=240)
    lines = [f"通过 Ansible 在 {len(hosts)} 台主机执行：{command}"]
    for item in result.get("per_host", []):
        state = "✓" if item.get("rc") == 0 else "✗"
        first_line = (item.get("stdout") or item.get("error") or "").splitlines()
        lines.append(f"  {state} {item.get('hostname')}: {first_line[0] if first_line else ''}"[:200])
    return "\n".join(lines)


async def _node_notify(node: dict, ctx: dict) -> str:
    webhook = os.getenv("FEISHU_WEBHOOK", "").strip()
    summary = _summarize_outputs(ctx, max_chars=1500)
    wf_name = ctx["workflow"].get("name", "工作流")
    if not webhook:
        return "未配置 FEISHU_WEBHOOK，通知已跳过（摘要已生成）"

    import httpx
    keyword = os.getenv("FEISHU_KEYWORD", "").strip()
    prefix = f"{keyword} " if keyword else ""
    text = f"{prefix}[工作流] {wf_name} 执行播报\n{summary}"[:3000]
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(webhook, json={"msg_type": "text", "content": {"text": text}})
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if resp.status_code != 200 or data.get("code") not in (0, None):
            raise RuntimeError(f"飞书推送失败: HTTP {resp.status_code} {data}")
    return f"已推送飞书通知（{len(text)} 字）"


async def _node_report(node: dict, ctx: dict) -> str:
    wf = ctx["workflow"]
    lines = [
        f"# {wf.get('name')} 执行报告",
        f"- 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 输入：{ctx.get('input') or '-'}",
        "",
        _summarize_outputs(ctx, max_chars=4000) or "（无节点输出）",
    ]
    return "\n".join(lines)


_NODE_EXECUTORS = {
    "trigger": _node_trigger,
    "input": _node_trigger,
    "metrics": _node_metrics,
    "log": _node_log,
    "check": _node_check,
    "agent": _node_agent,
    "approval": _node_approval,
    "action": _node_action,
    "notify": _node_notify,
    "report": _node_report,
}


def _update_task(task_id: str, mutator) -> dict | None:
    """同步读-改-写 store（事件循环内无 await，天然原子）。"""
    from routers.workflows import _load_store, _save_store

    data = _load_store()
    task = next((t for t in data["tasks"] if t.get("id") == task_id), None)
    if task is None:
        return None
    mutator(task)
    _save_store(data)
    return task


async def execute_workflow_task(task_id: str, workflow: dict,
                                input_text: str = "", context: dict | None = None) -> None:
    """后台执行工作流任务，逐节点更新进度。"""
    ctx: dict[str, Any] = {
        "workflow": workflow,
        "input": input_text,
        "context": context or {},
        "trigger": workflow.get("trigger_type", "manual"),
        "outputs": {},
    }
    nodes = _ordered_nodes(workflow)
    failed = False

    for node in nodes:
        node_id = str(node.get("id"))
        node_type = str(node.get("type") or "action")
        label = node.get("label") or node_id
        executor = _NODE_EXECUTORS.get(node_type, _node_trigger)
        timeout = _NODE_TIMEOUTS.get(node_type, _DEFAULT_NODE_TIMEOUT)

        _update_task(task_id, lambda t: (
            t.update({"current_node_id": node_id}),
            t.setdefault("logs", []).append(
                {"node_id": node_id, "level": "info", "message": f"节点「{label}」开始执行", "time": _now()}),
        ))

        try:
            output = await asyncio.wait_for(executor(node, ctx), timeout=timeout)
            ctx["outputs"][node_id] = {"label": label, "output": output}
            _update_task(task_id, lambda t: (
                t["node_results"].update({node_id: {"status": "success", "output": output}}),
                t.setdefault("logs", []).append(
                    {"node_id": node_id, "level": "info",
                     "message": f"节点「{label}」完成：{output.splitlines()[0][:120] if output else 'ok'}",
                     "time": _now()}),
            ))
        except Exception as exc:
            failed = True
            error_text = f"{type(exc).__name__}: {exc}" if not isinstance(exc, asyncio.TimeoutError) \
                else f"执行超时（>{timeout:.0f}s）"
            logger.warning("[workflow] 节点 %s(%s) 失败: %s", label, node_type, error_text)
            _update_task(task_id, lambda t: (
                t["node_results"].update({node_id: {"status": "failed", "output": error_text}}),
                t.setdefault("logs", []).append(
                    {"node_id": node_id, "level": "error",
                     "message": f"节点「{label}」失败：{error_text}", "time": _now()}),
            ))
            break

    def _finish(t):
        t["status"] = "failed" if failed else "success"
        t["end_time"] = _now()
        t.setdefault("logs", []).append({
            "level": "error" if failed else "info",
            "message": "工作流执行失败，已停止后续节点" if failed else "工作流全部节点执行成功",
            "time": _now(),
        })

    _update_task(task_id, _finish)
