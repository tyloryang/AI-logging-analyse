"""指标证据包（Metric Evidence Pack）构建器。

借鉴 sxdevops AIOps2.1 证据包设计（docs/AIOps2.1指标证据包设计.md）：
  - 后端模板化生成查询计划，不让模型自由生成 PromQL
  - 查询预算：单次最多 8 条 PromQL、默认 60 分钟窗口、步长 60s
  - 结果压缩为 latest / baseline / peak / trend / status / weight，
    完整时序不交给模型
  - 证据不足显式输出 gaps（无数据 ≠ 正常）

证据包结构：
{
  "summary": {planned, executed, abnormal, missing, budget, window_minutes},
  "evidence": [{name, kind, status, trend, latest, baseline, peak, unit,
                weight, detail}],
  "gaps": ["..."],
}
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_BUDGET = 8
DEFAULT_WINDOW_MINUTES = 60
_STEP_SECONDS = 60
_QUERY_TIMEOUT = 12
_TREND_RATIO = 0.15   # latest 相对 baseline 偏离 ±15% 判定趋势


def _esc(value: str) -> str:
    return str(value or "").replace("\\", "\\\\").replace('"', '\\"')


# ── 指标模板（第一阶段必查，按场景选择） ──────────────────────────────────

def host_templates(instance: str, hostname: str = "") -> list[dict]:
    """主机场景：node_exporter 四大件。

    不同 Prometheus 部署里 node_exporter 的 instance 标签既可能是 ip:9100，
    也可能是主机名（如 master01）。这里用正则同时匹配 IP、ip:port、主机名，
    避免因标签格式不一致而全部命中不到。
    """
    ip = str(instance or "").split(":")[0]
    alts = [a for a in {ip, str(instance or ""), str(hostname or "")} if a]
    pattern = "|".join(_esc(a).replace(".", r"\\.") for a in alts) or _esc(ip)
    inst_re = f'instance=~"({pattern})(:[0-9]+)?"'
    sel = f'{{{inst_re}}}'
    sel_idle = f'{{{inst_re},mode="idle"}}'
    sel_root = f'{{{inst_re},mountpoint="/"}}'
    return [
        {"name": "CPU 使用率", "unit": "%", "abnormal_over": 85,
         "query": f'100 - avg(rate(node_cpu_seconds_total{sel_idle}[5m])) * 100'},
        {"name": "内存使用率", "unit": "%", "abnormal_over": 90,
         "query": f'(1 - node_memory_MemAvailable_bytes{sel} / node_memory_MemTotal_bytes{sel}) * 100'},
        {"name": "根分区使用率", "unit": "%", "abnormal_over": 88,
         "query": f'100 - node_filesystem_avail_bytes{sel_root} / node_filesystem_size_bytes{sel_root} * 100'},
        {"name": "系统负载 load5", "unit": "", "abnormal_over": 8,
         "query": f'node_load5{sel}'},
    ]


def service_templates(service: str) -> list[dict]:
    """服务场景：RED 指标（依赖 http_server_requests，缺失自然成为 gap）。"""
    svc = _esc(service)
    sel = f'{{application=~".*{svc}.*"}}'
    sel_err = f'{{application=~".*{svc}.*",status=~"5.."}}'
    return [
        {"name": f"{service} 请求速率", "unit": "rps",
         "query": f'sum(rate(http_server_requests_seconds_count{sel}[5m]))'},
        {"name": f"{service} 5xx 错误率", "unit": "%", "abnormal_over": 1,
         "query": (f'sum(rate(http_server_requests_seconds_count{sel_err}[5m])) '
                   f'/ clamp_min(sum(rate(http_server_requests_seconds_count{sel}[5m])), 0.000001) * 100')},
        {"name": f"{service} P95 延迟", "unit": "ms", "abnormal_over": 2000,
         "query": (f'histogram_quantile(0.95, sum by (le) '
                   f'(rate(http_server_requests_seconds_bucket{sel}[5m]))) * 1000')},
    ]


def k8s_templates(pod: str = "", namespace: str = "") -> list[dict]:
    """K8s 运行态：重启/CPU/内存（依赖 kube-state-metrics / cAdvisor，缺失即 gap）。"""
    pod_sel = f'pod=~".*{_esc(pod)}.*"' if pod else 'pod!=""'
    ns_sel = f',namespace="{_esc(namespace)}"' if namespace else ""
    sel = "{" + pod_sel + ns_sel + "}"
    return [
        {"name": "Pod 重启次数(1h增量)", "unit": "次", "abnormal_over": 0,
         "query": f'sum(increase(kube_pod_container_status_restarts_total{sel}[1h]))'},
        {"name": "容器 CPU 使用", "unit": "core", "abnormal_over": 4,
         "query": f'sum(rate(container_cpu_usage_seconds_total{sel}[5m]))'},
        {"name": "容器内存使用", "unit": "MB",
         "query": f'sum(container_memory_working_set_bytes{sel}) / 1024 / 1024'},
    ]


def cluster_templates() -> list[dict]:
    """全局场景：采集目标健康。"""
    return [
        {"name": "Prometheus 采集目标 down 数", "unit": "个", "abnormal_over": 0,
         "query": "count(up == 0) or vector(0)"},
    ]


# ── 执行与压缩 ─────────────────────────────────────────────────────────────

def _summarize_series(values: list) -> dict | None:
    """时序点列表 [[ts, "v"], ...] → {latest, baseline, peak, trend}。"""
    points = []
    for item in values or []:
        try:
            v = float(item[1])
            if v == v and v not in (float("inf"), float("-inf")):
                points.append(v)
        except (TypeError, ValueError, IndexError):
            continue
    if not points:
        return None
    latest = points[-1]
    half = max(1, len(points) // 2)
    baseline = sum(points[:half]) / half
    peak = max(points)
    if baseline == 0:
        trend = "up" if latest > 0 else "flat"
    else:
        ratio = (latest - baseline) / abs(baseline)
        trend = "up" if ratio > _TREND_RATIO else ("down" if ratio < -_TREND_RATIO else "flat")
    return {"latest": latest, "baseline": baseline, "peak": peak, "trend": trend}


async def _execute_one(template: dict, start: float, end: float) -> dict:
    from state import prom

    item = {
        "name": template["name"],
        "query": template["query"],
        "unit": template.get("unit", ""),
        "status": "no_data",
        "trend": "-",
        "latest": None,
        "baseline": None,
        "peak": None,
        "weight": "weak",
        "detail": "",
    }
    try:
        result = await prom.query_range(
            template["query"], start=start, end=end,
            step=_STEP_SECONDS, timeout=_QUERY_TIMEOUT,
        )
    except Exception as exc:
        item["detail"] = f"查询失败: {str(exc)[:120]}"
        return item

    # 多序列时取 latest 最大的一条作为代表（top1，符合"少而准"）
    best = None
    for series in (result or [])[:5]:
        summary = _summarize_series(series.get("values"))
        if summary and (best is None or summary["latest"] > best["latest"]):
            best = summary
    if best is None:
        item["detail"] = "无数据"
        return item

    item.update({
        "latest": round(best["latest"], 3),
        "baseline": round(best["baseline"], 3),
        "peak": round(best["peak"], 3),
        "trend": best["trend"],
        "status": "normal",
    })
    threshold = template.get("abnormal_over")
    if threshold is not None and best["latest"] > threshold:
        item["status"] = "abnormal"
        item["weight"] = "strong"
        item["detail"] = f"当前 {item['latest']}{item['unit']} 超过阈值 {threshold}{item['unit']}"
    elif best["trend"] == "up" and best["baseline"] > 0 and best["latest"] > best["baseline"] * 2:
        item["status"] = "abnormal"
        item["weight"] = "medium"
        item["detail"] = f"较基线({item['baseline']}{item['unit']})上涨超 2 倍"
    return item


async def build_metric_evidence(
    *,
    service: str | None = None,
    instance: str | None = None,
    hostname: str | None = None,
    pod: str | None = None,
    namespace: str | None = None,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
    budget: int = DEFAULT_BUDGET,
) -> dict:
    """按场景组装查询计划并在预算内执行，返回指标证据包。"""
    templates: list[dict] = []
    if instance or hostname:
        templates += host_templates(instance or hostname or "", hostname or "")
    if service:
        templates += service_templates(service)
    if pod or namespace:
        templates += k8s_templates(pod or "", namespace or "")
    if not templates:
        templates = cluster_templates()

    planned = len(templates)
    templates = templates[:budget]

    end = time.time()
    start = end - window_minutes * 60
    results = await asyncio.gather(*[
        _execute_one(t, start, end) for t in templates
    ])

    evidence = list(results)
    abnormal = [e for e in evidence if e["status"] == "abnormal"]
    missing = [e for e in evidence if e["status"] == "no_data"]
    gaps = [f"{e['name']}: {e['detail'] or '无数据'}" for e in missing]
    if planned > budget:
        gaps.append(f"已达到查询预算（{budget} 条），{planned - budget} 条计划未执行")

    return {
        "summary": {
            "planned": planned,
            "executed": len(evidence),
            "abnormal": len(abnormal),
            "missing": len(missing),
            "budget": budget,
            "window_minutes": window_minutes,
        },
        "evidence": evidence,
        "gaps": gaps,
    }


def evidence_to_text(pack: dict) -> str:
    """证据包 → 给模型/报告的紧凑中文文本（含使用约束）。"""
    if not pack or not pack.get("evidence"):
        return ""
    s = pack.get("summary", {})
    lines = [
        f"指标证据包（计划 {s.get('planned', 0)} 条 / 执行 {s.get('executed', 0)} 条 / "
        f"异常 {s.get('abnormal', 0)} 条 / 缺失 {s.get('missing', 0)} 条，"
        f"窗口 {s.get('window_minutes', 60)} 分钟）：",
    ]
    for e in pack["evidence"]:
        if e["status"] == "no_data":
            lines.append(f"- [缺失] {e['name']}: {e['detail'] or '无数据'}")
        else:
            mark = "⚠" if e["status"] == "abnormal" else "✓"
            trend_text = {"up": "上升", "down": "下降", "flat": "平稳"}.get(e["trend"], e["trend"])
            lines.append(
                f"- [{mark}{'异常' if e['status'] == 'abnormal' else '正常'}] {e['name']}: "
                f"当前 {e['latest']}{e['unit']}，基线 {e['baseline']}{e['unit']}，"
                f"峰值 {e['peak']}{e['unit']}，趋势{trend_text}"
                + (f"（{e['detail']}）" if e["detail"] else "")
            )
    if pack.get("gaps"):
        lines.append("证据缺口：" + "；".join(pack["gaps"][:5]))
    lines.append(
        "约束：只能基于以上证据解释；无数据不代表正常；未查询的指标不得作为事实引用；"
        "证据不足时必须说明缺口。"
    )
    return "\n".join(lines)
