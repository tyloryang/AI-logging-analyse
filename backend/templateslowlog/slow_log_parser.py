# coding: utf-8
"""
# MySQL 慢日志解析并生成飞书告警内容。
"""
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import requests

LOG_FILE = Path("/mysqldata/mysql/data/3306/mysql-slow.log")
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK", "https://open.co.cibfintech.co...")
ALERT_TITLE = "告警"
THRESHOLD_SECONDS = 10.0   # 只告警耗时大于此阈值的 SQL
IGNORE_DAYS_THRESHOLD = 1  # 只处理最近 IGNORE_DAYS_THRESHOLD 天内的 SQL

# 需要忽略的关键字（可根据需求增加）
IGNORE_KWS = [
    "rollback",
    "SELECT * FROM",
    "SELECT /*140001",
    "SELECT count(1) FROM",
    "select count(1) from",
    "select count(*) from",
]


def _parse_user_host(line: str) -> Dict[str, str]:
    """
    解析: # User@Host: root[root] @ [192.168.10.23]  Id: 31962
    """
    parts = line.split()
    user = parts[2].split("[")[1][0]
    host = parts[4].strip("[]")
    return {"user": user, "host": host}


def _parse_query_stats(line: str) -> Dict[str, float]:
    """
    解析: # Query_time: 1.450802  Lock_time: 0.016600  Rows_sent: 15  Rows_examined: 133456
    """
    parts = line.split()
    return {
        "query_time": float(parts[2]),
        "lock_time": float(parts[4]),
        "rows_sent": int(parts[6]),
        "rows_examined": int(parts[8]),
    }


def _parse_time(line: str) -> Optional[datetime]:
    """解析时间行，兼容常见格式"""
    time_str = line.split("# Time:")[1].strip()
    fmts = (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%Z",
        "%y%m%d %H:%M:%S",
    )
    for fmt in fmts:
        try:
            return datetime.strptime(time_str, fmt)
        except ValueError:
            continue
    return None


def iter_slow_entries(log_file: Path) -> Iterable[Dict[str, object]]:
    """逐条解析慢日志，返回包含各字段的字典。"""
    current: Dict[str, object] = {}
    sql_lines: List[str] = []

    with log_file.open("r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("# Time:"):
                # 输出上一条
                if current:
                    current["sql"] = " ".join(sql_lines).strip()
                    yield current
                    current = {}
                    sql_lines = []
                current["time"] = line.split("# Time:")[1].strip()
                parsed_time = _parse_time(line)
                if parsed_time:
                    current["time_dt"] = parsed_time
                continue

            if line.startswith("# User@Host:"):
                current.update(_parse_user_host(line))
                continue

            if line.startswith("# Query_time:"):
                current.update(_parse_query_stats(line))
                continue

            if line.startswith("SET timestamp="):
                # 本脚本不使用该字段，直接跳过
                continue

            if (
                line.startswith("/mysqldata/mysql/base/8.0.24/bin/mysqld")
                or line.startswith("Tcp port: 3306  Unix socket")
                or line.startswith("Time                 Id")
            ):
                # 本脚本不使用该字段，直接跳过
                continue

            if line.startswith("# "):
                # 其他注释行
                continue

            if line.strip():
                sql_lines.append(line.strip())

    if current:
        current["sql"] = " ".join(sql_lines).strip()
        yield current


def build_msg(item: Dict[str, object], exec_count: int = 1) -> str:
    sql = item.get("sql", "")
    max_length = 4000
    if len(sql) > max_length:
        truncated_sql = sql[:max_length - 3] + "..."
    else:
        truncated_sql = sql

    return (
        f"> 执行时间：{item.get('time', '')}\n"
        f"> 用户@主机：{item.get('user', '')}@{item.get('host', '')}\n"
        f"> 执行用时：{item.get('query_time', '')}s\n"
        f"> 执行次数：{exec_count}\n"
        f"> 锁定用时：{item.get('lock_time', '')}s\n"
        f"> 扫描行数：{item.get('rows_examined', '')}\n"
        f"> 返回行数：{item.get('rows_sent', '')}\n"
        f"> 告警SQL：{truncated_sql}"
    )


def send_feishu(webhook: str, msg: str) -> Optional[str]:
    """发送飞书文本消息。未配置 webhook 时只打印。"""
    if not webhook:
        print("未配置 FEISHU_WEBHOOK，仅打印消息：")
        print(msg)
        return None

    payload = {"msg_type": "text", "content": {"text": msg}}
    try:
        resp = requests.post(webhook, json=payload, timeout=5)
        resp.raise_for_status()
        return resp.text
    except Exception as exc:
        print(f"发送失败：{exc}")
        return None


def is_ignore(sql: str) -> bool:
    return any(kw in sql for kw in IGNORE_KWS)


def main():
    if not LOG_FILE.exists():
        print(f"日志文件不存在：{LOG_FILE}")
        return

    cutoff = datetime.now() - timedelta(days=1)

    for entry in iter_slow_entries(LOG_FILE):
        sql_text = str(entry.get("sql", ""))
        if not sql_text:
            continue

        time_dt = entry.get("time_dt")
        if not time_dt:
            print(f"忽略 SQL(时间无法解析)：{sql_text[:80]}...")
            continue

        now_ref = datetime.now(time_dt.tzinfo) if time_dt.tzinfo else datetime.now()
        cutoff = now_ref - timedelta(days=IGNORE_DAYS_THRESHOLD)

        if time_dt < cutoff:
            print(f"忽略 SQL(超过 {IGNORE_DAYS_THRESHOLD} 天)：{sql_text[:80]}...")
            continue

        if float(entry.get("query_time", 0) or 0) < THRESHOLD_SECONDS:
            print(f"忽略 SQL(耗时未超过 {THRESHOLD_SECONDS}s)：{sql_text[:80]}...")
            continue

        if is_ignore(sql_text):
            print(f"忽略 SQL(含中忽略关键字)：{sql_text[:80]}...")
            continue

        msg = build_msg(entry, exec_count=1)

        with open("slow_sql.log", "a+", encoding="utf-8") as f:
            print(msg)
            f.write("\n" + msg)

        send_feishu(FEISHU_WEBHOOK, msg)


if __name__ == "__main__":
    main()
