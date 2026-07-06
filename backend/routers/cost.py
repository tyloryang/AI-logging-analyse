"""资源成本分析（参考 itops-agent-platform monitor/CostAnalysis）。

我们没有真实云账单接入，改为基于 CMDB 主机规格（CPU/内存/磁盘）+ 可配单价
做成本估算，并结合实时利用率（cpu_usage_pct）识别闲置浪费与优化建议。

路由前缀：/api/cost/*
单价可用环境变量覆盖：COST_RATE_CPU / COST_RATE_MEM / COST_RATE_DISK（¥/单位/小时）
"""
import os
import logging

from fastapi import APIRouter, Depends

from auth.deps import current_user
from auth.models import User

logger = logging.getLogger(__name__)
router = APIRouter()

_HOURS_PER_MONTH = 24 * 30


def _rate(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _rates() -> dict:
    return {
        "cpu":  _rate("COST_RATE_CPU", 0.10),    # ¥/核/小时
        "mem":  _rate("COST_RATE_MEM", 0.02),    # ¥/GB/小时
        "disk": _rate("COST_RATE_DISK", 0.0005), # ¥/GB/小时
    }


def _host_monthly(host: dict, rates: dict) -> float:
    cpu = float(host.get("cpu_cores") or 0)
    mem = float(host.get("memory_gb") or 0)
    disk = float(host.get("disk_gb") or 0)
    hourly = cpu * rates["cpu"] + mem * rates["mem"] + disk * rates["disk"]
    return round(hourly * _HOURS_PER_MONTH, 2)


@router.get("/api/cost/overview")
async def cost_overview(_: User = Depends(current_user)):
    """基于 CMDB 主机规格估算月度成本 + 闲置浪费 + 优化建议。"""
    from state import load_hosts_list

    rates = _rates()
    hosts = load_hosts_list()

    host_costs = []
    by_env: dict[str, float] = {}
    by_group: dict[str, float] = {}
    total = 0.0
    idle_waste = 0.0

    for h in hosts:
        monthly = _host_monthly(h, rates)
        total += monthly
        env = h.get("env") or "未分类"
        group = h.get("group") or "未分组"
        by_env[env] = round(by_env.get(env, 0) + monthly, 2)
        by_group[group] = round(by_group.get(group, 0) + monthly, 2)

        cpu_use = h.get("cpu_usage_pct")
        mem_use = h.get("memory_usage_pct")
        # 闲置浪费：利用率越低，浪费越多（用 CPU 利用率近似）
        waste = 0.0
        if isinstance(cpu_use, (int, float)) and cpu_use < 40:
            waste = round(monthly * (1 - cpu_use / 100) * 0.5, 2)
            idle_waste += waste

        host_costs.append({
            "id": h.get("id"),
            "hostname": h.get("hostname") or h.get("ip", ""),
            "ip": h.get("ip", ""),
            "env": env,
            "group": group,
            "cpu_cores": h.get("cpu_cores"),
            "memory_gb": h.get("memory_gb"),
            "disk_gb": h.get("disk_gb"),
            "cpu_usage_pct": cpu_use,
            "memory_usage_pct": mem_use,
            "monthly": monthly,
            "waste": waste,
        })

    host_costs.sort(key=lambda x: x["monthly"], reverse=True)

    # 优化建议
    recommendations = []
    for hc in host_costs:
        cpu_use = hc.get("cpu_usage_pct")
        if not isinstance(cpu_use, (int, float)):
            continue
        if cpu_use < 5:
            recommendations.append({
                "type": "idle", "level": "high",
                "resource": f"{hc['hostname']} ({hc['ip']})",
                "title": "疑似闲置主机", "monthly_savings": round(hc["monthly"] * 0.9, 2),
                "description": f"CPU 利用率仅 {cpu_use}%，建议确认是否可回收或合并",
            })
        elif cpu_use < 15:
            recommendations.append({
                "type": "downsize", "level": "medium",
                "resource": f"{hc['hostname']} ({hc['ip']})",
                "title": "建议降配", "monthly_savings": round(hc["monthly"] * 0.4, 2),
                "description": f"CPU 利用率 {cpu_use}%，规格偏高，可降配约省 40%",
            })
    recommendations.sort(key=lambda x: x["monthly_savings"], reverse=True)

    potential_savings = round(sum(r["monthly_savings"] for r in recommendations), 2)

    return {
        "rates": rates,
        "currency": "¥",
        "summary": {
            "total_monthly": round(total, 2),
            "host_count": len(hosts),
            "idle_waste": round(idle_waste, 2),
            "potential_savings": potential_savings,
            "avg_per_host": round(total / len(hosts), 2) if hosts else 0,
        },
        "by_env": [{"name": k, "value": v} for k, v in sorted(by_env.items(), key=lambda x: -x[1])],
        "by_group": [{"name": k, "value": v} for k, v in sorted(by_group.items(), key=lambda x: -x[1])],
        "hosts": host_costs,
        "recommendations": recommendations[:10],
    }
