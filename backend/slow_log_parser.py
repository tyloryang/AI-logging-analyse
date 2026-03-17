"""MySQL 8 慢日志解析器（改编自 templateslowlog/slow_log_parser.py）"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional

# ── 默认阈值 ──────────────────────────────────────────────────────────────────
DEFAULT_THRESHOLD  = 1.0    # 只解析耗时 ≥ 此秒数的 SQL
DEFAULT_ALERT_SEC  = 10.0   # 耗时 ≥ 此秒数标记为 alert

# 需要忽略的关键字（原脚本保留）
IGNORE_KWS: List[str] = [
    "rollback",
    "SELECT * FROM",
    "SELECT /*140001",
    "SELECT count(1) FROM",
    "select count(1) from",
    "select count(*) from",
]


# ── 解析辅助函数 ───────────────────────────────────────────────────────────────

def _parse_user_host(line: str) -> Dict[str, str]:
    """# User@Host: appuser[appuser] @ [192.168.10.101]  Id: 10001"""
    try:
        user_part, host_part = line.split("@", 2)[1], line.split("@", 2)[2]
        user  = re.search(r"\[([^\]]*)\]", user_part)
        user  = user.group(1) if user else user_part.strip().split("[")[0].strip()
        host  = re.search(r"\[([^\]]*)\]", host_part)
        host  = host.group(1) if host else ""
    except Exception:
        user, host = "", ""
    return {"user": user, "host": host}


def _parse_query_stats(line: str) -> Dict[str, float]:
    """# Query_time: 12.3  Lock_time: 0.0  Rows_sent: 1  Rows_examined: 980000"""
    def _f(key: str) -> float:
        m = re.search(rf"{key}:\s*([\d.]+)", line)
        return float(m.group(1)) if m else 0.0
    return {
        "query_time":    _f("Query_time"),
        "lock_time":     _f("Lock_time"),
        "rows_sent":     int(_f("Rows_sent")),
        "rows_examined": int(_f("Rows_examined")),
    }


_TIME_FMTS = (
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S",
    "%y%m%d %H:%M:%S",
)


def _parse_time(raw: str) -> Optional[datetime]:
    raw = raw.strip()
    for fmt in _TIME_FMTS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _is_ignore(sql: str) -> bool:
    return any(kw in sql for kw in IGNORE_KWS)


# ── 核心解析器 ────────────────────────────────────────────────────────────────

def iter_slow_entries(text: str) -> Iterable[Dict]:
    """
    从日志文本逐条解析慢查询，yield 包含以下字段的字典：
      time_raw, time_dt, user, host, query_time, lock_time,
      rows_sent, rows_examined, sql, is_ignore
    """
    current: Dict = {}
    sql_lines: List[str] = []

    for line in text.splitlines():
        if line.startswith("# Time:"):
            if current:
                current["sql"] = " ".join(sql_lines).strip()
                current["is_ignore"] = _is_ignore(current["sql"])
                yield current
            current = {}
            sql_lines = []
            time_raw = line.split("# Time:", 1)[1].strip()
            current["time_raw"] = time_raw
            current["time_dt"]  = _parse_time(time_raw)
            continue

        if line.startswith("# User@Host:"):
            current.update(_parse_user_host(line))
            continue

        if line.startswith("# Query_time:"):
            current.update(_parse_query_stats(line))
            continue

        # 跳过 SET timestamp= 和文件头
        if (line.startswith("SET timestamp=")
                or line.startswith("/mysqldata")
                or line.startswith("Tcp port:")
                or line.startswith("Time ")
                or line.startswith("# ")):
            continue

        if line.strip():
            sql_lines.append(line.strip())

    # 最后一条
    if current:
        current["sql"] = " ".join(sql_lines).strip()
        current["is_ignore"] = _is_ignore(current["sql"])
        yield current


def parse_slow_log(
    text: str,
    date: Optional[str] = None,          # 兼容旧调用：单日期 "YYYY-MM-DD"
    threshold_sec: float = DEFAULT_THRESHOLD,
    alert_sec: float = DEFAULT_ALERT_SEC,
    date_from: Optional[str] = None,     # 时间段起始 "YYYY-MM-DD"
    date_to: Optional[str] = None,       # 时间段结束 "YYYY-MM-DD"（含）
) -> List[Dict]:
    """
    解析慢日志文本，返回结构化列表，每条包含：
      id, time_raw, time_str, user, host,
      query_time, lock_time, rows_sent, rows_examined,
      sql, is_ignore, is_alert, severity

    日期过滤优先级：date_from/date_to > date（单日兼容）
    """
    from datetime import date as date_type

    dt_from: Optional[date_type] = None
    dt_to:   Optional[date_type] = None

    if date_from or date_to:
        try:
            if date_from:
                dt_from = datetime.strptime(date_from, "%Y-%m-%d").date()
            if date_to:
                dt_to = datetime.strptime(date_to, "%Y-%m-%d").date()
        except ValueError:
            pass
    elif date:
        try:
            d = datetime.strptime(date, "%Y-%m-%d").date()
            dt_from = dt_to = d
        except ValueError:
            pass

    results = []
    idx = 0
    for entry in iter_slow_entries(text):
        sql = entry.get("sql", "")
        if not sql:
            continue

        qt = float(entry.get("query_time", 0) or 0)
        if qt < threshold_sec:
            continue

        time_dt: Optional[datetime] = entry.get("time_dt")

        # 日期范围过滤
        if (dt_from or dt_to) and time_dt:
            entry_date = time_dt.date()
            if dt_from and entry_date < dt_from:
                continue
            if dt_to and entry_date > dt_to:
                continue

        # 格式化时间
        if time_dt:
            time_str = time_dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            time_str = entry.get("time_raw", "")

        is_alert = qt >= alert_sec

        # 严重程度
        if qt >= 60:
            severity = "critical"
        elif qt >= 10:
            severity = "warning"
        else:
            severity = "info"

        idx += 1
        results.append({
            "id":            idx,
            "time_raw":      entry.get("time_raw", ""),
            "time_str":      time_str,
            "time_dt":       time_dt.isoformat() if time_dt else None,
            "user":          entry.get("user", ""),
            "host":          entry.get("host", ""),
            "query_time":    round(qt, 3),
            "lock_time":     round(float(entry.get("lock_time", 0) or 0), 6),
            "rows_sent":     int(entry.get("rows_sent", 0) or 0),
            "rows_examined": int(entry.get("rows_examined", 0) or 0),
            "sql":           sql,
            "is_ignore":     bool(entry.get("is_ignore")),
            "is_alert":      is_alert,
            "severity":      severity,
        })

    return results


def build_summary(entries: List[Dict]) -> Dict:
    """生成汇总统计"""
    if not entries:
        return {"total": 0, "alert_count": 0, "avg_query_time": 0,
                "max_query_time": 0, "top_slow": []}

    alert_count  = sum(1 for e in entries if e["is_alert"])
    avg_qt       = round(sum(e["query_time"] for e in entries) / len(entries), 2)
    max_qt       = max(e["query_time"] for e in entries)
    top_slow     = sorted(entries, key=lambda x: x["query_time"], reverse=True)[:5]

    # 按用户统计
    user_stats: Dict[str, Dict] = {}
    for e in entries:
        u = e["user"] or "unknown"
        user_stats.setdefault(u, {"user": u, "count": 0, "total_time": 0.0})
        user_stats[u]["count"] += 1
        user_stats[u]["total_time"] += e["query_time"]
    top_users = sorted(user_stats.values(), key=lambda x: x["total_time"], reverse=True)[:5]

    return {
        "total":          len(entries),
        "alert_count":    alert_count,
        "avg_query_time": avg_qt,
        "max_query_time": round(max_qt, 3),
        "top_slow":       [{"id": e["id"], "query_time": e["query_time"],
                            "sql_brief": e["sql"][:120]} for e in top_slow],
        "top_users":      top_users,
    }
