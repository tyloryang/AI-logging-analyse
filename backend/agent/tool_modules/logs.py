"""日志查询工具：错误日志 / 服务错误统计 / 最近日志 / 服务列表。"""
from __future__ import annotations

from langchain_core.tools import tool

from state import loki


@tool
async def query_error_logs(service: str = "", hours: int = 24, minutes: int = 0, keyword: str = "", limit: int = 50) -> str:
    """查询错误日志。service=服务名(空=全部), hours=最近N小时, minutes=最近N分钟(优先于hours，如5分钟传minutes=5), keyword=关键词过滤, limit=返回条数上限。"""
    actual_hours = minutes / 60.0 if minutes > 0 else hours
    time_label = f"{minutes}分钟" if minutes > 0 else f"{hours}小时"
    try:
        logs = await loki.query_logs(
            service=service, hours=actual_hours, limit=limit, level="error", keyword=keyword
        )
        if not logs:
            return f"最近 {time_label} 内未发现错误日志" + (f"（服务：{service}）" if service else "")
        lines = []
        for log in logs[:limit]:
            ts = str(log.get("timestamp", ""))[:19]
            svc = log.get("service", "?")
            msg = str(log.get("message", ""))[:200]
            lines.append(f"[{ts}][{svc}] {msg}")
        return f"共 {len(logs)} 条错误日志：\n" + "\n".join(lines)
    except Exception as e:
        return f"查询错误日志失败：{e}"


@tool
async def count_errors_by_service(hours: int = 24, minutes: int = 0) -> str:
    """统计各服务错误数量排名，用于快速定位问题服务。hours=统计时间范围（小时），minutes=统计时间范围（分钟，优先于hours，如最近5分钟传minutes=5）。"""
    actual_hours = minutes / 60.0 if minutes > 0 else hours
    time_label = f"{minutes}分钟" if minutes > 0 else f"{hours}小时"
    try:
        errors = await loki.count_errors_by_service(actual_hours)
        if not errors:
            return f"最近 {time_label} 无错误日志"
        sorted_errors = sorted(errors.items(), key=lambda x: x[1], reverse=True)
        total = sum(errors.values())
        lines = [f"最近 {time_label} 错误汇总（共 {total} 条，{len(errors)} 个服务）："]
        for svc, cnt in sorted_errors[:20]:
            lines.append(f"  {svc}: {cnt} 条")
        return "\n".join(lines)
    except Exception as e:
        return f"统计错误失败：{e}"


@tool
async def get_services_list() -> str:
    """获取所有被监控的服务列表及错误状态。了解系统中有哪些服务时使用。"""
    try:
        services = await loki.get_services()
        if not services:
            return "未发现任何服务"
        with_errors = sorted(
            [s for s in services if s.get("error_count", 0) > 0],
            key=lambda x: x.get("error_count", 0), reverse=True
        )
        healthy_count = len(services) - len(with_errors)
        lines = [f"共 {len(services)} 个服务，{healthy_count} 健康，{len(with_errors)} 有错误"]
        for s in with_errors[:15]:
            lines.append(f"  ⚠ {s['name']}: {s.get('error_count')} 条错误")
        return "\n".join(lines)
    except Exception as e:
        return f"获取服务列表失败：{e}"


@tool
async def query_recent_logs(service: str = "", hours: int = 1, minutes: int = 0, level: str = "", keyword: str = "", limit: int = 30) -> str:
    """查询最近的日志（可指定级别）。level=error/warn/info（空=全部级别）。minutes=最近N分钟（优先于hours，如最近10分钟传minutes=10）。适合查看服务最近运行情况。"""
    actual_hours = minutes / 60.0 if minutes > 0 else hours
    time_label = f"{minutes}分钟" if minutes > 0 else f"{hours}小时"
    try:
        logs = await loki.query_logs(
            service=service, hours=actual_hours, limit=limit, level=level, keyword=keyword
        )
        if not logs:
            return f"最近 {time_label} 内未找到符合条件的日志"
        lines = []
        for log in logs[:limit]:
            ts = str(log.get("timestamp", ""))[:19]
            svc = log.get("service", "?")
            lvl = str(log.get("level", "?")).upper()
            msg = str(log.get("message", ""))[:200]
            lines.append(f"[{ts}][{lvl}][{svc}] {msg}")
        return f"共 {len(logs)} 条日志：\n" + "\n".join(lines)
    except Exception as e:
        return f"查询日志失败：{e}"


__all__ = ["query_error_logs", "count_errors_by_service", "get_services_list", "query_recent_logs"]
