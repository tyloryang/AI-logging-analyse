from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

_DISPLAY_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")
_NOW_NS = int(time.time() * 1e9)
_BASE_NS = _NOW_NS - 40 * 60 * 1_000_000_000


def _format_display_timestamp(ts_ns: str | int) -> str:
    dt = datetime.fromtimestamp(int(ts_ns) / 1e9, tz=timezone.utc).astimezone(_DISPLAY_TZ)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _entry(
    offset_seconds: int,
    *,
    app: str,
    namespace: str,
    env: str,
    team: str,
    cluster: str,
    pod: str,
    line: str,
) -> dict:
    ts_ns = _BASE_NS + offset_seconds * 1_000_000_000
    labels = {
        "app": app,
        "job": app,
        "namespace": namespace,
        "env": env,
        "team": team,
        "cluster": cluster,
        "pod": pod,
    }
    return {
        "timestamp": _format_display_timestamp(ts_ns),
        "timestamp_ns": str(ts_ns),
        "line": line,
        "labels": labels,
    }


_DEMO_LOGS = sorted(
    [
        _entry(0, app="gateway-service", namespace="prod", env="prod", team="edge", cluster="cluster-a", pod="gateway-6c9d8b", line="INFO request accepted traceId=trace-1001 requestId=req-9001 path=/api/orders/submit"),
        _entry(4, app="gateway-service", namespace="prod", env="prod", team="edge", cluster="cluster-a", pod="gateway-6c9d8b", line="INFO auth token verified traceId=trace-1001 userId=1024"),
        _entry(7, app="gateway-service", namespace="prod", env="prod", team="edge", cluster="cluster-a", pod="gateway-6c9d8b", line="WARN upstream order-service latency increased traceId=trace-1001 attempt=1"),
        _entry(11, app="gateway-service", namespace="prod", env="prod", team="edge", cluster="cluster-a", pod="gateway-6c9d8b", line="ERROR upstream request timeout calling order-service traceId=trace-1001 timeout=800ms"),
        _entry(15, app="gateway-service", namespace="prod", env="prod", team="edge", cluster="cluster-a", pod="gateway-6c9d8b", line="INFO retrying upstream request traceId=trace-1001 retry=1"),
        _entry(19, app="gateway-service", namespace="prod", env="prod", team="edge", cluster="cluster-a", pod="gateway-6c9d8b", line="INFO response recovered after retry traceId=trace-1001 status=200"),
        _entry(23, app="gateway-service", namespace="prod", env="prod", team="edge", cluster="cluster-a", pod="gateway-6c9d8b", line="INFO request completed traceId=trace-1001 cost=1248ms"),
        _entry(40, app="order-service", namespace="prod", env="prod", team="commerce", cluster="cluster-a", pod="order-7f7d6c", line="INFO create order begin traceId=trace-1001 orderNo=SO20260602001"),
        _entry(45, app="order-service", namespace="prod", env="prod", team="commerce", cluster="cluster-a", pod="order-7f7d6c", line="INFO lock inventory traceId=trace-1001 sku=SKU-1"),
        _entry(49, app="order-service", namespace="prod", env="prod", team="commerce", cluster="cluster-a", pod="order-7f7d6c", line="WARN payment-service slow response traceId=trace-1001 elapsed=620ms"),
        _entry(54, app="order-service", namespace="prod", env="prod", team="commerce", cluster="cluster-a", pod="order-7f7d6c", line="ERROR payment-service timeout traceId=trace-1001 elapsed=1200ms"),
        _entry(58, app="order-service", namespace="prod", env="prod", team="commerce", cluster="cluster-a", pod="order-7f7d6c", line="INFO order marked pending_payment traceId=trace-1001"),
        _entry(74, app="payment-service", namespace="prod", env="prod", team="finance", cluster="cluster-a", pod="payment-5b8d4f", line="INFO payment request received traceId=trace-1001 channel=alipay"),
        _entry(79, app="payment-service", namespace="prod", env="prod", team="finance", cluster="cluster-a", pod="payment-5b8d4f", line="WARN redis connection pool saturated traceId=trace-1001 active=48"),
        _entry(84, app="payment-service", namespace="prod", env="prod", team="finance", cluster="cluster-a", pod="payment-5b8d4f", line="ERROR redis timeout traceId=trace-1001 key=payment:token:9001"),
        _entry(88, app="payment-service", namespace="prod", env="prod", team="finance", cluster="cluster-a", pod="payment-5b8d4f", line="ERROR payment callback exception traceId=trace-1001 java.lang.IllegalStateException: callback not ready"),
        _entry(92, app="payment-service", namespace="prod", env="prod", team="finance", cluster="cluster-a", pod="payment-5b8d4f", line="INFO fallback queue published traceId=trace-1001 topic=payment_retry"),
        _entry(110, app="inventory-service", namespace="prod", env="prod", team="commerce", cluster="cluster-a", pod="inventory-84cdd9", line="INFO reserve stock begin traceId=trace-1002 sku=SKU-9"),
        _entry(114, app="inventory-service", namespace="prod", env="prod", team="commerce", cluster="cluster-a", pod="inventory-84cdd9", line="INFO reserve stock success traceId=trace-1002 remaining=182"),
        _entry(130, app="gateway-service", namespace="prod", env="prod", team="edge", cluster="cluster-a", pod="gateway-6c9d8b", line="INFO request accepted traceId=trace-2001 requestId=req-9011 path=/api/payments/confirm"),
        _entry(134, app="gateway-service", namespace="prod", env="prod", team="edge", cluster="cluster-a", pod="gateway-6c9d8b", line="ERROR downstream 502 from payment-service traceId=trace-2001"),
        _entry(138, app="gateway-service", namespace="prod", env="prod", team="edge", cluster="cluster-a", pod="gateway-6c9d8b", line="WARN circuit breaker opened traceId=trace-2001 target=payment-service"),
        _entry(142, app="gateway-service", namespace="prod", env="prod", team="edge", cluster="cluster-a", pod="gateway-6c9d8b", line="INFO degraded response returned traceId=trace-2001 status=202"),
        _entry(180, app="user-service", namespace="staging", env="staging", team="account", cluster="cluster-b", pod="user-69c4bb", line="INFO login request traceId=trace-3001 username=tester"),
        _entry(184, app="user-service", namespace="staging", env="staging", team="account", cluster="cluster-b", pod="user-69c4bb", line="WARN password retry threshold near limit traceId=trace-3001 username=tester"),
        _entry(188, app="user-service", namespace="staging", env="staging", team="account", cluster="cluster-b", pod="user-69c4bb", line="INFO login success traceId=trace-3001 username=tester"),
        _entry(220, app="gateway-service", namespace="prod", env="prod", team="edge", cluster="cluster-a", pod="gateway-6c9d8b", line="INFO health probe success component=loki-demo"),
        _entry(224, app="order-service", namespace="prod", env="prod", team="commerce", cluster="cluster-a", pod="order-7f7d6c", line="INFO batch settlement finished batchId=batch-20260602 count=32"),
        _entry(228, app="payment-service", namespace="prod", env="prod", team="finance", cluster="cluster-a", pod="payment-5b8d4f", line="WARN slow SQL detected traceId=trace-5001 sqlId=sql-19 elapsed=890ms"),
        _entry(232, app="payment-service", namespace="prod", env="prod", team="finance", cluster="cluster-a", pod="payment-5b8d4f", line="INFO reconciliation worker completed traceId=trace-5001"),
    ],
    key=lambda item: int(item["timestamp_ns"]),
)


def _copy_rows(rows: list[dict]) -> list[dict]:
    return [
        {
            "timestamp": row["timestamp"],
            "timestamp_ns": row["timestamp_ns"],
            "line": row["line"],
            "labels": dict(row["labels"]),
        }
        for row in rows
    ]


def _resolve_bounds(
    hours: float = 24,
    start_ns: Optional[int] = None,
    end_ns: Optional[int] = None,
) -> tuple[int, int]:
    now_ns = int(time.time() * 1e9)
    lower = start_ns if start_ns is not None else int(now_ns - hours * 3600 * 1e9)
    upper = end_ns if end_ns is not None else now_ns
    return lower, upper


def _matches_level(line: str, level: Optional[str]) -> bool:
    if not level:
        return True
    lowered = line.lower()
    if level in ("error", "err"):
        return bool(re.search(r"(error|exception|fatal|panic)", lowered))
    if level in ("warn", "warning"):
        return bool(re.search(r"(warn|warning)", lowered))
    if level == "info":
        return "info" in lowered
    if level == "debug":
        return "debug" in lowered
    return True


def _filter_rows(
    *,
    service: Optional[str] = None,
    hours: float = 24,
    level: Optional[str] = None,
    keyword: Optional[str] = None,
    start_ns: Optional[int] = None,
    end_ns: Optional[int] = None,
    label_filters: Optional[dict[str, str]] = None,
) -> list[dict]:
    lower, upper = _resolve_bounds(hours=hours, start_ns=start_ns, end_ns=end_ns)
    lowered_keyword = (keyword or "").lower().strip()
    rows: list[dict] = []
    for row in _DEMO_LOGS:
        ts_ns = int(row["timestamp_ns"])
        if ts_ns < lower or ts_ns > upper:
            continue
        labels = row["labels"]
        current_service = labels.get("app") or labels.get("job") or ""
        if service and current_service != service:
            continue
        if label_filters:
            if any(str(labels.get(label, "")) != str(value) for label, value in label_filters.items() if value not in (None, "")):
                continue
        if lowered_keyword and lowered_keyword not in row["line"].lower():
            continue
        if not _matches_level(row["line"], level):
            continue
        rows.append(row)
    return rows


def get_all_labels() -> list[str]:
    labels = set()
    for row in _DEMO_LOGS:
        labels.update(row["labels"].keys())
    return sorted(labels)


def get_label_values(label: str) -> list[str]:
    values = sorted({row["labels"].get(label, "") for row in _DEMO_LOGS if row["labels"].get(label)})
    return values


def get_series(match: Optional[str] = None) -> list[dict]:
    matcher_label = None
    matcher_exact = None
    matcher_regex = None
    if match:
        exact = re.fullmatch(r'\{([A-Za-z_][A-Za-z0-9_]*)="([^"]+)"\}', match)
        regex = re.fullmatch(r'\{([A-Za-z_][A-Za-z0-9_]*)=~"(.+)"\}', match)
        if exact:
            matcher_label = exact.group(1)
            matcher_exact = exact.group(2)
        elif regex:
            matcher_label = regex.group(1)
            matcher_regex = re.compile(regex.group(2))

    unique: dict[tuple[tuple[str, str], ...], dict] = {}
    for row in _DEMO_LOGS:
        labels = row["labels"]
        if matcher_label:
            current = labels.get(matcher_label, "")
            if matcher_exact is not None and current != matcher_exact:
                continue
            if matcher_regex is not None and not matcher_regex.search(current):
                continue
        key = tuple(sorted((key, str(value)) for key, value in labels.items()))
        unique.setdefault(key, dict(labels))
    return list(unique.values())


def query_logs(
    *,
    service: Optional[str] = None,
    hours: float = 24,
    limit: int = 5000,
    level: Optional[str] = None,
    keyword: Optional[str] = None,
    start_ns: Optional[int] = None,
    end_ns: Optional[int] = None,
    group_label: Optional[str] = None,
    group_value: Optional[str] = None,
) -> list[dict]:
    label_filters = {group_label: group_value} if group_label and group_value else None
    rows = _filter_rows(
        service=service,
        hours=hours,
        level=level,
        keyword=keyword,
        start_ns=start_ns,
        end_ns=end_ns,
        label_filters=label_filters,
    )
    rows.sort(key=lambda item: int(item["timestamp_ns"]), reverse=True)
    return _copy_rows(rows[:limit])


def query_logs_page(
    *,
    service: Optional[str] = None,
    hours: float = 24,
    page_size: int = 200,
    cursor_ns: Optional[int] = None,
    level: Optional[str] = None,
    keyword: Optional[str] = None,
    start_ns: Optional[int] = None,
    end_ns: Optional[int] = None,
    group_label: Optional[str] = None,
    group_value: Optional[str] = None,
) -> dict:
    effective_end_ns = (cursor_ns - 1) if cursor_ns is not None else end_ns
    rows = query_logs(
        service=service,
        hours=hours,
        limit=100000,
        level=level,
        keyword=keyword,
        start_ns=start_ns,
        end_ns=effective_end_ns,
        group_label=group_label,
        group_value=group_value,
    )
    page = rows[:page_size]
    has_more = len(rows) > page_size
    next_cursor_ns = int(page[-1]["timestamp_ns"]) if page and has_more else None
    return {"data": page, "has_more": has_more, "next_cursor_ns": next_cursor_ns}


def query_log_context(
    *,
    timestamp_ns: int,
    service: Optional[str] = None,
    line_prefix: Optional[str] = None,
    before: int = 10,
    after: int = 10,
    hours: float = 24,
    start_ns: Optional[int] = None,
    end_ns: Optional[int] = None,
    label_filters: Optional[dict[str, str]] = None,
) -> dict:
    rows = _filter_rows(
        service=service,
        hours=hours,
        start_ns=start_ns,
        end_ns=end_ns,
        label_filters=label_filters,
    )
    rows.sort(key=lambda item: int(item["timestamp_ns"]))

    anchor_idx = -1
    for idx, row in enumerate(rows):
        if int(row["timestamp_ns"]) != int(timestamp_ns):
            continue
        if not line_prefix or row["line"].startswith(line_prefix):
            anchor_idx = idx
            break

    if anchor_idx < 0:
        for idx, row in enumerate(rows):
            if int(row["timestamp_ns"]) == int(timestamp_ns):
                anchor_idx = idx
                break

    anchor_found = anchor_idx >= 0
    if anchor_found:
        start_idx = max(0, anchor_idx - before)
        end_idx = min(len(rows), anchor_idx + after + 1)
        data = _copy_rows(rows[start_idx:end_idx])
        return {
            "data": data,
            "anchor_index": anchor_idx - start_idx,
            "anchor_found": True,
            "before_count": anchor_idx - start_idx,
            "after_count": end_idx - anchor_idx - 1,
        }

    anchor_labels = dict(label_filters or {})
    if service and "app" not in anchor_labels:
        anchor_labels["app"] = service
    anchor_row = {
        "timestamp": _format_display_timestamp(timestamp_ns),
        "timestamp_ns": str(timestamp_ns),
        "line": line_prefix or "",
        "labels": anchor_labels,
    }
    return {
        "data": [anchor_row],
        "anchor_index": 0,
        "anchor_found": False,
        "before_count": 0,
        "after_count": 0,
    }


def count_errors_by_service(hours: float = 24) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in _filter_rows(hours=hours, level="error"):
        service = row["labels"].get("app") or row["labels"].get("job") or "unknown"
        counts[service] = counts.get(service, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))


def count_errors_by_group_service(group_label: str, hours: float = 24) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for row in _filter_rows(hours=hours, level="error"):
        labels = row["labels"]
        group_value = labels.get(group_label)
        service = labels.get("app") or labels.get("job") or "unknown"
        if not group_value:
            continue
        bucket = result.setdefault(group_value, {})
        bucket[service] = bucket.get(service, 0) + 1
    return result

