"""Loki HTTP API v1 client."""

from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timezone
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
_grouped_svc_cache: TTLCache = TTLCache(maxsize=1, ttl=60)


class LokiClient:
    LOKI_PAGE_SIZE = 5000

    def __init__(self, base_url: str, username: str = "", password: str = ""):
        self.base_url = base_url.rstrip("/")
        self.auth = (username, password) if username else None
        self.timeout = httpx.Timeout(60.0)
        self.scan_timeout = httpx.Timeout(120.0)

        client_kwargs: dict = {
            "limits": httpx.Limits(max_connections=20, max_keepalive_connections=10),
        }
        if self.auth:
            client_kwargs["auth"] = self.auth
        self._client = httpx.AsyncClient(**client_kwargs)

    def _headers(self) -> dict:
        return {"Content-Type": "application/json"}

    async def _request_json(
        self,
        path: str,
        *,
        params: Optional[dict] = None,
        timeout: Optional[httpx.Timeout] = None,
    ) -> dict:
        resp = await self._client.get(
            f"{self.base_url}{path}",
            headers=self._headers(),
            params=params,
            timeout=timeout or self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

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
                    ts_sec = int(ts_ns) / 1e9
                    dt = datetime.fromtimestamp(ts_sec, tz=timezone.utc)
                    rows.append(
                        {
                            "timestamp": dt.strftime("%Y-%m-%d %H:%M:%S"),
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
    ) -> list[dict]:
        now = int(time.time() * 1e9)
        start = start_ts if start_ts else now - 86400 * int(1e9)
        end = end_ts if end_ts else now

        results: list[dict] = []
        remaining = limit
        cur_start, cur_end = start, end
        timeout = self.scan_timeout if use_scan_timeout else self.timeout

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

    async def query_logs_page(
        self,
        service: Optional[str] = None,
        hours: float = 24,
        page_size: int = 200,
        cursor_ns: Optional[int] = None,
        level: Optional[str] = None,
        keyword: Optional[str] = None,
        start_ns: Optional[int] = None,
        end_ns: Optional[int] = None,
    ) -> dict:
        now_ns = int(time.time() * 1e9)
        s_ns = start_ns if start_ns is not None else int(now_ns - hours * 3600 * 1e9)
        e_ns = (cursor_ns - 1) if cursor_ns is not None else (end_ns if end_ns is not None else now_ns)

        svc_label = await self._detect_service_label()
        base = f'{{{svc_label}="{service}"}}' if service else f'{{{svc_label}=~".+"}}'

        if level in ("error", "err"):
            query = f'{base} |~ "(?i)(error|exception|fatal|panic)"'
        elif level in ("warn", "warning"):
            query = f'{base} |~ "(?i)(warn|warning)"'
        else:
            query = base

        if keyword:
            safe_kw = re.escape(keyword).replace("\\", "\\\\")
            query += f' |~ "(?i){safe_kw}"'

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
        hours: float = 24,
        limit: int = 5000,
        level: Optional[str] = None,
        keyword: Optional[str] = None,
        start_ns: Optional[int] = None,
        end_ns: Optional[int] = None,
        use_scan_timeout: bool = False,
    ) -> list[dict]:
        now_ns = int(time.time() * 1e9)
        s_ns = start_ns if start_ns is not None else int(now_ns - hours * 3600 * 1e9)
        e_ns = end_ns if end_ns is not None else now_ns

        svc_label = await self._detect_service_label()
        base = f'{{{svc_label}="{service}"}}' if service else f'{{{svc_label}=~".+"}}'

        if level in ("error", "err"):
            query = f'{base} |~ "(?i)(error|exception|fatal|panic)"'
        elif level in ("warn", "warning"):
            query = f'{base} |~ "(?i)(warn|warning)"'
        else:
            query = base

        if keyword:
            safe_kw = re.escape(keyword).replace("\\", "\\\\")
            query += f' |~ "(?i){safe_kw}"'

        return await self.query_range(query, s_ns, e_ns, limit, use_scan_timeout=use_scan_timeout)

    async def query_error_logs(
        self,
        service: Optional[str] = None,
        hours: float = 24,
        limit: int = 5000,
    ) -> list[dict]:
        return await self.query_logs(service=service, hours=hours, limit=limit, level="error")

    async def count_errors_by_service(self, hours: float = 24) -> dict[str, int]:
        cache_key = f"err_{hours}"
        if cache_key in _err_cache:
            return _err_cache[cache_key]

        logs = await self.query_error_logs(hours=hours, limit=10000)
        counts: dict[str, int] = {}
        for log in logs:
            svc = log["labels"].get("app") or log["labels"].get("job") or "unknown"
            counts[svc] = counts.get(svc, 0) + 1

        result = dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))
        _err_cache[cache_key] = result
        return result

    async def get_namespaces(self) -> list[str]:
        _, namespaces = await self._detect_namespace_label()
        return namespaces

    async def get_services_by_namespace(
        self,
        namespace: str,
        namespace_label: Optional[str] = None,
    ) -> list[str]:
        effective_namespace_label = namespace_label
        if not effective_namespace_label:
            effective_namespace_label, _ = await self._detect_namespace_label()
        if not effective_namespace_label:
            return []

        cache_key = f"{effective_namespace_label}:{namespace}"
        if cache_key in _namespace_services_cache:
            return _namespace_services_cache[cache_key]

        start_ns = int((time.time() - 86400) * 1e9)
        try:
            data = await self._request_json(
                "/loki/api/v1/series",
                params={
                    "match[]": f'{{{effective_namespace_label}="{namespace}"}}',
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

    async def get_grouped_services(self) -> list[dict]:
        if "grouped_services" in _grouped_svc_cache:
            return _grouped_svc_cache["grouped_services"]

        namespace_task = asyncio.create_task(self._detect_namespace_label())
        error_task = asyncio.create_task(self.count_errors_by_service())

        namespace_label, namespaces = await namespace_task
        try:
            error_counts = await error_task
        except Exception:
            error_counts = {}

        if not namespaces:
            services = await self.get_services()
            result = [{"namespace": "", "label": "鍏ㄩ儴鏈嶅姟", "services": services}]
            _grouped_svc_cache["grouped_services"] = result
            return result

        semaphore = asyncio.Semaphore(8)

        async def _build_group(namespace: str) -> Optional[dict]:
            async with semaphore:
                apps = await self.get_services_by_namespace(namespace, namespace_label=namespace_label)
            if not apps:
                return None
            services = [{"name": app, "error_count": error_counts.get(app, 0)} for app in apps]
            services.sort(key=lambda item: -item["error_count"])
            return {"namespace": namespace, "label": namespace, "services": services}

        grouped = await asyncio.gather(*(_build_group(namespace) for namespace in namespaces))
        result = [item for item in grouped if item]
        _grouped_svc_cache["grouped_services"] = result
        return result

    async def get_services(self) -> list[dict]:
        if "services" in _svc_cache:
            return _svc_cache["services"]

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

        error_counts = await self.count_errors_by_service()
        services = [{"name": name, "error_count": error_counts.get(name, 0)} for name in names]
        services.sort(key=lambda item: item["error_count"], reverse=True)
        _svc_cache["services"] = services
        return services
