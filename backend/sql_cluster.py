"""SQL 慢查询模板聚合 — 基于 drain3

流程：
  1. 对每条 SQL 做参数脱敏（数字/字符串字面量 → <*>）
  2. 将脱敏后的 SQL 喂给 drain3 TemplateMiner
  3. 按模板分组，统计次数、耗时分布、扫描行分布
  4. 返回聚合结果列表，按 total_time 降序
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List

logger = logging.getLogger(__name__)

# ── SQL 参数脱敏 ──────────────────────────────────────────────────────────────

_RE_IN_LIST = re.compile(r"\bIN\s*\([^)]+\)", re.IGNORECASE)
_RE_STR_LIT = re.compile(r"'[^']*'|\"[^\"]*\"")
_RE_NUM_LIT = re.compile(r"\b\d+(?:\.\d+)?\b")
_RE_SPACES  = re.compile(r"\s+")


def _normalize_sql(sql: str) -> str:
    s = sql.strip().upper()
    s = _RE_IN_LIST.sub("IN (<*>)", s)
    s = _RE_STR_LIT.sub("<*>", s)
    s = _RE_NUM_LIT.sub("<*>", s)
    s = _RE_SPACES.sub(" ", s)
    return s[:500]   # 截断过长 SQL 避免 drain3 处理异常


# ── Drain3 聚合 ───────────────────────────────────────────────────────────────

def _cluster_with_drain3(norm_sqls: List[str]) -> Dict[int, str]:
    """
    用 drain3 对规范化 SQL 聚合，返回 {index: template_str} 映射。
    任何 drain3 异常会向上抛出，由调用方捕获后降级。
    """
    from drain3 import TemplateMiner
    from drain3.template_miner_config import TemplateMinerConfig

    cfg = TemplateMinerConfig()
    cfg.drain_depth = 4
    cfg.drain_sim_th = 0.4
    cfg.drain_max_children = 100
    cfg.parametrize_numeric_tokens = True
    cfg.snapshot_interval_minutes = 0   # 禁用后台快照线程

    miner = TemplateMiner(config=cfg)

    result_map: Dict[int, str] = {}
    for idx, norm in enumerate(norm_sqls):
        res = miner.add_log_message(norm)
        # drain3 返回 (LogCluster, UpdateType) 元组
        cluster_obj = res[0] if isinstance(res, tuple) else res
        template = " ".join(cluster_obj.log_template_tokens)
        result_map[idx] = template

    return result_map


def _cluster_by_prefix(norm_sqls: List[str]) -> Dict[int, str]:
    """
    drain3 不可用时的降级方案：用规范化 SQL 前100字符作为 key 分组。
    """
    result_map: Dict[int, str] = {}
    for idx, norm in enumerate(norm_sqls):
        result_map[idx] = norm[:100]
    return result_map


# ── 主函数 ────────────────────────────────────────────────────────────────────

def cluster_slow_queries(entries: List[Dict]) -> List[Dict]:
    """
    对慢查询列表做模板聚合，返回聚合列表，每条包含：
      cluster_id, template, count, total_time, avg_time, max_time,
      avg_rows, max_rows, alert_count, severity, rank, samples
    """
    if not entries:
        return []

    norm_sqls = [_normalize_sql(e.get("sql", "")) for e in entries]

    # 尝试 drain3；失败则降级为前缀分组
    try:
        template_map = _cluster_with_drain3(norm_sqls)
    except Exception as exc:
        logger.warning("[sql_cluster] drain3 失败，降级为前缀分组: %s", exc)
        template_map = _cluster_by_prefix(norm_sqls)

    # template_str → group of entries
    groups: Dict[str, List[Dict]] = {}
    templates: Dict[str, str] = {}
    for idx, e in enumerate(entries):
        tpl = template_map.get(idx, norm_sqls[idx][:100])
        groups.setdefault(tpl, []).append(e)
        templates[tpl] = tpl

    sev_order = {"critical": 2, "warning": 1, "info": 0}

    results = []
    for tpl, group in groups.items():
        times  = [e["query_time"] for e in group]
        rows   = [int(e.get("rows_examined", 0) or 0) for e in group]
        alerts = sum(1 for e in group if e.get("is_alert"))
        worst  = max(group, key=lambda e: sev_order.get(e.get("severity", "info"), 0))
        samples = sorted(group, key=lambda e: e["query_time"], reverse=True)[:3]

        total_t  = round(sum(times), 3)
        avg_rows = int(round(sum(rows) / len(rows))) if rows else 0

        results.append({
            "cluster_id":  hash(tpl) & 0x7FFFFFFF,  # stable positive int
            "template":    tpl,
            "count":       len(group),
            "total_time":  total_t,
            "avg_time":    round(total_t / len(group), 3),
            "max_time":    round(max(times), 3),
            "avg_rows":    avg_rows,
            "max_rows":    max(rows) if rows else 0,
            "alert_count": alerts,
            "severity":    worst.get("severity", "info"),
            "samples": [
                {
                    "id":            s["id"],
                    "time_str":      s.get("time_str", ""),
                    "query_time":    s["query_time"],
                    "rows_examined": int(s.get("rows_examined", 0) or 0),
                    "user":          s.get("user", ""),
                    "sql":           s.get("sql", ""),
                }
                for s in samples
            ],
        })

    results.sort(key=lambda x: x["total_time"], reverse=True)
    for i, r in enumerate(results, 1):
        r["rank"] = i

    return results
