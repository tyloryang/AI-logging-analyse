"""中间件总览工具。"""
from __future__ import annotations

from langchain_core.tools import tool


@tool
async def get_middleware_summary() -> str:
    """查询中间件总览：MySQL / Redis / Kafka / Elasticsearch 等实例数量和健康状态。
    用户询问中间件状态、数据库状态、消息队列状态时使用。"""
    try:
        from routers.middleware import middleware_summary
        data = await middleware_summary()
        if not data:
            return "暂无中间件数据（Prometheus 中未发现中间件 target）"
        lines = ["**中间件总览**\n"]
        for item in data:
            icon = item.get("icon", "")
            label = item.get("label", item.get("type", "?"))
            total = item.get("total", "?")
            up = item.get("up", "?")
            ok = item.get("up") == item.get("total")
            status_mark = "[正常]" if ok else "[异常]"
            lines.append(f"{status_mark} {icon} {label} — {up}/{total} 实例正常")
        return "\n".join(lines)
    except Exception as exc:
        return f"查询中间件失败：{exc}"


@tool
async def get_middleware_instances(middleware_type: str = "") -> str:
    """查询具体中间件实例列表及连接信息。
    middleware_type = mysql / redis / kafka / elasticsearch / 留空=全部。
    用户询问某类中间件的实例详情时使用。"""
    try:
        from routers.middleware import list_instances
        instances = await list_instances()
        if middleware_type:
            instances = [i for i in instances if i.get("type", "").lower() == middleware_type.lower()]
        if not instances:
            return f"未找到{'类型：' + middleware_type + ' 的' if middleware_type else '任何'}中间件实例"
        lines = [f"**中间件实例列表**（{middleware_type or '全部'}，共 {len(instances)} 个）\n"]
        for inst in instances[:20]:
            status = "[正常]" if inst.get("status") == "up" else "[异常]"
            lines.append(
                f"{status} [{inst.get('label', inst.get('type',''))}] "
                f"{inst.get('instance','')}  job:{inst.get('job','?')}"
            )
        return "\n".join(lines)
    except Exception as exc:
        return f"查询中间件实例失败：{exc}"


__all__ = ["get_middleware_summary", "get_middleware_instances"]
