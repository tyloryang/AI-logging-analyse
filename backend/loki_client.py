"""Loki HTTP API v1 客户端"""
import time
from datetime import datetime, timezone
from typing import Optional
import httpx


class LokiClient:
    def __init__(self, base_url: str, username: str = "", password: str = ""):
        self.base_url = base_url.rstrip("/")
        self.auth = (username, password) if username else None
        self.timeout = httpx.Timeout(30.0)

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

    async def query_range(
        self,
        query: str,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        limit: int = 500,
        direction: str = "backward",
    ) -> list[dict]:
        """
        查询日志范围，返回日志条目列表
        每条: {"timestamp": str, "line": str, "labels": dict}
        """
        now = int(time.time() * 1e9)
        start = start_ts if start_ts else now - 86400 * int(1e9)
        end = end_ts if end_ts else now

        async with httpx.AsyncClient(timeout=self.timeout) as client:
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

        results = []
        for stream in data.get("data", {}).get("result", []):
            labels = stream.get("stream", {})
            for ts_ns, line in stream.get("values", []):
                ts_sec = int(ts_ns) / 1e9
                dt = datetime.fromtimestamp(ts_sec, tz=timezone.utc)
                results.append({
                    "timestamp": dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "timestamp_ns": ts_ns,
                    "line": line,
                    "labels": labels,
                })
        # 按时间倒序
        results.sort(key=lambda x: x["timestamp_ns"], reverse=True)
        return results

    async def _detect_service_label(self) -> str:
        """自动探测服务标签：优先用 app，没有则用 job"""
        labels = await self.get_all_labels()
        return "app" if "app" in labels else "job"

    async def query_logs(
        self,
        service: Optional[str] = None,
        hours: int = 24,
        limit: int = 1000,
        level: Optional[str] = None,
    ) -> list[dict]:
        """
        查询日志，自动适配 app / job 标签。
        level: None=全部, 'error'=错误级别, 'warn'=警告级别
        """
        now_ns = int(time.time() * 1e9)
        start_ns = now_ns - hours * 3600 * int(1e9)

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

        return await self.query_range(query, start_ns, now_ns, limit)

    async def query_error_logs(
        self,
        service: Optional[str] = None,
        hours: int = 24,
        limit: int = 1000,
    ) -> list[dict]:
        """查询错误日志（兼容旧调用）"""
        return await self.query_logs(service=service, hours=hours, limit=limit, level="error")

    async def count_errors_by_service(self, hours: int = 24) -> dict[str, int]:
        """统计各服务错误数"""
        logs = await self.query_error_logs(hours=hours, limit=2000)
        counts: dict[str, int] = {}
        for log in logs:
            svc = log["labels"].get("app") or log["labels"].get("job") or "unknown"
            counts[svc] = counts.get(svc, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))

    async def get_services(self) -> list[dict]:
        """获取服务列表及错误数"""
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
        return services
