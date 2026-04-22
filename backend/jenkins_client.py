"""Jenkins REST API 客户端（基于 httpx，无外部依赖）。"""
import logging
from typing import Optional
import httpx

logger = logging.getLogger(__name__)


class JenkinsClient:
    def __init__(self, url: str, username: str = "", token: str = ""):
        self.url = url.rstrip("/")
        self.auth = (username, token) if username and token else None

    def _headers(self) -> dict:
        return {"Accept": "application/json"}

    async def _get(self, path: str, params: dict | None = None) -> dict | list:
        async with httpx.AsyncClient(auth=self.auth, verify=False, timeout=15) as client:
            r = await client.get(f"{self.url}{path}", params=params, headers=self._headers())
            r.raise_for_status()
            return r.json()

    async def _post(self, path: str, params: dict | None = None, data: dict | None = None) -> httpx.Response:
        async with httpx.AsyncClient(auth=self.auth, verify=False, timeout=15) as client:
            r = await client.post(f"{self.url}{path}", params=params, data=data, headers=self._headers())
            r.raise_for_status()
            return r

    async def _get_text(self, path: str) -> str:
        async with httpx.AsyncClient(auth=self.auth, verify=False, timeout=30) as client:
            r = await client.get(f"{self.url}{path}", headers={"Accept": "text/plain"})
            r.raise_for_status()
            return r.text

    # ── 查询 ──────────────────────────────────────────────────────────────────

    async def get_all_jobs(self) -> list[dict]:
        """获取所有 Job 列表（含状态）。"""
        data = await self._get("/api/json", {"tree": "jobs[name,url,color,lastBuild[number,result,timestamp,duration]]"})
        return data.get("jobs", [])

    async def search_jobs(self, query: str) -> list[dict]:
        """按关键字模糊匹配 Job 名称。"""
        jobs = await self.get_all_jobs()
        q = query.lower()
        return [j for j in jobs if q in j.get("name", "").lower()]

    async def get_build_info(self, job: str, build: int | str) -> dict:
        """获取指定构建详情。"""
        return await self._get(f"/job/{job}/{build}/api/json")

    async def get_last_build_info(self, job: str) -> dict:
        return await self._get(f"/job/{job}/lastBuild/api/json")

    async def get_build_logs(self, job: str, build: int | str, lines: int = 200) -> str:
        """获取构建控制台日志（末尾 N 行）。"""
        text = await self._get_text(f"/job/{job}/{build}/consoleText")
        if lines and lines > 0:
            log_lines = text.splitlines()
            return "\n".join(log_lines[-lines:])
        return text

    async def get_running_builds(self) -> list[dict]:
        """获取当前正在运行的所有构建。"""
        data = await self._get(
            "/api/json",
            {"tree": "jobs[name,color,lastBuild[number,result,timestamp,building,estimatedDuration]]"},
        )
        result = []
        for job in data.get("jobs", []):
            lb = job.get("lastBuild")
            if lb and lb.get("building"):
                result.append({"job": job["name"], **lb})
        return result

    async def get_test_results(self, job: str, build: int | str) -> dict:
        """获取构建测试报告。"""
        return await self._get(f"/job/{job}/{build}/testReport/api/json")

    async def get_queue_items(self) -> list[dict]:
        """获取构建队列。"""
        data = await self._get("/queue/api/json")
        return data.get("items", [])

    # ── 操作 ──────────────────────────────────────────────────────────────────

    async def build_job(self, job: str, params: dict | None = None) -> int:
        """触发构建，返回队列 ID。params 非空时走 buildWithParameters。"""
        if params:
            r = await self._post(f"/job/{job}/buildWithParameters", data=params)
        else:
            r = await self._post(f"/job/{job}/build")
        # Location: .../queue/item/123/  →  queue_id=123
        location = r.headers.get("Location", "")
        parts = [p for p in location.rstrip("/").split("/") if p]
        try:
            return int(parts[-1])
        except (ValueError, IndexError):
            return 0

    async def cancel_queue_item(self, queue_id: int) -> bool:
        """取消队列中的构建。"""
        try:
            await self._post("/queue/cancelItem", params={"id": queue_id})
            return True
        except Exception:
            return False

    async def ping(self) -> bool:
        try:
            await self._get("/api/json", {"tree": "nodeName"})
            return True
        except Exception:
            return False
