"""
基于 Drain3 的日志模板聚合器

Drain 算法通过前缀树对日志行进行在线聚类，将大量重复日志
归纳为带 <*> 占位符的模板，例如：
  "Connection timeout to 10.0.1.5 after 30002ms"
  "Connection timeout to 10.0.2.3 after 15443ms"
  → "Connection timeout to <*> after <*>"
"""
import re
from collections import defaultdict

from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig


# 预编译：剥离日志行头部的时间戳和日志级别，让 Drain 专注于消息体
_RE_TIMESTAMP = re.compile(
    r"^\d{4}[-/]\d{2}[-/]\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?\s*"
)
_RE_LEVEL = re.compile(
    r"^\[?(?:ERROR|WARN(?:ING)?|INFO|DEBUG|FATAL|TRACE|CRITICAL)\]?\s*[-:]?\s*",
    re.IGNORECASE,
)
_RE_CALLER = re.compile(r"^\S+\.\w+:\d+\s*")  # e.g. "main.go:42 "


def _clean(line: str) -> str:
    """剥离时间戳、级别、调用位置等非语义前缀"""
    s = _RE_TIMESTAMP.sub("", line)
    s = _RE_LEVEL.sub("", s)
    s = _RE_CALLER.sub("", s)
    return s.strip() or line.strip()


def _make_template_miner() -> TemplateMiner:
    """创建一个无持久化的内存 TemplateMiner 实例"""
    cfg = TemplateMinerConfig()
    cfg.load_defaults()

    # ── Drain 超参数 ──────────────────────────────
    cfg.drain_sim_th = 0.4       # 相似度阈值（越低越宽松，同一模板更多）
    cfg.drain_depth = 4          # 前缀树深度
    cfg.drain_max_children = 100 # 每节点最大子节点
    cfg.drain_max_clusters = 500 # 最多保留多少模板
    cfg.parametrize_numeric_tokens = True  # 数字自动变为 <*>

    # 不做任何持久化（每次请求独立聚类）
    return TemplateMiner(persistence_handler=None, config=cfg)


class LogClusterer:
    def cluster(
        self,
        logs: list[dict],
        top_n: int = 50,
    ) -> list[dict]:
        """
        对日志列表进行 Drain3 模板聚类。

        返回按出现次数降序排列的模板列表，每条包含：
          - template     : 带 <*> 占位符的模板字符串
          - count        : 归属该模板的日志条数
          - top_services : 贡献最多的服务（最多 5 个）
          - example      : 一条原始日志示例
          - cluster_id   : Drain 内部 ID
        """
        if not logs:
            return []

        tm = _make_template_miner()

        # cluster_id → {logs, services}
        cluster_meta: dict[int, dict] = defaultdict(
            lambda: {"logs": [], "services": defaultdict(int)}
        )

        for log in logs:
            clean = _clean(log["line"])
            result = tm.add_log_message(clean)
            if result and result.cluster:
                cid = result.cluster.cluster_id
                cluster_meta[cid]["logs"].append(log)
                svc = log["labels"].get("app") or log["labels"].get("job") or "unknown"
                cluster_meta[cid]["services"][svc] += 1

        templates = []
        for cluster in sorted(
            tm.drain.clusters, key=lambda c: c.size, reverse=True
        )[:top_n]:
            cid = cluster.cluster_id
            meta = cluster_meta.get(cid, {})
            raw_logs = meta.get("logs", [])
            services = meta.get("services", {})

            # 服务分布，按数量降序取前 5
            top_svcs = sorted(services.items(), key=lambda x: x[1], reverse=True)[:5]

            templates.append({
                "cluster_id":   cid,
                "template":     cluster.get_template(),
                "count":        cluster.size,
                "top_services": [{"name": s, "count": c} for s, c in top_svcs],
                "example":      raw_logs[0]["line"] if raw_logs else "",
                "example_ts":   raw_logs[0]["timestamp"] if raw_logs else "",
            })

        return templates
