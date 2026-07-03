"""Prometheus PromQL 查询与历史趋势工具（供 aiops_router / prometheus.md skill 使用）。"""
from __future__ import annotations

import time
from statistics import median

from langchain_core.tools import tool

from state import prom


@tool
async def promql_query(query: str) -> str:
    """执行 PromQL instant 查询（当前时刻）。
    query=PromQL 表达式（必填），示例：
      - up{job="node"} == 0                       # 有多少 target 挂了
      - rate(http_requests_total[5m])             # 每秒请求数
      - histogram_quantile(0.99, ...)            # P99 延迟
    返回：instant 结果的 metric labels + 值（最多 20 条）。"""
    try:
        result = await prom.query(query, timeout=10)
        if not result:
            return f"PromQL `{query}` 无结果（可能 target 全 down 或表达式错误）"
        lines = [f"**PromQL 结果（{len(result)} 条，最多显示 20）**\n"]
        for item in result[:20]:
            labels = item.get("metric", {}) or {}
            value = item.get("value") or []
            v = value[1] if len(value) > 1 else "-"
            label_str = ",".join(f"{k}={v}" for k, v in list(labels.items())[:6]) or "(无标签)"
            lines.append(f"- `{label_str}` → **{v}**")
        return "\n".join(lines)
    except Exception as e:
        return f"PromQL 查询失败：{e}"


@tool
async def get_metric_history(query: str, hours: int = 168, step_seconds: int = 300) -> str:
    """拉 PromQL 时序历史给 LLM 直接看曲线判断趋势（不跑算法）。

    query=PromQL 表达式（必填），支持任意聚合，如 `sum(rate(http_requests_total[5m])) by (service)`
    hours=拉多少小时（默认 168=7 天）
    step_seconds=采样步长（默认 300s=5 分钟，7 天 x 5 分钟 ≈ 2016 点）

    返回：每条 series 的采样点 + 统计摘要（min/median/p95/max/首末值）
    让 AI 直接对比现在 vs 历史中位数/百分位判断『是否异常、是否首次、周期性』。
    典型用法：接到告警后拉 7 天曲线，问 AI『这个尖峰在历史里正常吗？』"""
    if hours <= 0 or hours > 720:
        return "hours 必须在 (0, 720] 范围内"
    if step_seconds < 15:
        step_seconds = 15
    try:
        end = time.time()
        start = end - hours * 3600
        series = await prom.query_range(query, start=start, end=end, step=step_seconds, timeout=20)
        if not series:
            return f"PromQL `{query}` 历史查询无数据（{hours}h）"

        out = [f"**历史时序（PromQL: `{query}` · 最近 {hours}h · step={step_seconds}s）**\n"]
        out.append(f"共 {len(series)} 条 series，每条给出摘要 + 采样点（下采样至 40 点便于 AI 阅读）：\n")

        for idx, item in enumerate(series[:5]):  # 最多 5 条 series
            labels = item.get("metric", {}) or {}
            values = item.get("values") or []
            if not values:
                continue
            nums = []
            for pair in values:
                try:
                    nums.append(float(pair[1]))
                except (ValueError, TypeError):
                    pass
            if not nums:
                continue
            # 下采样：等距抽 40 个点
            if len(nums) > 40:
                stride = len(nums) // 40
                sampled = nums[::stride][:40]
            else:
                sampled = nums

            label_str = ",".join(f"{k}={v}" for k, v in list(labels.items())[:5]) or "(无标签)"
            stats = {
                "min":    min(nums),
                "median": median(nums),
                "p95":    sorted(nums)[int(len(nums) * 0.95)] if nums else 0,
                "max":    max(nums),
                "first":  nums[0],
                "last":   nums[-1],
            }
            out.append(f"### series[{idx}] `{label_str}`")
            out.append(f"- 统计：min={stats['min']:.4g} · median={stats['median']:.4g} · p95={stats['p95']:.4g} · max={stats['max']:.4g}")
            out.append(f"- 首末：{stats['first']:.4g} → {stats['last']:.4g}（{'涨' if stats['last']>stats['first'] else ('跌' if stats['last']<stats['first'] else '平')} {abs(stats['last']-stats['first']):.4g}）")
            out.append(f"- 曲线（40 点等距下采样）：")
            out.append(f"  `{' '.join(f'{v:.3g}' for v in sampled)}`")
            out.append("")

        if len(series) > 5:
            out.append(f"...还有 {len(series) - 5} 条 series 未展示（可用更具体的 label 过滤缩小范围）")

        out.append("### 【AI 判断趋势的建议】")
        out.append("- 若当前值 > p95 → 已进入告警区间")
        out.append("- 若 last > median × 2 → 显著异常")
        out.append("- 观察曲线是否有规律周期（业务时段/夜间）")
        out.append("- 与阈值/SLO 目标对比看是否首次触及")
        return "\n".join(out)
    except Exception as e:
        return f"获取指标历史失败：{e}"


__all__ = ["promql_query", "get_metric_history"]
