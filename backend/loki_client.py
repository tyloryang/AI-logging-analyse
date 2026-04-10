"""Loki HTTP API v1 客户端"""
import re
import time
from datetime import datetime, timezone
from typing import Optional
import httpx
from cachetools import TTLCache

# 服务列表 / 错误统计缓存 60s，避免 Dashboard 频繁刷新触发大量 Loki 请求
_svc_cache:   TTLCache = TTLCache(maxsize=1, ttl=60)
_err_cache:   TTLCache = TTLCache(maxsize=8, ttl=60)


class LokiClient:
    def __init__(self, base_url: str, username: str = "", password: str = ""):
        self.base_url = base_url.rstrip("/")
        self.auth = (username, password) if username else None
        self.timeout      = httpx.Timeout(60.0)   # 常规查询
        self.scan_timeout = httpx.Timeout(120.0)  # 大量日志扫描（trace/聚类）

    def _headers(self) -> dict:
        return {"Content-Type": "application/json"}

    async def get_label_values(self, label: str = "app") -> list[str]:
        """获取指定 label 的所有值（服务列表）"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            kwargs = dict(
                url=f"{self.base_url}/loki/api/v1/label/{label}/values",
                headers=self._headers(),
                params={"start": str(int((time.time() - 86400) * 1e9))},
            )
            if self.auth:
                kwargs["auth"] = self.auth
            resp = await client.get(**kwargs)
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", [])

    async def get_all_labels(self) -> list[str]:
        """获取所有标签名"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            kwargs = dict(
                url=f"{self.base_url}/loki/api/v1/labels",
                headers=self._headers(),
            )
            if self.auth:
                kwargs["auth"] = self.auth
            resp = await client.get(**kwargs)
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", [])

    # Loki 服务端默认 max_entries_limit_per_query，超出会 400
    LOKI_PAGE_SIZE = 5000

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        query: str,
        start: int,
        end: int,
        limit: int,
        direction: str,
    ) -> list[dict]:
        """向 Loki 发送单次 query_range 请求，返回解析后的日志列表。"""
        kwargs = dict(
            url=f"{self.base_url}/loki/api/v1/query_range",
            headers=self._headers(),
            params={
                "query": query,
                "start": str(start),
                "end": str(end),
                "limit": str(limit),
                "direction": direction,
            },
        )
        if self.auth:
            kwargs["auth"] = self.auth
        resp = await client.get(**kwargs)
        resp.raise_for_status()
        data = resp.json()

        rows = []
        for stream in data.get("data", {}).get("result", []):
            labels = stream.get("stream", {})
            for ts_ns, line in stream.get("values", []):
                ts_sec = int(ts_ns) / 1e9
                dt = datetime.fromtimestamp(ts_sec, tz=timezone.utc)
                rows.append({
                    "timestamp": dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "timestamp_ns": ts_ns,
                    "line": line,
                    "labels": labels,
                })
        return rows

    async def query_range(
        self,
        query: str,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        limit: int = 5000,
        direction: str = "backward",
        use_scan_timeout: bool = False,
    ) -> list[dict]:
        """
        查询日志范围，返回日志条目列表（自动分页，突破 Loki 单次 5000 条限制）。
        每条: {"timestamp": str, "line": str, "labels": dict}
        use_scan_timeout: 大量扫描时使用更长的超时（trace/聚类等）
        """
        now = int(time.time() * 1e9)
        start = start_ts if start_ts else now - 86400 * int(1e9)
        end = end_ts if end_ts else now

        results: list[dict] = []
        remaining = limit
        cur_start, cur_end = start, end

        timeout = self.scan_timeout if use_scan_timeout else self.timeout
        async with httpx.AsyncClient(timeout=timeout) as client:
            while remaining > 0:
                page_limit = min(remaining, self.LOKI_PAGE_SIZE)
                page = await self._fetch_page(client, query, cur_start, cur_end, page_limit, direction)
                if not page:
                    break

                results.extend(page)
                remaining -= len(page)

                # 数据不足一页，说明已无更多数据
                if len(page) < page_limit:
                    break

                # 滑动时间窗口：backward 模式向更早时间延伸
                if direction == "backward":
                    oldest_ns = min(int(r["timestamp_ns"]) for r in page)
                    if oldest_ns <= cur_start:
                        break
                    cur_end = oldest_ns - 1
                else:
                    newest_ns = max(int(r["timestamp_ns"]) for r in page)
                    if newest_ns >= cur_end:
                        break
                    cur_start = newest_ns + 1

        results.sort(key=lambda x: x["timestamp_ns"], reverse=True)
        return results[:limit]

    async def _detect_service_label(self) -> str:
        """自动探测服务标签：优先用 app，没有则用 job"""
        labels = await self.get_all_labels()
        return "app" if "app" in labels else "job"

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
        """
        查询日志，自动适配 app / job 标签。
        level:    None=全部, 'error'=错误级别, 'warn'=警告级别
        keyword:  关键字过滤（不区分大小写）
        start_ns / end_ns: 自定义时间范围（纳秒时间戳），优先于 hours
        use_scan_timeout: 大量扫描时传 True，使用 scan_timeout（120s）
        """
        now_ns = int(time.time() * 1e9)
        s_ns = start_ns if start_ns is not None else int(now_ns - hours * 3600 * 1e9)
        e_ns = end_ns if end_ns is not None else now_ns

        svc_label = await self._detect_service_label()

        if service:
            base = f'{{{svc_label}="{service}"}}'
        else:
            base = f'{{{svc_label}=~".+"}}'

        if level in ("error", "err"):
            query = f'{base} |~ "(?i)(error|exception|fatal|panic)"'
        elif level in ("warn", "warning"):
            query = f'{base} |~ "(?i)(warn|warning)"'
        else:
            query = base

        if keyword:
            # re.escape() 产生的 \ 在 LogQL 双引号字符串中需再次转义为 \\
            # 否则 Loki 的 Go 字符串解析器会因无效转义序列返回 400
            safe_kw = re.escape(keyword).replace('\\', '\\\\')
            query += f' |~ "(?i){safe_kw}"'

        return await self.query_range(query, s_ns, e_ns, limit, use_scan_timeout=use_scan_timeout)

    async def query_error_logs(
        self,
        service: Optional[str] = None,
        hours: float = 24,
        limit: int = 5000,
    ) -> list[dict]:
        """查询错误日志（兼容旧调用）"""
        return await self.query_logs(service=service, hours=hours, limit=limit, level="error")

    async def count_errors_by_service(self, hours: float = 24) -> dict[str, int]:
        """统计各服务错误数（结果缓存 60s）"""
        cache_key = f"err_{hours}"
        if cache_key in _err_cache:
            return _err_cache[cache_key]
        logs = await self.query_error_logs(hours=hours, limit=10000)
        counts: dict[str, int] = {}
        for log in logs:
            svc = log["labels"].get("app") or log["labels"].get("job") or "unknown"
            counts[svc] = counts.get(svc, 0) + 1
        result = dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))
        _err_cache[cache_key] = result
        return result

    async def get_services(self) -> list[dict]:
        """获取服务列表及错误数（结果缓存 60s）"""
        if "services" in _svc_cache:
            return _svc_cache["services"]
        try:
            names = await self.get_label_values("app")
        except Exception:
            try:
                names = await self.get_label_values("job")
            except Exception:
                names = []

        error_counts = await self.count_errors_by_service()
        services = []
        for name in names:
            services.append({
                "name": name,
                "error_count": error_counts.get(name, 0),
            })
        services.sort(key=lambda x: x["error_count"], reverse=True)
        _svc_cache["services"] = services
        return services
