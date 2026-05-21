"""Unified topology endpoints.

Knowledge topology combines a curated static graph with live context from:
- CMDB groups / hosts
- recent RCA results
- recent anomaly detections
- Loki label inventory
"""

from __future__ import annotations

import asyncio
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from cachetools import TTLCache
from fastapi import APIRouter

from services.anomaly_detector import list_anomalies
from services.rca_engine import list_rca
from state import load_groups, load_hosts_list, loki

router = APIRouter(prefix="/api/topology", tags=["topology"])

_CACHE: TTLCache = TTLCache(maxsize=4, ttl=60)
_CACHE_LOCK = asyncio.Lock()

_GROUPS = [
    {"id": "control", "label": "控制面", "color": "#38bdf8"},
    {"id": "workload", "label": "工作负载", "color": "#a78bfa"},
    {"id": "traffic", "label": "流量入口", "color": "#22c55e"},
    {"id": "config", "label": "配置与存储", "color": "#fbbf24"},
    {"id": "observe", "label": "可观测性", "color": "#14b8a6"},
    {"id": "aiops", "label": "AIOps", "color": "#f87171"},
]

_RELATIONS = [
    {"id": "operate", "label": "控制 / 调用", "color": "#38bdf8"},
    {"id": "manage", "label": "编排 / 管理", "color": "#a78bfa"},
    {"id": "route", "label": "路由 / 选择", "color": "#22c55e"},
    {"id": "inject", "label": "注入 / 挂载", "color": "#fbbf24"},
    {"id": "observe", "label": "采集 / 观测", "color": "#14b8a6"},
    {"id": "analyze", "label": "关联 / 根因", "color": "#f87171"},
]

_ZONES = [
    {"id": "control", "label": "Control Plane", "x": 30, "y": 40, "w": 420, "h": 250, "color": "#38bdf8"},
    {"id": "workload", "label": "Workloads", "x": 30, "y": 330, "w": 420, "h": 300, "color": "#a78bfa"},
    {"id": "traffic", "label": "Traffic & Service", "x": 480, "y": 40, "w": 430, "h": 250, "color": "#22c55e"},
    {"id": "config", "label": "Config & Storage", "x": 480, "y": 330, "w": 430, "h": 300, "color": "#fbbf24"},
    {"id": "observe", "label": "Observability", "x": 940, "y": 40, "w": 500, "h": 320, "color": "#14b8a6"},
    {"id": "aiops", "label": "AIOps Correlation", "x": 940, "y": 390, "w": 500, "h": 430, "color": "#f87171"},
]

_STATIC_NODES = [
    {
        "id": "kubectl",
        "name": "kubectl",
        "subtitle": "CLI / GitOps",
        "abbr": "CLI",
        "group": "control",
        "zone": "control",
        "x": 110,
        "y": 140,
        "size": 28,
        "summary": [
            "运维和发布入口，负责提交与查询集群状态。",
            "统一通过 API Server 与 Kubernetes 控制面交互。",
        ],
        "metadata": {"kind": "client", "scope": "k8s"},
    },
    {
        "id": "api_server",
        "name": "API Server",
        "subtitle": "REST / Watch",
        "abbr": "API",
        "group": "control",
        "zone": "control",
        "x": 235,
        "y": 140,
        "size": 34,
        "summary": [
            "Kubernetes 控制面的统一入口。",
            "负责认证、授权、资源读写和 watch 事件分发。",
        ],
        "metadata": {"kind": "control-plane", "scope": "k8s"},
    },
    {
        "id": "controller",
        "name": "Controller",
        "subtitle": "Reconcile Loop",
        "abbr": "CTL",
        "group": "control",
        "zone": "control",
        "x": 360,
        "y": 140,
        "size": 30,
        "summary": [
            "持续比较期望状态与实际状态。",
            "驱动 Deployment、Job 等资源向目标状态收敛。",
        ],
        "metadata": {"kind": "controller-manager", "scope": "k8s"},
    },
    {
        "id": "deployment",
        "name": "Deployment",
        "subtitle": "Stateless App",
        "abbr": "DEP",
        "group": "workload",
        "zone": "workload",
        "x": 120,
        "y": 430,
        "size": 30,
        "summary": [
            "声明式管理无状态应用副本和滚动升级。",
            "是多数业务微服务的上层控制对象。",
        ],
        "metadata": {"kind": "workload", "scope": "k8s"},
    },
    {
        "id": "pod",
        "name": "Pod",
        "subtitle": "Runtime Unit",
        "abbr": "POD",
        "group": "workload",
        "zone": "workload",
        "x": 240,
        "y": 535,
        "size": 36,
        "summary": [
            "容器运行的最小调度单元。",
            "日志、指标和链路数据都从 Pod 或其容器产生。",
        ],
        "metadata": {"kind": "workload", "scope": "k8s"},
    },
    {
        "id": "cronjob",
        "name": "CronJob",
        "subtitle": "Batch / Schedule",
        "abbr": "JOB",
        "group": "workload",
        "zone": "workload",
        "x": 360,
        "y": 430,
        "size": 28,
        "summary": [
            "用于批处理、巡检和定时任务。",
            "在 AIOps 场景里可承载修复脚本或巡检作业。",
        ],
        "metadata": {"kind": "batch", "scope": "k8s"},
    },
    {
        "id": "ingress",
        "name": "Ingress",
        "subtitle": "North-South",
        "abbr": "ING",
        "group": "traffic",
        "zone": "traffic",
        "x": 605,
        "y": 130,
        "size": 30,
        "summary": [
            "承载域名、路径和 TLS 入口规则。",
            "把外部请求转发到 Service。",
        ],
        "metadata": {"kind": "network", "scope": "k8s"},
    },
    {
        "id": "service",
        "name": "Service",
        "subtitle": "Stable Endpoint",
        "abbr": "SVC",
        "group": "traffic",
        "zone": "traffic",
        "x": 755,
        "y": 130,
        "size": 32,
        "summary": [
            "为 Pod 提供稳定的访问地址。",
            "通过 label selector 选择后端实例。",
        ],
        "metadata": {"kind": "network", "scope": "k8s"},
    },
    {
        "id": "network_policy",
        "name": "NetworkPolicy",
        "subtitle": "East-West",
        "abbr": "NET",
        "group": "traffic",
        "zone": "traffic",
        "x": 605,
        "y": 245,
        "size": 28,
        "summary": [
            "定义 Pod 间允许的网络访问边界。",
            "用于限制跨服务调用面和横向移动风险。",
        ],
        "metadata": {"kind": "network", "scope": "k8s"},
    },
    {
        "id": "configmap",
        "name": "ConfigMap",
        "subtitle": "Config Data",
        "abbr": "CFG",
        "group": "config",
        "zone": "config",
        "x": 605,
        "y": 440,
        "size": 28,
        "summary": [
            "保存普通配置项。",
            "常通过环境变量或挂载卷注入业务 Pod。",
        ],
        "metadata": {"kind": "config", "scope": "k8s"},
    },
    {
        "id": "secret",
        "name": "Secret",
        "subtitle": "Credential",
        "abbr": "SEC",
        "group": "config",
        "zone": "config",
        "x": 755,
        "y": 440,
        "size": 28,
        "summary": [
            "保存密码、Token、证书等敏感配置。",
            "通常与数据库、消息队列、第三方 API 访问绑定。",
        ],
        "metadata": {"kind": "secret", "scope": "k8s"},
    },
    {
        "id": "pvc",
        "name": "PVC",
        "subtitle": "Persistent Volume",
        "abbr": "PVC",
        "group": "config",
        "zone": "config",
        "x": 860,
        "y": 440,
        "size": 26,
        "summary": [
            "为 Pod 提供持久化存储声明。",
            "日志缓存、任务状态或数据文件可通过 PVC 保存。",
        ],
        "metadata": {"kind": "storage", "scope": "k8s"},
    },
    {
        "id": "loki",
        "name": "Loki",
        "subtitle": "Logs",
        "abbr": "LOG",
        "group": "observe",
        "zone": "observe",
        "x": 1080,
        "y": 120,
        "size": 30,
        "summary": [
            "采集和查询日志流。",
            "为异常检测、日志模板聚合和根因分析提供原始证据。",
        ],
        "metadata": {"kind": "observability", "scope": "platform"},
    },
    {
        "id": "prometheus",
        "name": "Prometheus",
        "subtitle": "Metrics",
        "abbr": "MET",
        "group": "observe",
        "zone": "observe",
        "x": 1220,
        "y": 120,
        "size": 30,
        "summary": [
            "抓取业务和集群指标。",
            "告警规则与容量趋势判断依赖 Prometheus 指标数据。",
        ],
        "metadata": {"kind": "observability", "scope": "platform"},
    },
    {
        "id": "skywalking",
        "name": "SkyWalking",
        "subtitle": "Trace / APM",
        "abbr": "APM",
        "group": "observe",
        "zone": "observe",
        "x": 1360,
        "y": 120,
        "size": 30,
        "summary": [
            "采集微服务调用链与性能拓扑。",
            "用于定位慢调用、跨服务依赖和运行时真实调用关系。",
        ],
        "metadata": {"kind": "observability", "scope": "platform"},
    },
    {
        "id": "alertmanager",
        "name": "AlertManager",
        "subtitle": "Alert Routing",
        "abbr": "ALT",
        "group": "observe",
        "zone": "observe",
        "x": 1220,
        "y": 240,
        "size": 30,
        "summary": [
            "承接 Prometheus 告警并做分组、路由、抑制。",
            "可通过 webhook 把告警推送到本平台。",
        ],
        "metadata": {"kind": "observability", "scope": "platform"},
    },
    {
        "id": "grafana",
        "name": "Grafana",
        "subtitle": "Dashboard",
        "abbr": "GRF",
        "group": "observe",
        "zone": "observe",
        "x": 1360,
        "y": 240,
        "size": 30,
        "summary": [
            "负责可视化看板和排障联动入口。",
            "日志与指标查询通常通过 Grafana 面板联动展示。",
        ],
        "metadata": {"kind": "observability", "scope": "platform"},
    },
    {
        "id": "cmdb",
        "name": "CMDB",
        "subtitle": "Asset Context",
        "abbr": "CMD",
        "group": "aiops",
        "zone": "aiops",
        "x": 1080,
        "y": 460,
        "size": 30,
        "summary": [
            "保存主机、凭证、分组和环境资产信息。",
            "用于把运行异常映射到资产责任域。",
        ],
        "metadata": {"kind": "cmdb", "scope": "platform"},
    },
    {
        "id": "rca",
        "name": "RCA Engine",
        "subtitle": "Correlation",
        "abbr": "RCA",
        "group": "aiops",
        "zone": "aiops",
        "x": 1220,
        "y": 460,
        "size": 34,
        "summary": [
            "聚合日志、指标、链路、告警和资产上下文。",
            "输出根因候选、处置建议和排障证据链。",
        ],
        "metadata": {"kind": "aiops", "scope": "platform"},
    },
    {
        "id": "assistant",
        "name": "AIOps Assistant",
        "subtitle": "Copilot",
        "abbr": "AI",
        "group": "aiops",
        "zone": "aiops",
        "x": 1360,
        "y": 460,
        "size": 32,
        "summary": [
            "将根因、技能工具和工作目录编排为可执行对话。",
            "面向用户输出诊断结论、命令建议与后续操作。",
        ],
        "metadata": {"kind": "assistant", "scope": "platform"},
    },
]

_STATIC_EDGES = [
    {"id": "kubectl-api", "source": "kubectl", "target": "api_server", "relation": "operate", "label": "apply / get", "category": "operate"},
    {"id": "api-controller", "source": "api_server", "target": "controller", "relation": "watch", "label": "watch events", "category": "operate", "bend": 0.08},
    {"id": "controller-deploy", "source": "controller", "target": "deployment", "relation": "reconcile", "label": "reconcile", "category": "manage", "bend": 0.16},
    {"id": "deploy-pod", "source": "deployment", "target": "pod", "relation": "manage", "label": "manages", "category": "manage"},
    {"id": "cronjob-pod", "source": "cronjob", "target": "pod", "relation": "create", "label": "creates", "category": "manage", "bend": -0.18, "style": "dash"},
    {"id": "ingress-service", "source": "ingress", "target": "service", "relation": "route", "label": "routes_to", "category": "route"},
    {"id": "service-pod", "source": "service", "target": "pod", "relation": "select", "label": "selects", "category": "route", "bend": 0.07},
    {"id": "policy-pod", "source": "network_policy", "target": "pod", "relation": "restrict", "label": "restricts", "category": "route", "bend": -0.08, "style": "dash"},
    {"id": "configmap-pod", "source": "configmap", "target": "pod", "relation": "inject", "label": "injects", "category": "inject", "bend": -0.08},
    {"id": "secret-pod", "source": "secret", "target": "pod", "relation": "mount", "label": "mounts", "category": "inject", "bend": 0.04},
    {"id": "pvc-pod", "source": "pvc", "target": "pod", "relation": "persist", "label": "persists", "category": "inject", "bend": 0.14},
    {"id": "pod-loki", "source": "pod", "target": "loki", "relation": "observe", "label": "emits logs", "category": "observe", "bend": 0.06},
    {"id": "pod-prometheus", "source": "pod", "target": "prometheus", "relation": "observe", "label": "exports metrics", "category": "observe", "bend": -0.01},
    {"id": "pod-skywalking", "source": "pod", "target": "skywalking", "relation": "observe", "label": "reports traces", "category": "observe", "bend": -0.08},
    {"id": "prom-alert", "source": "prometheus", "target": "alertmanager", "relation": "alert", "label": "fires alerts", "category": "observe"},
    {"id": "prom-grafana", "source": "prometheus", "target": "grafana", "relation": "datasource", "label": "metrics datasource", "category": "observe", "bend": -0.06},
    {"id": "loki-grafana", "source": "loki", "target": "grafana", "relation": "datasource", "label": "logs datasource", "category": "observe", "bend": 0.03},
    {"id": "alert-rca", "source": "alertmanager", "target": "rca", "relation": "trigger", "label": "triggers", "category": "analyze"},
    {"id": "loki-rca", "source": "loki", "target": "rca", "relation": "correlate", "label": "correlates logs", "category": "analyze", "bend": 0.18},
    {"id": "sw-rca", "source": "skywalking", "target": "rca", "relation": "correlate", "label": "correlates traces", "category": "analyze", "bend": -0.18},
    {"id": "cmdb-rca", "source": "cmdb", "target": "rca", "relation": "enrich", "label": "enriches context", "category": "analyze"},
    {"id": "rca-assistant", "source": "rca", "target": "assistant", "relation": "assist", "label": "generates diagnosis", "category": "analyze"},
]

_SEVERITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "critical": 0, "warning": 1}


def _copy_base_graph() -> dict[str, Any]:
    return {
        "graph_id": "knowledge-aiops-k8s",
        "title": "知识拓扑图",
        "subtitle": "K8s 资源、可观测性与 AIOps 根因关系",
        "source": "knowledge",
        "groups": deepcopy(_GROUPS),
        "relation_legend": deepcopy(_RELATIONS),
        "zones": deepcopy(_ZONES),
        "nodes": deepcopy(_STATIC_NODES),
        "edges": deepcopy(_STATIC_EDGES),
        "stats": {"groups": len(_GROUPS), "zones": len(_ZONES)},
    }


def _safe_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _short_text(value: Any, limit: int = 72) -> str:
    text = _safe_text(value)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_dt(value: Any) -> str:
    parsed = _parse_iso(value)
    if not parsed:
        return ""
    return parsed.astimezone(timezone.utc).strftime("%m-%d %H:%M UTC")


def _extract_rca_summary(result: str) -> str:
    text = str(result or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""

    heading = re.search(r"^##\s*根因摘要\s*$\n+([\s\S]*?)(?=^##\s+|\Z)", text, flags=re.MULTILINE)
    if heading:
        lines = []
        for raw in heading.group(1).splitlines():
            clean = re.sub(r"^\s*[-*]\s*", "", raw)
            clean = re.sub(r"^\s*\d+\.\s*", "", clean)
            clean = clean.replace("**", "").replace("__", "")
            clean = " ".join(clean.split()).strip()
            if clean:
                lines.append(clean)
        if lines:
            return _short_text(" ".join(lines[:2]), 140)

    plain = []
    for raw in text.splitlines():
        line = _safe_text(raw.replace("**", "").replace("__", ""))
        if not line or line.startswith("##"):
            continue
        plain.append(line)
        if len(plain) >= 2:
            break
    return _short_text(" ".join(plain), 140)


async def _load_label_inventory() -> dict[str, Any]:
    try:
        return await loki.get_label_inventory()
    except Exception:
        return {}


def _build_label_nodes(label_inventory: dict[str, Any]) -> tuple[list[dict], list[dict], int]:
    items = label_inventory.get("data") if isinstance(label_inventory, dict) else []
    if not isinstance(items, list) or not items:
        return [], [], 0

    service_label = _safe_text(label_inventory.get("service_label"))
    default_group = _safe_text(label_inventory.get("default_group_by"))
    group_options = label_inventory.get("group_options") if isinstance(label_inventory, dict) else []
    if not isinstance(group_options, list):
        group_options = []

    chosen: list[str] = []
    for label in (service_label, default_group):
        if label and label not in chosen:
            chosen.append(label)
    for option in group_options:
        label = _safe_text(option.get("value"))
        if label and label not in chosen:
            chosen.append(label)
        if len(chosen) >= 3:
            break

    item_map = {str(item.get("name")): item for item in items if isinstance(item, dict)}
    total_labels = len(items)
    nodes: list[dict] = []
    edges: list[dict] = []
    positions = [(1045, 320), (1215, 320), (1380, 320)]

    for index, label in enumerate(chosen[:3]):
        item = item_map.get(label, {})
        role = _safe_text(item.get("role")) or "generic"
        groupable = bool(item.get("groupable"))
        node_id = f"loki_label_{label.replace('-', '_')}"
        nodes.append(
            {
                "id": node_id,
                "name": label,
                "subtitle": f"Loki label / {role}",
                "abbr": label[:4].upper(),
                "group": "observe",
                "zone": "observe",
                "x": positions[index][0],
                "y": positions[index][1],
                "size": 22,
                "summary": [
                    f"标签角色: {role}",
                    "可作为分组标签" if groupable else "通常用于过滤和定位",
                    f"Loki 当前共发现 {total_labels} 个标签",
                ],
                "metadata": {"kind": "loki-label", "scope": "logs"},
            }
        )
        edges.extend(
            [
                {
                    "id": f"loki-to-{node_id}",
                    "source": "loki",
                    "target": node_id,
                    "relation": "index",
                    "label": "indexes",
                    "category": "observe",
                    "bend": -0.05 + index * 0.04,
                },
                {
                    "id": f"{node_id}-to-rca",
                    "source": node_id,
                    "target": "rca",
                    "relation": "filter",
                    "label": "filters",
                    "category": "analyze",
                    "bend": 0.08 - index * 0.04,
                    "style": "dash",
                },
            ]
        )

    return nodes, edges, total_labels


def _build_cmdb_nodes() -> tuple[list[dict], list[dict], int, int]:
    groups = load_groups()
    hosts = load_hosts_list()
    group_name_map = {
        str(group.get("id") or "").strip(): _safe_text(group.get("name")) or str(group.get("id") or "").strip()
        for group in groups
        if str(group.get("id") or "").strip()
    }

    grouped: dict[str, dict[str, Any]] = {}
    for host in hosts:
        gid = _safe_text(host.get("group"))
        if not gid:
            continue
        item = grouped.setdefault(
            gid,
            {
                "count": 0,
                "envs": {},
                "roles": {},
                "owners": {},
            },
        )
        item["count"] += 1
        for key, field in (("envs", "env"), ("roles", "role"), ("owners", "owner")):
            value = _safe_text(host.get(field))
            if value:
                item[key][value] = item[key].get(value, 0) + 1

    top_groups = sorted(
        grouped.items(),
        key=lambda item: (-int(item[1]["count"]), group_name_map.get(item[0], item[0])),
    )[:3]

    nodes: list[dict] = []
    edges: list[dict] = []
    for index, (gid, info) in enumerate(top_groups):
        x = 1060
        y = 590 + index * 95
        env_top = next(iter(sorted(info["envs"].items(), key=lambda item: (-item[1], item[0]))), None)
        role_top = next(iter(sorted(info["roles"].items(), key=lambda item: (-item[1], item[0]))), None)
        owner_top = next(iter(sorted(info["owners"].items(), key=lambda item: (-item[1], item[0]))), None)
        name = group_name_map.get(gid, gid)
        node_id = f"cmdb_group_{gid.replace('-', '_')}"
        summary = [f"CMDB 分组 ID: {gid}", f"共 {info['count']} 台主机"]
        if env_top:
            summary.append(f"主要环境: {env_top[0]} ({env_top[1]})")
        if role_top:
            summary.append(f"主要角色: {role_top[0]} ({role_top[1]})")
        if owner_top:
            summary.append(f"负责人最多: {owner_top[0]} ({owner_top[1]})")
        nodes.append(
            {
                "id": node_id,
                "name": name,
                "subtitle": f"{info['count']} hosts",
                "abbr": f"G{index + 1}",
                "group": "aiops",
                "zone": "aiops",
                "x": x,
                "y": y,
                "size": 24,
                "summary": summary[:5],
                "metadata": {"kind": "cmdb-group", "scope": "asset"},
            }
        )
        edges.extend(
            [
                {
                    "id": f"cmdb-to-{node_id}",
                    "source": "cmdb",
                    "target": node_id,
                    "relation": "contains",
                    "label": "contains",
                    "category": "manage",
                    "bend": -0.06 + index * 0.03,
                },
                {
                    "id": f"{node_id}-to-rca",
                    "source": node_id,
                    "target": "rca",
                    "relation": "context",
                    "label": "asset context",
                    "category": "analyze",
                    "bend": 0.04 + index * 0.03,
                },
            ]
        )

    return nodes, edges, len(groups), len(hosts)


def _build_recent_rca_nodes() -> tuple[list[dict], list[dict], int]:
    records = list_rca(12)
    selected: list[dict] = []
    seen = set()
    for record in records:
        service = _safe_text(record.get("service")) or "global"
        alert_name = _safe_text(record.get("alert_name"))
        key = (service, alert_name)
        if key in seen:
            continue
        seen.add(key)
        selected.append(record)
        if len(selected) >= 2:
            break

    nodes: list[dict] = []
    edges: list[dict] = []
    for index, record in enumerate(selected):
        node_id = f"rca_case_{index + 1}"
        service = _safe_text(record.get("service")) or "global"
        alert_name = _safe_text(record.get("alert_name")) or "manual RCA"
        created_at = _format_dt(record.get("created_at"))
        summary = _extract_rca_summary(record.get("result") or "")
        lines = [
            f"服务: {service}",
            f"告警: {_short_text(alert_name, 48)}",
        ]
        if created_at:
            lines.append(f"时间: {created_at}")
        if summary:
            lines.append(summary)
        nodes.append(
            {
                "id": node_id,
                "name": _short_text(service, 32),
                "subtitle": _short_text(alert_name, 32),
                "abbr": f"R{index + 1}",
                "group": "aiops",
                "zone": "aiops",
                "x": 1220,
                "y": 610 + index * 110,
                "size": 24,
                "summary": lines[:5],
                "metadata": {"kind": "rca-case", "scope": "incident"},
            }
        )
        edges.extend(
            [
                {
                    "id": f"rca-to-{node_id}",
                    "source": "rca",
                    "target": node_id,
                    "relation": "records",
                    "label": "recent case",
                    "category": "analyze",
                },
                {
                    "id": f"{node_id}-to-assistant",
                    "source": node_id,
                    "target": "assistant",
                    "relation": "advise",
                    "label": "actionable output",
                    "category": "analyze",
                    "bend": 0.05 if index == 0 else -0.05,
                    "style": "dash",
                },
            ]
        )

    return nodes, edges, len(records)


def _build_anomaly_nodes() -> tuple[list[dict], list[dict], int]:
    anomalies = list_anomalies(20)
    selected = sorted(
        anomalies[:8],
        key=lambda item: (
            _SEVERITY_RANK.get(_safe_text(item.get("severity")), 9),
            -int(_parse_iso(item.get("detected_at")).timestamp()) if _parse_iso(item.get("detected_at")) else 0,
        ),
    )[:2]

    nodes: list[dict] = []
    edges: list[dict] = []
    for index, anomaly in enumerate(selected):
        severity = _safe_text(anomaly.get("severity")) or "P2"
        detail = _short_text(anomaly.get("detail"), 120)
        detected_at = _format_dt(anomaly.get("detected_at"))
        node_id = f"anomaly_{index + 1}"
        lines = [
            f"严重级别: {severity}",
            f"数值: {anomaly.get('value', '-')}{_safe_text(anomaly.get('unit'))}",
        ]
        if detected_at:
            lines.append(f"时间: {detected_at}")
        if detail:
            lines.append(detail)
        nodes.append(
            {
                "id": node_id,
                "name": _short_text(anomaly.get("name") or f"Anomaly {index + 1}", 34),
                "subtitle": severity,
                "abbr": severity,
                "group": "aiops",
                "zone": "aiops",
                "x": 1370,
                "y": 610 + index * 110,
                "size": 22,
                "summary": lines[:5],
                "metadata": {"kind": "anomaly", "scope": "detection"},
            }
        )
        edges.extend(
            [
                {
                    "id": f"alert-to-{node_id}",
                    "source": "alertmanager",
                    "target": node_id,
                    "relation": "surface",
                    "label": "surfaces",
                    "category": "observe",
                    "bend": 0.07 if index == 0 else -0.04,
                },
                {
                    "id": f"{node_id}-to-rca",
                    "source": node_id,
                    "target": "rca",
                    "relation": "triggers",
                    "label": "triggers RCA",
                    "category": "analyze",
                    "bend": -0.06 if index == 0 else 0.06,
                },
            ]
        )

    return nodes, edges, len(anomalies)


async def _build_knowledge_graph() -> dict[str, Any]:
    payload = _copy_base_graph()

    label_inventory, cmdb_part, rca_part, anomaly_part = await asyncio.gather(
        _load_label_inventory(),
        asyncio.to_thread(_build_cmdb_nodes),
        asyncio.to_thread(_build_recent_rca_nodes),
        asyncio.to_thread(_build_anomaly_nodes),
    )

    label_nodes, label_edges, total_labels = _build_label_nodes(label_inventory)
    cmdb_nodes, cmdb_edges, total_groups, total_hosts = cmdb_part
    rca_nodes, rca_edges, total_rca = rca_part
    anomaly_nodes, anomaly_edges, total_anomalies = anomaly_part

    payload["nodes"].extend(label_nodes)
    payload["nodes"].extend(cmdb_nodes)
    payload["nodes"].extend(rca_nodes)
    payload["nodes"].extend(anomaly_nodes)

    payload["edges"].extend(label_edges)
    payload["edges"].extend(cmdb_edges)
    payload["edges"].extend(rca_edges)
    payload["edges"].extend(anomaly_edges)

    payload["stats"].update(
        {
            "nodes": len(payload["nodes"]),
            "edges": len(payload["edges"]),
            "details": [
                {"label": "CMDB 主机", "value": total_hosts},
                {"label": "Loki 标签", "value": total_labels},
                {"label": "RCA 历史", "value": total_rca},
                {"label": "异常记录", "value": total_anomalies},
            ],
            "sources": {
                "cmdb_groups": total_groups,
                "cmdb_hosts": total_hosts,
                "loki_labels": total_labels,
                "rca_records": total_rca,
                "anomalies": total_anomalies,
            },
        }
    )

    return payload


@router.get("/knowledge")
async def get_knowledge_topology():
    cached = _CACHE.get("knowledge")
    # 只返回非空缓存，避免缓存住空结果
    if cached is not None and cached.get("nodes"):
        return cached

    async with _CACHE_LOCK:
        cached = _CACHE.get("knowledge")
        if cached is not None and cached.get("nodes"):
            return cached
        try:
            payload = await _build_knowledge_graph()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("[topology] build failed: %s", exc, exc_info=True)
            raise
        _CACHE["knowledge"] = payload
        return payload
