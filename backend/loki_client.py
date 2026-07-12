"""Loki HTTP API v1 client."""

from __future__ import annotations

import asyncio
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from cachetools import TTLCache

# Short-lived caches keep the dashboard responsive without holding stale data
# for too long.
_svc_cache: TTLCache = TTLCache(maxsize=1, ttl=60)
_err_cache: TTLCache = TTLCache(maxsize=8, ttl=60)
_all_labels_cache: TTLCache = TTLCache(maxsize=1, ttl=300)
_label_values_cache: TTLCache = TTLCache(maxsize=32, ttl=300)
_service_label_cache: TTLCache = TTLCache(maxsize=1, ttl=300)
_namespace_label_cache: TTLCache = TTLCache(maxsize=1, ttl=300)
_namespace_services_cache: TTLCache = TTLCache(maxsize=128, ttl=120)
_namespace_service_map_cache: TTLCache = TTLCache(maxsize=2, ttl=120)
_grouped_svc_cache: TTLCache = TTLCache(maxsize=1, ttl=60)
_group_service_map_cache: TTLCache = TTLCache(maxsize=8, ttl=120)
_group_error_cache: TTLCache = TTLCache(maxsize=16, ttl=60)
# Stale-while-revalidate: keep the last successful error counts forever so the
# dashboard can answer instantly while a background task refreshes the data.
_err_stale: dict[str, dict[str, int]] = {}
_err_refresh_tasks: dict[str, "asyncio.Task"] = {}
_DISPLAY_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")


def _demo_mode() -> bool:
    return os.getenv("LOKI_DEMO_MODE", "").lower() in ("1", "true", "yes")


def _format_display_timestamp(ts_ns: str | int) -> str:
    dt = datetime.fromtimestamp(int(ts_ns) / 1e9, tz=timezone.utc).astimezone(_DISPLAY_TZ)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


class LokiClient:
    LOKI_PAGE_SIZE = 5000

    def __init__(self, base_url: str, username: str = "", password: str = ""):
        self.base_url = base_url.rstrip("/")
        self.auth = (username, password) if username else None
        self.timeout = httpx.Timeout(60.0)
        self.scan_timeout = httpx.Timeout(120.0)
        # 上下文查询是交互操作(用户点一条日志等着看), 用短超时快速失败,
        # 路由层有降级重试 + 最小兜底, 比让用户干等 120s 好
        self.context_timeout = httpx.Timeout(15.0)

        client_kwargs: dict = {
            "limits": httpx.Limits(max_connections=20, max_keepalive_connections=10),
            # 关键: 禁用环境代理。Loki 是内网服务, 若部署环境设了 HTTP_PROXY/ALL_PROXY
            # (国内环境常见), httpx 默认 trust_env=True 会把每个内网请求都塞进代理,
            # 代理连不上内网 IP → 每请求固定 2-4s 延迟, context 多子查询叠加到 20s+。
            "trust_env": False,
        }
        if self.auth:
            client_kwargs["auth"] = self.auth
        self._client = httpx.AsyncClient(**client_kwargs)

    def _headers(self) -> dict:
        return {"Content-Type": "application/json"}

    @staticmethod
    def _escape_label_value(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _format_logql_duration(hours: float) -> str:
        total_seconds = max(int(hours * 3600), 1)
        if total_seconds % 3600 == 0:
            return f"{total_seconds // 3600}h"
        if total_seconds % 60 == 0:
            return f"{total_seconds // 60}m"
        return f"{total_seconds}s"

    def _build_log_query(
        self,
        *,
        service_label: str,
        service: Optional[str] = None,
        services: Optional[list[str]] = None,
        level: Optional[str] = None,
        keyword: Optional[str] = None,
        keywords: Optional[list[str]] = None,
        keyword_mode: str = "and",
        exclude_keywords: Optional[list[str]] = None,
        label_filters: Optional[dict[str, str]] = None,
    ) -> str:
        # 归一化服务列表：单值 service 兼容旧参数，与 services 合并去重
        svc_list: list[str] = []
        if services:
            svc_list.extend(s for s in services if s and s.strip())
        if service and service.strip() and service not in svc_list:
            svc_list.append(service)

        selector_parts: list[str] = []
        if len(svc_list) == 1:
            selector_parts.append(f'{service_label}="{self._escape_label_value(svc_list[0])}"')
        elif len(svc_list) > 1:
            # LogQL regex alternation：{app=~"a|b|c"}
            joined = "|".join(re.escape(s) for s in svc_list)
            # 反斜杠需要在 LogQL 字符串里再转义一次
            joined = joined.replace("\\", "\\\\")
            selector_parts.append(f'{service_label}=~"{joined}"')
        else:
            selector_parts.append(f'{service_label}=~".+"')

        for label, value in (label_filters or {}).items():
            if not label:
                continue
            # 支持三种输入：str / list[str]
            # 单值 → label="v"；多值 → label=~"a|b|c"
            if isinstance(value, (list, tuple, set)):
                vals = [str(v) for v in value if v not in (None, "")]
            elif value in (None, ""):
                continue
            else:
                vals = [str(value)]
            if not vals:
                continue
            if len(vals) == 1:
                selector_parts.append(f'{label}="{self._escape_label_value(vals[0])}"')
            else:
                joined = "|".join(re.escape(v) for v in vals).replace("\\", "\\\\")
                selector_parts.append(f'{label}=~"{joined}"')

        query = "{" + ",".join(selector_parts) + "}"

        if level in ("error", "err"):
            query += ' |~ "(?i)(error|exception|fatal|panic)"'
        elif level in ("warn", "warning"):
            query += ' |~ "(?i)(warn|warning)"'

        # 关键字：keywords 列表优先；否则 keyword 单值降级
        kw_list = [k for k in (keywords or []) if k and k.strip()]
        if not kw_list and keyword and keyword.strip():
            kw_list = [keyword.strip()]

        if kw_list:
            mode = (keyword_mode or "and").lower()
            if mode == "or" and len(kw_list) > 1:
                joined = "|".join(re.escape(k).replace("\\", "\\\\") for k in kw_list)
                query += f' |~ "(?i)({joined})"'
            else:
                for kw in kw_list:
                    safe_kw = re.escape(kw).replace("\\", "\\\\")
                    query += f' |~ "(?i){safe_kw}"'

        for ex in (exclude_keywords or []):
            if not ex or not ex.strip():
                continue
            safe_ex = re.escape(ex).replace("\\", "\\\\")
            query += f' !~ "(?i){safe_ex}"'

        return query

    async def _request_json(
        self,
        path: str,
        *,
        params: Optional[dict] = None,
        timeout: Optional[httpx.Timeout] = None,
    ) -> dict:
        if _demo_mode():
            import loki_mock

            if path == "/loki/api/v1/labels":
                return {"status": "success", "data": loki_mock.get_all_labels()}

            label_match = re.fullmatch(r"/loki/api/v1/label/([^/]+)/values", path)
            if label_match:
                return {"status": "success", "data": loki_mock.get_label_values(label_match.group(1))}

            if path == "/loki/api/v1/series":
                match_expr = None
                if params:
                    match_expr = params.get("match[]")
                return {"status": "success", "data": loki_mock.get_series(match_expr)}

        resp = await self._client.get(
            f"{self.base_url}{path}",
            headers=self._headers(),
            params=params,
            timeout=timeout or self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    async def _instant_query(
        self,
        query: str,
        *,
        ts_ns: Optional[int] = None,
        timeout: Optional[httpx.Timeout] = None,
    ) -> dict:
        params = {"query": query}
        if ts_ns is not None:
            params["time"] = str(ts_ns)
        return await self._request_json(
            "/loki/api/v1/query",
            params=params,
            timeout=timeout or self.timeout,
        )

    async def get_label_values(self, label: str = "app") -> list[str]:
        cache_key = f"label:{label}"
        if cache_key in _label_values_cache:
            return _label_values_cache[cache_key]

        data = await self._request_json(
            f"/loki/api/v1/label/{label}/values",
            params={"start": str(int((time.time() - 86400) * 1e9))},
        )
        values = data.get("data", [])
        _label_values_cache[cache_key] = values
        return values

    async def get_all_labels(self) -> list[str]:
        if "all_labels" in _all_labels_cache:
            return _all_labels_cache["all_labels"]

        data = await self._request_json("/loki/api/v1/labels")
        labels = data.get("data", [])
        _all_labels_cache["all_labels"] = labels
        return labels

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        query: str,
        start: int,
        end: int,
        limit: int,
        direction: str,
        timeout: httpx.Timeout,
    ) -> list[dict]:
        cur_limit = limit
        for attempt in range(3):
            resp = await client.get(
                f"{self.base_url}/loki/api/v1/query_range",
                headers=self._headers(),
                params={
                    "query": query,
                    "start": str(start),
                    "end": str(end),
                    "limit": str(cur_limit),
                    "direction": direction,
                },
                timeout=timeout,
            )

            if resp.status_code in (400, 413) and attempt < 2:
                body = resp.text.lower()
                if any(k in body for k in ("too many", "limit", "size", "large", "bytes")):
                    cur_limit = max(50, cur_limit // 2)
                    continue
            resp.raise_for_status()

            data = resp.json()
            rows: list[dict] = []
            for stream in data.get("data", {}).get("result", []):
                labels = stream.get("stream", {})
                for ts_ns, line in stream.get("values", []):
                    rows.append(
                        {
                            "timestamp": _format_display_timestamp(ts_ns),
                            "timestamp_ns": ts_ns,
                            "line": line,
                            "labels": labels,
                        }
                    )
            return rows
        return []

    async def query_range(
        self,
        query: str,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        limit: int = 5000,
        direction: str = "backward",
        use_scan_timeout: bool = False,
        timeout_override: Optional[httpx.Timeout] = None,
    ) -> list[dict]:
        now = int(time.time() * 1e9)
        start = start_ts if start_ts else now - 86400 * int(1e9)
        end = end_ts if end_ts else now

        results: list[dict] = []
        remaining = limit
        cur_start, cur_end = start, end
        timeout = timeout_override or (self.scan_timeout if use_scan_timeout else self.timeout)

        while remaining > 0:
            page_limit = min(remaining, self.LOKI_PAGE_SIZE)
            page = await self._fetch_page(
                self._client,
                query,
                cur_start,
                cur_end,
                page_limit,
                direction,
                timeout,
            )
            if not page:
                break

            results.extend(page)
            remaining -= len(page)

            if len(page) < page_limit:
                break

            if direction == "backward":
                oldest_ns = min(int(row["timestamp_ns"]) for row in page)
                if oldest_ns <= cur_start:
                    break
                cur_end = oldest_ns - 1
            else:
                newest_ns = max(int(row["timestamp_ns"]) for row in page)
                if newest_ns >= cur_end:
                    break
                cur_start = newest_ns + 1

        results.sort(key=lambda item: item["timestamp_ns"], reverse=True)
        return results[:limit]

    async def _detect_service_label(self) -> str:
        if "service_label" in _service_label_cache:
            return _service_label_cache["service_label"]

        labels = await self.get_all_labels()
        label = "app" if "app" in labels else "job"
        _service_label_cache["service_label"] = label
        return label

    async def _detect_namespace_label(self) -> tuple[Optional[str], list[str]]:
        cached_label = _namespace_label_cache.get("namespace_label")
        if cached_label:
            try:
                values = await self.get_label_values(cached_label)
                if values:
                    return cached_label, sorted(values)
            except Exception:
                pass
            _namespace_label_cache.pop("namespace_label", None)

        for label in ("namespace", "k8s_namespace_name", "kubernetes_namespace"):
            try:
                values = await self.get_label_values(label)
            except Exception:
                continue
            if values:
                namespaces = sorted(values)
                _namespace_label_cache["namespace_label"] = label
                return label, namespaces
        return None, []

    async def _resolve_group_label(self, group_label: Optional[str]) -> Optional[str]:
        if not group_label:
            return None

        normalized = group_label.strip()
        if not normalized:
            return None

        if normalized in ("namespace", "k8s_namespace_name", "kubernetes_namespace"):
            namespace_label, _ = await self._detect_namespace_label()
            if namespace_label:
                return namespace_label

        labels = await self.get_all_labels()
        if normalized in labels:
            return normalized

        return None

    async def query_logs_page(
        self,
        service: Optional[str] = None,
        services: Optional[list[str]] = None,
        hours: float = 24,
        page_size: int = 200,
        cursor_ns: Optional[int] = None,
        level: Optional[str] = None,
        keyword: Optional[str] = None,
        keywords: Optional[list[str]] = None,
        keyword_mode: str = "and",
        exclude_keywords: Optional[list[str]] = None,
        start_ns: Optional[int] = None,
        end_ns: Optional[int] = None,
        group_label: Optional[str] = None,
        group_value: Optional[str] = None,
        extra_label_filters: Optional[dict[str, str]] = None,
    ) -> dict:
        if _demo_mode():
            import loki_mock

            return loki_mock.query_logs_page(
                service=service,
                hours=hours,
                page_size=page_size,
                cursor_ns=cursor_ns,
                level=level,
                keyword=keyword,
                start_ns=start_ns,
                end_ns=end_ns,
                group_label=group_label,
                group_value=group_value,
            )

        now_ns = int(time.time() * 1e9)
        s_ns = start_ns if start_ns is not None else int(now_ns - hours * 3600 * 1e9)
        e_ns = (cursor_ns - 1) if cursor_ns is not None else (end_ns if end_ns is not None else now_ns)

        svc_label = await self._detect_service_label()
        # value 可以是 str 或 list[str]；builder 内部会决定 = 或 =~ 生成
        label_filters: dict[str, object] = {}
        if extra_label_filters:
            for k, v in extra_label_filters.items():
                if not k or v in (None, "", []):
                    continue
                resolved = await self._resolve_group_label(k) or k
                label_filters[resolved] = v
        resolved_group_label = await self._resolve_group_label(group_label)
        if resolved_group_label and group_value and resolved_group_label not in label_filters:
            label_filters[resolved_group_label] = group_value
        query = self._build_log_query(
            service_label=svc_label,
            service=service,
            services=services,
            level=level,
            keyword=keyword,
            keywords=keywords,
            keyword_mode=keyword_mode,
            exclude_keywords=exclude_keywords,
            label_filters=label_filters or None,
        )

        safe_size = min(page_size, self.LOKI_PAGE_SIZE)
        rows = await self._fetch_page(
            self._client,
            query,
            s_ns,
            e_ns,
            safe_size,
            "backward",
            self.timeout,
        )

        rows.sort(key=lambda item: item["timestamp_ns"], reverse=True)
        has_more = len(rows) >= safe_size
        next_cursor = int(rows[-1]["timestamp_ns"]) if rows and has_more else None
        return {"data": rows, "has_more": has_more, "next_cursor_ns": next_cursor}

    async def query_logs(
        self,
        service: Optional[str] = None,
        services: Optional[list[str]] = None,
        hours: float = 24,
        limit: int = 5000,
        level: Optional[str] = None,
        keyword: Optional[str] = None,
        keywords: Optional[list[str]] = None,
        keyword_mode: str = "and",
        exclude_keywords: Optional[list[str]] = None,
        start_ns: Optional[int] = None,
        end_ns: Optional[int] = None,
        use_scan_timeout: bool = False,
        group_label: Optional[str] = None,
        group_value: Optional[str] = None,
        extra_label_filters: Optional[dict[str, str]] = None,
    ) -> list[dict]:
        if _demo_mode():
            import loki_mock

            return loki_mock.query_logs(
                service=service,
                hours=hours,
                limit=limit,
                level=level,
                keyword=keyword,
                start_ns=start_ns,
                end_ns=end_ns,
                group_label=group_label,
                group_value=group_value,
            )

        now_ns = int(time.time() * 1e9)
        s_ns = start_ns if start_ns is not None else int(now_ns - hours * 3600 * 1e9)
        e_ns = end_ns if end_ns is not None else now_ns

        svc_label = await self._detect_service_label()
        label_filters: dict[str, str] = {}
        if extra_label_filters:
            for k, v in extra_label_filters.items():
                if not k or v in (None, ""):
                    continue
                resolved = await self._resolve_group_label(k) or k
                label_filters[resolved] = str(v)
        resolved_group_label = await self._resolve_group_label(group_label)
        if resolved_group_label and group_value:
            label_filters.setdefault(resolved_group_label, group_value)
        query = self._build_log_query(
            service_label=svc_label,
            service=service,
            services=services,
            level=level,
            keyword=keyword,
            keywords=keywords,
            keyword_mode=keyword_mode,
            exclude_keywords=exclude_keywords,
            label_filters=label_filters or None,
        )

        return await self.query_range(query, s_ns, e_ns, limit, use_scan_timeout=use_scan_timeout)

    async def query_log_context(
        self,
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
        if _demo_mode():
            import loki_mock

            return loki_mock.query_log_context(
                timestamp_ns=timestamp_ns,
                service=service,
                line_prefix=line_prefix,
                before=before,
                after=after,
                hours=hours,
                start_ns=start_ns,
                end_ns=end_ns,
                label_filters=label_filters,
            )

        now_ns = int(time.time() * 1e9)
        lower_bound = start_ns if start_ns is not None else int(now_ns - hours * 3600 * 1e9)
        upper_bound = end_ns if end_ns is not None else now_ns

        svc_label = await self._detect_service_label()
        normalized_filters: dict[str, str] = {}
        for label, value in (label_filters or {}).items():
            if not label or value in (None, ""):
                continue
            if label.startswith("__") or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", label):
                continue
            normalized_filters[label] = str(value)

        if not service:
            service = normalized_filters.get(svc_label) or None
        normalized_filters.pop(svc_label, None)

        if not service and not normalized_filters:
            raise ValueError("missing stream labels for context lookup")

        query = self._build_log_query(
            service_label=svc_label,
            service=service,
            label_filters=normalized_filters or None,
        )

        # 上下文日志绝大多数落在锚点前后几分钟内: 先并行查『近窗』(锚点 ±30min),
        # 只有不满才并行扩查『远窗』补足 —— Loki 扫描量比直接扫全窗低一个量级,
        # 且 anchor/before/after 三路并行, 总耗时从三者之和降为最大值。
        NEAR_WINDOW_NS = int(30 * 60 * 1e9)
        near_lower = max(lower_bound, timestamp_ns - NEAR_WINDOW_NS)
        near_upper = min(upper_bound, timestamp_ns + NEAR_WINDOW_NS)

        async def _fetch(start, end, limit, direction):
            if limit <= 0 or start > end:
                return []
            return await self.query_range(
                query, start, end, limit,
                direction=direction,
                timeout_override=self.context_timeout,
            )

        anchor_rows, before_rows, after_rows = await asyncio.gather(
            _fetch(timestamp_ns, timestamp_ns, max(before + after + 1, 20), "forward"),
            _fetch(near_lower, timestamp_ns - 1, before, "backward"),
            _fetch(timestamp_ns + 1, near_upper, after, "forward"),
        )

        # 近窗不满且还有更远的窗口 → 并行补足两侧
        need_before = before - len(before_rows) if near_lower > lower_bound else 0
        need_after = after - len(after_rows) if near_upper < upper_bound else 0
        if need_before > 0 or need_after > 0:
            far_before, far_after = await asyncio.gather(
                _fetch(lower_bound, near_lower - 1, need_before, "backward"),
                _fetch(near_upper + 1, upper_bound, need_after, "forward"),
            )
            before_rows = far_before + before_rows
            after_rows = after_rows + far_after

        anchor_rows.sort(key=lambda item: int(item["timestamp_ns"]))
        before_rows.sort(key=lambda item: int(item["timestamp_ns"]))
        before_rows = before_rows[-before:] if before > 0 else []
        after_rows.sort(key=lambda item: int(item["timestamp_ns"]))
        after_rows = after_rows[:after] if after > 0 else []

        anchor = None
        if line_prefix:
            anchor = next((row for row in anchor_rows if row["line"].startswith(line_prefix)), None)
        if anchor is None and anchor_rows:
            anchor = anchor_rows[0]

        anchor_found = anchor is not None
        if anchor is None:
            anchor_labels = dict(normalized_filters)
            if service:
                anchor_labels[svc_label] = service
            anchor = {
                "timestamp": _format_display_timestamp(timestamp_ns),
                "timestamp_ns": str(timestamp_ns),
                "line": line_prefix or "",
                "labels": anchor_labels,
            }

        rows = before_rows + [anchor] + after_rows
        return {
            "data": rows,
            "anchor_index": len(before_rows),
            "anchor_found": anchor_found,
            "before_count": len(before_rows),
            "after_count": len(after_rows),
        }

    async def query_error_logs(
        self,
        service: Optional[str] = None,
        hours: float = 24,
        limit: int = 5000,
        group_label: Optional[str] = None,
        group_value: Optional[str] = None,
    ) -> list[dict]:
        return await self.query_logs(
            service=service,
            hours=hours,
            limit=limit,
            level="error",
            group_label=group_label,
            group_value=group_value,
        )

    async def count_errors_by_service(self, hours: float = 24) -> dict[str, int]:
        if _demo_mode():
            import loki_mock

            result = loki_mock.count_errors_by_service(hours=hours)
            _err_cache[f"err_{hours}"] = result
            return result

        cache_key = f"err_{hours}"
        if cache_key in _err_cache:
            return _err_cache[cache_key]

        svc_label = await self._detect_service_label()
        window = self._format_logql_duration(hours)
        query = (
            f'sum by ({svc_label}) ('
            f'count_over_time('
            f'{self._build_log_query(service_label=svc_label, level="error")}'
            f' [{window}]'
            f')'
            f')'
        )

        counts: dict[str, int] = {}
        try:
            data = await self._instant_query(query, timeout=self.scan_timeout)
            for item in data.get("data", {}).get("result", []):
                metric = item.get("metric", {})
                value = item.get("value", [])
                svc = metric.get(svc_label) or metric.get("app") or metric.get("job") or "unknown"
                if len(value) >= 2:
                    counts[svc] = int(float(value[1]))
        except Exception:
            logs = await self.query_error_logs(hours=hours, limit=10000)
            for log in logs:
                svc = log["labels"].get("app") or log["labels"].get("job") or "unknown"
                counts[svc] = counts.get(svc, 0) + 1

        result = dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))
        _err_cache[cache_key] = result
        _err_stale[cache_key] = result
        return result

    def _spawn_err_refresh(self, hours: float) -> "asyncio.Task":
        """启动（或复用）一个后台错误计数刷新任务，避免并发重复扫描。"""
        cache_key = f"err_{hours}"
        task = _err_refresh_tasks.get(cache_key)
        if task is not None and not task.done():
            return task

        async def _refresh() -> dict[str, int]:
            try:
                return await self.count_errors_by_service(hours=hours)
            except Exception:
                return _err_stale.get(cache_key, {})
            finally:
                _err_refresh_tasks.pop(cache_key, None)

        task = asyncio.create_task(_refresh())
        _err_refresh_tasks[cache_key] = task
        return task

    async def count_errors_by_service_fast(
        self, hours: float = 24, budget: float = 15.0
    ) -> dict[str, int]:
        """错误计数的限时版本：budget 秒内拿不到就返回上次成功结果（或空），
        同时让真实统计在后台继续跑，下次请求即可命中缓存。"""
        cache_key = f"err_{hours}"
        if cache_key in _err_cache:
            return _err_cache[cache_key]
        task = self._spawn_err_refresh(hours)
        try:
            result = await asyncio.wait_for(asyncio.shield(task), timeout=budget)
            return result if isinstance(result, dict) else _err_stale.get(cache_key, {})
        except (asyncio.TimeoutError, Exception):
            return _err_stale.get(cache_key, {})

    async def count_errors_by_group_service(
        self,
        group_label: str,
        hours: float = 24,
    ) -> dict[str, dict[str, int]]:
        if _demo_mode():
            import loki_mock

            return loki_mock.count_errors_by_group_service(group_label, hours=hours)

        resolved_group_label = await self._resolve_group_label(group_label)
        if not resolved_group_label:
            return {}

        svc_label = await self._detect_service_label()
        if resolved_group_label == svc_label:
            return {}

        cache_key = f"{resolved_group_label}:{hours}"
        if cache_key in _group_error_cache:
            return _group_error_cache[cache_key]

        window = self._format_logql_duration(hours)
        query = (
            f"sum by ({resolved_group_label}, {svc_label}) ("
            f"count_over_time("
            f'{self._build_log_query(service_label=svc_label, level="error")}'
            f" [{window}]"
            f")"
            f")"
        )

        result: dict[str, dict[str, int]] = {}
        try:
            data = await self._instant_query(query, timeout=self.scan_timeout)
            for item in data.get("data", {}).get("result", []):
                metric = item.get("metric", {})
                value = item.get("value", [])
                group_value = metric.get(resolved_group_label)
                service_name = metric.get(svc_label) or metric.get("app") or metric.get("job")
                if not group_value or not service_name or len(value) < 2:
                    continue
                result.setdefault(group_value, {})[service_name] = int(float(value[1]))
        except Exception:
            logs = await self.query_error_logs(hours=hours, limit=10000)
            for log in logs:
                labels = log.get("labels", {})
                group_value = labels.get(resolved_group_label)
                service_name = labels.get(svc_label) or labels.get("app") or labels.get("job")
                if not group_value or not service_name:
                    continue
                bucket = result.setdefault(group_value, {})
                bucket[service_name] = bucket.get(service_name, 0) + 1

        _group_error_cache[cache_key] = result
        return result

    async def get_namespaces(self) -> list[str]:
        _, namespaces = await self._detect_namespace_label()
        return namespaces

    async def get_services_by_namespace(
        self,
        namespace: str,
        namespace_label: Optional[str] = None,
    ) -> list[str]:
        effective_namespace_label = namespace_label or "namespace"
        resolved_group_label = await self._resolve_group_label(effective_namespace_label)
        if not resolved_group_label:
            return []
        return await self.get_services_by_group(resolved_group_label, namespace)

    async def _get_namespace_service_map(self, namespace_label: str) -> dict[str, list[str]]:
        return await self._get_service_map_by_group_label(namespace_label)

    async def get_services_by_group(
        self,
        group_label: str,
        group_value: str,
    ) -> list[str]:
        resolved_group_label = await self._resolve_group_label(group_label)
        if not resolved_group_label:
            return []

        cache_key = f"{resolved_group_label}:{group_value}"
        if cache_key in _namespace_services_cache:
            return _namespace_services_cache[cache_key]

        service_map = await self._get_service_map_by_group_label(resolved_group_label)
        if service_map:
            services = service_map.get(group_value, [])
            _namespace_services_cache[cache_key] = services
            return services

        start_ns = int((time.time() - 86400) * 1e9)
        try:
            data = await self._request_json(
                "/loki/api/v1/series",
                params={
                    "match[]": f'{{{resolved_group_label}="{self._escape_label_value(group_value)}"}}',
                    "start": str(start_ns),
                },
            )
        except Exception:
            return []

        preferred_label = await self._detect_service_label()
        candidate_labels: list[str] = []
        for label in (preferred_label, "app", "container", "job"):
            if label not in candidate_labels:
                candidate_labels.append(label)

        services = sorted(
            {
                series.get(label, "")
                for series in data.get("data", [])
                for label in candidate_labels
                if series.get(label)
            }
        )
        _namespace_services_cache[cache_key] = services
        return services

    async def _get_service_map_by_group_label(self, group_label: str) -> dict[str, list[str]]:
        resolved_group_label = await self._resolve_group_label(group_label)
        if not resolved_group_label:
            return {}

        preferred_label = await self._detect_service_label()
        cache_key = f"{resolved_group_label}:{preferred_label}"
        if cache_key in _group_service_map_cache:
            return _group_service_map_cache[cache_key]

        start_ns = int((time.time() - 86400) * 1e9)
        try:
            data = await self._request_json(
                "/loki/api/v1/series",
                params={
                    "match[]": f"{{{resolved_group_label}=~\".+\"}}",
                    "start": str(start_ns),
                },
                timeout=self.scan_timeout,
            )
        except Exception:
            return {}

        candidate_labels: list[str] = []
        for label in (preferred_label, "app", "container", "job"):
            if label not in candidate_labels:
                candidate_labels.append(label)

        grouped: dict[str, set[str]] = {}
        for series in data.get("data", []):
            current_group_value = series.get(resolved_group_label)
            if not current_group_value:
                continue
            service_name = ""
            for label in candidate_labels:
                if series.get(label):
                    service_name = series[label]
                    break
            if not service_name:
                continue
            grouped.setdefault(current_group_value, set()).add(service_name)

        result = {value: sorted(services) for value, services in grouped.items()}
        _group_service_map_cache[cache_key] = result
        return result

    def _is_recommended_group_label(
        self,
        label: str,
        service_label: str,
        namespace_label: Optional[str],
    ) -> bool:
        if label == service_label:
            return False
        if namespace_label and label == namespace_label:
            return True

        lowered = label.lower()
        if any(token in lowered for token in ("pod", "instance", "filename", "stream", "trace", "container_id")):
            return False

        return any(
            token in lowered
            for token in (
                "namespace",
                "env",
                "cluster",
                "team",
                "biz",
                "domain",
                "owner",
                "project",
                "component",
                "part_of",
                "release",
            )
        )

    async def get_label_inventory(self) -> dict:
        labels = sorted(await self.get_all_labels())
        service_label = await self._detect_service_label()
        namespace_label, _ = await self._detect_namespace_label()

        preferred_order = [service_label]
        if namespace_label and namespace_label not in preferred_order:
            preferred_order.append(namespace_label)
        for label in ("env", "cluster", "team", "biz", "domain", "owner", "project"):
            if label not in preferred_order:
                preferred_order.append(label)

        priority = {label: idx for idx, label in enumerate(preferred_order)}
        labels.sort(key=lambda item: (priority.get(item, len(priority) + 1), item))

        items = [
            {
                "name": label,
                "role": (
                    "service"
                    if label == service_label
                    else "namespace"
                    if namespace_label and label == namespace_label
                    else "group"
                    if self._is_recommended_group_label(label, service_label, namespace_label)
                    else "generic"
                ),
                "groupable": self._is_recommended_group_label(label, service_label, namespace_label),
            }
            for label in labels
        ]

        group_options = [{"value": item["name"], "label": item["name"]} for item in items if item["groupable"]]
        if namespace_label and not any(option["value"] == namespace_label for option in group_options):
            group_options.insert(0, {"value": namespace_label, "label": namespace_label})

        return {
            "data": items,
            "group_options": group_options,
            "default_group_by": namespace_label or "",
            "service_label": service_label,
        }

    async def get_grouped_services(
        self,
        group_label: Optional[str] = None,
        with_errors: bool = True,
    ) -> list[dict]:
        """按 namespace/env/team 等标签分组返回服务。with_errors=False 时跳过
        所有错误统计查询，毫秒级返回（前端首屏快路径）。"""
        resolved_group_label = await self._resolve_group_label(group_label) if group_label else None
        cache_key = f"grouped_services:{resolved_group_label or 'default'}:{'full' if with_errors else 'fast'}"
        if cache_key in _grouped_svc_cache:
            return _grouped_svc_cache[cache_key]

        if not resolved_group_label:
            resolved_group_label, group_values = await self._detect_namespace_label()
        else:
            group_values = await self.get_label_values(resolved_group_label)

        if not resolved_group_label or not group_values:
            services = await self.get_services(with_errors=with_errors)
            result = [{"key": "", "label": "All Services", "group_label": "", "services": services}]
            _grouped_svc_cache[cache_key] = result
            return result

        service_map = await self._get_service_map_by_group_label(resolved_group_label)

        if with_errors:
            group_error_counts_task = asyncio.create_task(self.count_errors_by_group_service(resolved_group_label))
            fallback_error_counts_task = asyncio.create_task(self.count_errors_by_service_fast())
            try:
                group_error_counts = await asyncio.wait_for(group_error_counts_task, timeout=20)
            except (asyncio.TimeoutError, Exception):
                group_error_counts = {}
            try:
                fallback_error_counts = await fallback_error_counts_task
            except Exception:
                fallback_error_counts = {}
        else:
            group_error_counts = {}
            fallback_error_counts = {}

        result: list[dict] = []
        for group_value in sorted(group_values):
            apps = service_map.get(group_value, [])
            if not apps:
                continue

            services = []
            for app in apps:
                error_count = group_error_counts.get(group_value, {}).get(app)
                if error_count is None:
                    error_count = fallback_error_counts.get(app, 0)
                services.append(
                    {
                        "name": app,
                        "error_count": error_count,
                        "group_label": resolved_group_label,
                        "group_value": group_value,
                    }
                )
            services.sort(key=lambda item: (-item["error_count"], item["name"]))
            result.append(
                {
                    "key": group_value,
                    "label": group_value,
                    "group_label": resolved_group_label,
                    "services": services,
                }
            )

        _grouped_svc_cache[cache_key] = result
        return result

    async def get_services(self, with_errors: bool = True) -> list[dict]:
        """获取服务列表。with_errors=False 时跳过错误统计（毫秒级返回，
        前端可分两步加载：先快速展示服务名，统计稍后再补）。"""
        # 完整结果（含 error_count）有独立缓存 key，避免污染只要名字的快速路径
        cache_key = "services" if with_errors else "services_names"
        if cache_key in _svc_cache:
            return _svc_cache[cache_key]

        label = await self._detect_service_label()
        try:
            names = await self.get_label_values(label)
        except Exception:
            fallback = "job" if label == "app" else "app"
            try:
                names = await self.get_label_values(fallback)
                _service_label_cache["service_label"] = fallback
            except Exception:
                names = []

        if not with_errors:
            # 快速路径：只返回服务名，按字母排序，error_count 占位 0
            services_only = [{"name": name, "error_count": 0} for name in sorted(names)]
            _svc_cache[cache_key] = services_only
            return services_only

        # 完整路径：计错误数并按错误数降序排
        error_counts = await self.count_errors_by_service_fast()
        services = [{"name": name, "error_count": error_counts.get(name, 0)} for name in names]
        services.sort(key=lambda item: item["error_count"], reverse=True)
        _svc_cache[cache_key] = services
        return services
