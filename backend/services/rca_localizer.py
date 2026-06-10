"""RCA 阶段 A：Failure Localization。

只用算子（无 LLM），输出嫌疑组件清单 + 证据。供 routers/rca.py 的两阶段
流程在调用 LLM 前作为输入。

算子组合（评分权重）：
  - burst         (0.40) 当前窗错误数 vs 基线窗均值的 z-score
  - new_templates (0.25) 当前窗出现而基线窗未出现的模板数
  - rate_delta    (0.20) 错误率突变百分比
  - upstream      (0.10) 拓扑联动加分（SkyWalking 可用时；否则 0）
  - history       (0.05) 历史相似案例命中（Milvus 可用时；否则 0）

总分 0-1，>=0.5 算嫌疑。
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any

from state import loki, clusterer

logger = logging.getLogger(__name__)


# 权重（可调）
W_BURST = 0.40
W_NEW_TPL = 0.25
W_RATE = 0.20
W_UPSTREAM = 0.10
W_HISTORY = 0.05


@dataclass
class Candidate:
    service: str
    score: float
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "score": round(self.score, 3),
            "evidence": self.evidence,
        }


def _normalize(value: float, cap: float) -> float:
    """把任意正数压缩到 [0, 1]，cap 处取 1.0。"""
    if value <= 0:
        return 0.0
    return min(1.0, value / cap)


def _z_score(current: float, baseline_mean: float, baseline_stdev: float) -> float:
    if baseline_stdev <= 0:
        return 0.0 if current <= baseline_mean else min(10.0, current / max(baseline_mean, 1))
    return (current - baseline_mean) / baseline_stdev


async def _op_burst(window_hours: float) -> dict[str, dict[str, float]]:
    """对每个服务返回 {service: {burst_z, current, baseline_mean}}。"""
    current = await loki.count_errors_by_service(window_hours)
    baseline = await loki.count_errors_by_service(window_hours * 4)

    # baseline 是累计 4 窗的总数；平均到单窗
    out: dict[str, dict[str, float]] = {}
    for svc, cur in current.items():
        base_total = baseline.get(svc, 0)
        base_mean = max(0.0, (base_total - cur) / 3)  # 排除当前窗
        # stdev 用 sqrt(mean) 当 Poisson 近似（错误事件常近似 Poisson）
        base_stdev = math.sqrt(max(1.0, base_mean))
        z = _z_score(cur, base_mean, base_stdev)
        out[svc] = {
            "burst_z": round(z, 2),
            "current": float(cur),
            "baseline_mean_per_window": round(base_mean, 2),
        }
    return out


async def _op_new_templates(
    window_hours: float,
    candidate_services: list[str],
    sample_limit: int = 2000,
) -> dict[str, dict[str, Any]]:
    """对每个候选服务计算 当前窗模板集合 - 基线窗模板集合 = 新增模板。"""
    out: dict[str, dict[str, Any]] = {}
    now_ns = int(time.time() * 1e9)
    win_ns = int(window_hours * 3600 * 1e9)

    current_end = now_ns
    current_start = now_ns - win_ns
    baseline_end = current_start - 1
    baseline_start = baseline_end - 3 * win_ns  # 用 3 倍窗做基线

    for svc in candidate_services:
        try:
            cur_logs = await loki.query_logs(
                service=svc,
                start_ns=current_start,
                end_ns=current_end,
                limit=sample_limit,
                level="error",
            )
            base_logs = await loki.query_logs(
                service=svc,
                start_ns=baseline_start,
                end_ns=baseline_end,
                limit=sample_limit * 3,
                level="error",
            )
            cur_tpls = {t.get("template", "") for t in clusterer.cluster(cur_logs, top_n=100)}
            base_tpls = {t.get("template", "") for t in clusterer.cluster(base_logs, top_n=100)}
            new_set = cur_tpls - base_tpls - {""}
            out[svc] = {
                "new_template_count": len(new_set),
                "examples": sorted(new_set)[:3],
            }
        except Exception as exc:
            logger.warning("[localize.new_templates] %s failed: %s", svc, exc)
            out[svc] = {"new_template_count": 0, "examples": [], "error": str(exc)[:120]}
    return out


async def _op_rate_delta(
    window_hours: float,
    candidate_services: list[str],
) -> dict[str, dict[str, float]]:
    """简单的 error_rate_delta：当前窗错误数 / 基线窗均值，>1 表示突变倍数。

    用 burst 复用数据：基线已经在 _op_burst 中算过，这里直接用上层缓存即可。
    本函数独立调用一次保证职责清晰，命中 loki 的 60s 缓存所以代价不大。
    """
    current = await loki.count_errors_by_service(window_hours)
    baseline = await loki.count_errors_by_service(window_hours * 4)
    out: dict[str, dict[str, float]] = {}
    for svc in candidate_services:
        cur = current.get(svc, 0)
        base_total = baseline.get(svc, 0)
        base_mean = max(1.0, (base_total - cur) / 3)
        delta_pct = (cur - base_mean) / base_mean * 100
        out[svc] = {
            "error_rate_delta_pct": round(delta_pct, 1),
            "ratio": round(cur / max(base_mean, 1), 2),
        }
    return out


async def _op_history(query_text: str, top_k: int = 3) -> list[dict[str, Any]]:
    """检索历史案例（可选，Milvus 不可用时返回空）。"""
    try:
        from agent.milvus_memory import get_memory  # type: ignore

        hits = await get_memory().search(query_text, top_k)
        return hits or []
    except Exception as exc:
        logger.debug("[localize.history] Milvus unavailable: %s", exc)
        return []


def _aggregate_score(
    burst_z: float,
    new_tpl_count: int,
    rate_delta_pct: float,
    upstream_hits: int = 0,
    history_hits: int = 0,
) -> float:
    """把各算子原始信号归一并按权重相加。

    归一上限是工程经验值，可按生产分布回调：
      - burst_z       cap=4.0   (z=4 即非常显著)
      - new_templates cap=5     (5 个全新错误模板足以怀疑)
      - rate_delta    cap=300%  (3 倍以上算极端)
      - upstream      cap=3
      - history       cap=3
    """
    return (
        W_BURST * _normalize(max(0.0, burst_z), 4.0)
        + W_NEW_TPL * _normalize(new_tpl_count, 5)
        + W_RATE * _normalize(max(0.0, rate_delta_pct), 300)
        + W_UPSTREAM * _normalize(upstream_hits, 3)
        + W_HISTORY * _normalize(history_hits, 3)
    )


async def localize_failure(
    window_hours: float = 1.0,
    top_k: int = 5,
    suspect_burst_z: float = 1.5,
    query_text: str = "",
) -> dict[str, Any]:
    """运行阶段 A，返回 {candidates: [...], elapsed_ms, signals}。

    流程：
      1. 跑 burst 算子，挑 top_k * 2 个 burst_z >= suspect_burst_z 的服务做后续算子
      2. 对它们跑 new_templates + rate_delta（并行慢）
      3. 历史检索（异步可选）
      4. 加权评分，按 score 降序返回 top_k 候选
    """
    started = time.perf_counter()

    burst_map = await _op_burst(window_hours)
    # 选 burst_z >= 阈值 或 错误数前 top_k*2 的服务（兜底）
    by_z = sorted(burst_map.items(), key=lambda kv: kv[1]["burst_z"], reverse=True)
    suspects = [svc for svc, ev in by_z if ev["burst_z"] >= suspect_burst_z][: top_k * 2]
    if not suspects:
        # 兜底：哪怕 z 不显著，也按错误数挑前几个
        by_cnt = sorted(burst_map.items(), key=lambda kv: kv[1]["current"], reverse=True)
        suspects = [svc for svc, _ in by_cnt[: top_k * 2]]

    if not suspects:
        return {
            "candidates": [],
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "signals": {"burst_service_count": len(burst_map)},
            "note": "未发现任何错误信号；可能时间窗内系统正常或日志未到达 Loki",
        }

    new_tpl_map = await _op_new_templates(window_hours, suspects)
    rate_map = await _op_rate_delta(window_hours, suspects)
    history_hits = await _op_history(query_text or "service error spike", top_k=3)

    candidates: list[Candidate] = []
    for svc in suspects:
        burst = burst_map.get(svc, {})
        ntpl = new_tpl_map.get(svc, {})
        rate = rate_map.get(svc, {})
        score = _aggregate_score(
            burst_z=float(burst.get("burst_z", 0)),
            new_tpl_count=int(ntpl.get("new_template_count", 0)),
            rate_delta_pct=float(rate.get("error_rate_delta_pct", 0)),
            upstream_hits=0,  # SkyWalking 联动留作 P2 扩展
            history_hits=len([h for h in history_hits if svc.lower() in str(h).lower()]),
        )
        evidence = {
            "burst_z": burst.get("burst_z", 0),
            "current_errors": burst.get("current", 0),
            "baseline_mean_per_window": burst.get("baseline_mean_per_window", 0),
            "new_template_count": ntpl.get("new_template_count", 0),
            "new_template_examples": ntpl.get("examples", []),
            "error_rate_delta_pct": rate.get("error_rate_delta_pct", 0),
        }
        candidates.append(Candidate(service=svc, score=score, evidence=evidence))

    candidates.sort(key=lambda c: c.score, reverse=True)
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    return {
        "stage": "localized",
        "candidates": [c.to_dict() for c in candidates[:top_k]],
        "elapsed_ms": elapsed_ms,
        "signals": {
            "burst_service_count": len(burst_map),
            "suspect_count": len(suspects),
            "history_hits": len(history_hits),
        },
    }


__all__ = ["localize_failure", "Candidate"]
