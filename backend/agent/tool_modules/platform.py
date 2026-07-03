"""Platform inventory and capability overview tools."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from ._shared import _allowed_groups, _filter_hosts_by_groups

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_DATA_DIR = _BACKEND_DIR / "data"


def _read_json(name: str, default: Any) -> Any:
    try:
        import json

        path = _DATA_DIR / name
        if not path.exists():
            return default
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        return data if data is not None else default
    except Exception:
        return default


def _items(data: Any) -> list[dict]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [item for item in data.values() if isinstance(item, dict)]
    return []


def _yes_no(value: Any) -> str:
    return "是" if bool(value) else "否"


def _configured(value: Any) -> str:
    return "已配置" if str(value or "").strip() else "未配置"


def _count_by(items: list[dict], field: str, default: str = "未标记") -> str:
    counter = Counter(str(item.get(field) or default).strip() or default for item in items)
    if not counter:
        return "无"
    return "，".join(f"{key}:{value}" for key, value in counter.most_common(8))


def _names(items: list[dict], field: str = "name", limit: int = 8) -> str:
    names = [str(item.get(field) or item.get("hostname") or item.get("id") or "").strip() for item in items]
    names = [name for name in names if name]
    if not names:
        return "无"
    suffix = f" 等{len(names)}个" if len(names) > limit else ""
    return "，".join(names[:limit]) + suffix


def _load_visible_k8s_clusters(config: RunnableConfig | None) -> list[dict]:
    try:
        from ._shared import _visible_k8s_clusters

        return _visible_k8s_clusters(config)
    except Exception:
        return _items(_read_json("k8s_clusters.json", []))


def _settings_section(settings: dict) -> list[str]:
    return [
        "**基础配置**",
        f"- Loki：{_configured(settings.get('loki_url'))} ({settings.get('loki_url') or '-'})",
        f"- Prometheus：{_configured(settings.get('prometheus_url'))} ({settings.get('prometheus_url') or '-'})",
        f"- Alertmanager：{_configured(settings.get('alertmanager_url'))} ({settings.get('alertmanager_url') or '-'})",
        f"- Grafana：{_configured(settings.get('grafana_url'))} ({settings.get('grafana_url') or '-'})",
        f"- SkyWalking：{_configured(settings.get('skywalking_oap_url'))} ({settings.get('skywalking_oap_url') or '-'})",
        f"- AI：provider={settings.get('ai_provider') or '-'}，model={settings.get('ai_model') or '-'}，wire={settings.get('ai_wire_api') or 'auto'}",
        f"- Agent 执行器：{settings.get('agent_executor') or 'langgraph'}",
    ]


def _capabilities_section() -> list[str]:
    return [
        "**能力地图**",
        "- 日志分析：服务列表、错误日志、最近日志、错误分布统计",
        "- 指标巡检：主机 CPU/内存/磁盘/负载，全量主机巡检",
        "- K8s 运维：集群总览、节点、Pod、命名空间、Deployment、Service 查询",
        "- 中间件：MySQL、Redis、Kafka、Elasticsearch 实例与健康状态",
        "- CI/CD：Jenkins Job、构建详情、构建日志、队列与运行中任务",
        "- 知识库：历史日报检索、相似故障案例召回",
        "- MCP：列出已启用 MCP、发现工具、调用只读或经审批的外部工具",
    ]


def _agent_section(agent_cfg: dict) -> list[str]:
    models = _items(agent_cfg.get("models", []))
    active_model = next((item for item in models if item.get("active")), None)
    mcps = _items(agent_cfg.get("mcps", []))
    enabled_mcps = [item for item in mcps if item.get("enabled")]
    skills = _items(agent_cfg.get("skills", []))
    enabled_skills = [item for item in skills if item.get("enabled")]
    behaviors = _items(agent_cfg.get("behaviors", []))
    enabled_behaviors = [item for item in behaviors if item.get("enabled")]

    lines = [
        "**AI 助手配置**",
        f"- 模型：共 {len(models)} 个，当前激活：{active_model.get('name') if active_model else '未设置'}",
    ]
    if active_model:
        lines.append(
            "- 运行模型："
            f"{active_model.get('runtime_provider') or active_model.get('provider') or '-'} / "
            f"{active_model.get('runtime_model') or '-'} / "
            f"wire={active_model.get('wire_api') or 'auto'}"
        )
    lines.extend(
        [
            f"- MCP：启用 {len(enabled_mcps)}/{len(mcps)} 个；{_names(enabled_mcps)}",
            f"- Skills：启用 {len(enabled_skills)}/{len(skills)} 个；{_names(enabled_skills)}",
            f"- 行为开关：启用 {len(enabled_behaviors)}/{len(behaviors)} 个；{_names(enabled_behaviors, field='name')}",
        ]
    )
    return lines


def _inventory_section(config: RunnableConfig | None) -> list[str]:
    clusters = _load_visible_k8s_clusters(config)
    hosts = _items(_read_json("cmdb_hosts.json", []))
    hosts = _filter_hosts_by_groups(hosts, _allowed_groups(config))
    groups = _items(_read_json("groups.json", []))
    es_clusters = _items(_read_json("es_clusters.json", []))
    redis_clusters = _items(_read_json("redis_clusters.json", []))
    kafka_clusters = _items(_read_json("kafka_clusters.json", []))
    jenkins = _items(_read_json("jenkins.json", []))

    return [
        "**平台库存**",
        f"- K8s 集群：{len(clusters)} 个；{_names(clusters)}",
        f"- CMDB 主机：{len(hosts)} 台；状态：{_count_by(hosts, 'status')}；平台：{_count_by(hosts, 'platform')}",
        f"- 主机分组：{len(groups)} 个；{_names(groups)}",
        f"- Elasticsearch：{len(es_clusters)} 个；{_names(es_clusters)}",
        f"- Redis：{len(redis_clusters)} 个；{_names(redis_clusters)}",
        f"- Kafka：{len(kafka_clusters)} 个；{_names(kafka_clusters)}",
        f"- Jenkins：{len(jenkins)} 个；{_names(jenkins)}",
    ]


def _mcp_section(agent_cfg: dict) -> list[str]:
    mcps = _items(agent_cfg.get("mcps", []))
    enabled = [item for item in mcps if item.get("enabled")]
    lines = [f"**MCP 接入**（启用 {len(enabled)}/{len(mcps)} 个）"]
    if not enabled:
        lines.append("- 当前没有启用 MCP")
        return lines
    for item in enabled[:12]:
        lines.append(
            "- "
            f"{item.get('name') or item.get('id') or '-'}："
            f"type={item.get('type') or '-'}，"
            f"ok={_yes_no(item.get('ok'))}，"
            f"auto_callable={_yes_no(item.get('auto_callable'))}，"
            f"risk={item.get('risk') or '-'}"
        )
    if len(enabled) > 12:
        lines.append(f"- ... 共 {len(enabled)} 个，仅展示前 12 个")
    return lines


@tool
async def get_platform_overview(scope: str = "overview", config: RunnableConfig = None) -> str:
    """查询 AIOps 平台自身信息、能力地图、接入组件和 AI 助手配置。

    scope 可选：
    overview=基础配置+库存+助手配置，capabilities=能力地图，agent=AI/MCP/Skills，
    inventory=K8s/CMDB/中间件/Jenkins 库存，mcp=MCP 明细，all=全部。
    用户询问平台有什么能力、当前接入了哪些组件、AI 助手用哪个模型、有哪些 MCP/工具时优先使用。
    """
    normalized = (scope or "overview").strip().lower()
    aliases = {
        "能力": "capabilities",
        "工具": "capabilities",
        "组件": "inventory",
        "接入": "inventory",
        "模型": "agent",
        "助手": "agent",
        "全部": "all",
        "平台": "overview",
    }
    normalized = aliases.get(normalized, normalized)
    settings = _read_json("settings.json", {})
    agent_cfg = _read_json("agent_config.json", {})

    sections: list[list[str]]
    if normalized in {"capabilities", "capability"}:
        sections = [_capabilities_section()]
    elif normalized in {"agent", "ai", "model", "models"}:
        sections = [_agent_section(agent_cfg)]
    elif normalized in {"inventory", "integrations", "integration", "components"}:
        sections = [_inventory_section(config)]
    elif normalized in {"mcp", "mcps"}:
        sections = [_mcp_section(agent_cfg)]
    elif normalized == "all":
        sections = [
            _settings_section(settings),
            _capabilities_section(),
            _inventory_section(config),
            _agent_section(agent_cfg),
            _mcp_section(agent_cfg),
        ]
    else:
        sections = [
            _settings_section(settings),
            _inventory_section(config),
            _agent_section(agent_cfg),
        ]

    body = "\n\n".join("\n".join(section) for section in sections)
    return (
        body
        + "\n\n说明：以上为平台本地配置和库存摘要，已隐藏密钥、密码、token、webhook、kubeconfig 等敏感字段。"
    )


__all__ = ["get_platform_overview"]
