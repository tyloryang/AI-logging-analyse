"""Jenkins REST API 客户端（基于 httpx，支持多级文件夹 Pipeline）。"""
import logging
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

# tree 查询：展开 3 层文件夹嵌套（覆盖绝大多数场景）
_JOBS_TREE = (
    "jobs[name,url,color,_class,"
    "lastBuild[number,result,timestamp,duration,building,estimatedDuration],"
    "jobs[name,url,color,_class,"
    "lastBuild[number,result,timestamp,duration,building,estimatedDuration],"
    "jobs[name,url,color,_class,"
    "lastBuild[number,result,timestamp,duration,building,estimatedDuration]]]]"
)


def _job_api_path(job: str) -> str:
    """将 'folder/sub/job' 转换为 Jenkins API 路径 '/job/folder/job/sub/job/job'。"""
    parts = [p for p in job.strip("/").split("/") if p]
    return "/" + "/".join(f"job/{p}" for p in parts)


def _flatten_jobs(jobs: list, prefix: str = "") -> list[dict]:
    """递归展开文件夹，返回所有叶子 Job，name 为完整路径（folder/sub/job）。"""
    result = []
    for job in jobs:
        name = job.get("name", "")
        full_name = f"{prefix}/{name}" if prefix else name
        sub = job.get("jobs")
        if sub is not None:
            # 文件夹：递归进去
            result.extend(_flatten_jobs(sub, full_name))
        else:
            result.append({**job, "name": full_name})
    return result


class JenkinsClient:
    def __init__(self, url: str, username: str = "", token: str = ""):
        self.url = url.rstrip("/")
        self.auth = (username, token) if username and token else None
        self._crumb: dict | None = None

    def _headers(self) -> dict:
        return {"Accept": "application/json"}

    async def _get_crumb(self, client: httpx.AsyncClient) -> dict:
        if self._crumb is not None:
            return self._crumb
        try:
            r = await client.get(f"{self.url}/crumbIssuer/api/json", headers=self._headers())
            if r.status_code == 200:
                data = r.json()
                self._crumb = {data["crumbRequestField"]: data["crumb"]}
                return self._crumb
        except Exception as e:
            logger.debug("[jenkins] 获取 crumb 失败（可能未启用 CSRF）: %s", e)
        self._crumb = {}
        return {}

    async def _get(self, path: str, params: dict | None = None) -> dict | list:
        async with httpx.AsyncClient(auth=self.auth, verify=False, timeout=30) as client:
            try:
                r = await client.get(f"{self.url}{path}", params=params, headers=self._headers())
            except httpx.ConnectError:
                raise RuntimeError(f"无法连接 Jenkins ({self.url})，请检查 URL 和网络")
            except httpx.TimeoutException:
                raise RuntimeError(f"连接 Jenkins 超时 ({self.url})")
            if r.status_code == 401:
                raise RuntimeError("Jenkins 认证失败，请检查用户名和 API Token")
            if r.status_code == 403:
                raise RuntimeError("Jenkins 拒绝访问（403），请确认账号权限或 CSRF 配置")
            r.raise_for_status()
            return r.json()

    async def _post(self, path: str, params: dict | None = None, data: dict | None = None) -> httpx.Response:
        async with httpx.AsyncClient(auth=self.auth, verify=False, timeout=30) as client:
            crumb = await self._get_crumb(client)
            headers = {**self._headers(), **crumb}
            r = await client.post(f"{self.url}{path}", params=params, data=data, headers=headers)
            if r.status_code == 403:
                self._crumb = None
                crumb = await self._get_crumb(client)
                headers = {**self._headers(), **crumb}
                r = await client.post(f"{self.url}{path}", params=params, data=data, headers=headers)
            r.raise_for_status()
            return r

    async def _get_text(self, path: str) -> str:
        async with httpx.AsyncClient(auth=self.auth, verify=False, timeout=30) as client:
            r = await client.get(f"{self.url}{path}", headers={"Accept": "text/plain"})
            r.raise_for_status()
            return r.text

    async def _post_xml(self, path: str, xml_body: str) -> httpx.Response:
        """POST application/xml body（用于 config.xml 上传 / job 创建）"""
        async with httpx.AsyncClient(auth=self.auth, verify=False, timeout=30) as client:
            crumb = await self._get_crumb(client)
            headers = {**self._headers(), **crumb, "Content-Type": "application/xml"}
            r = await client.post(f"{self.url}{path}", content=xml_body, headers=headers)
            if r.status_code == 403:
                self._crumb = None
                crumb = await self._get_crumb(client)
                headers = {**self._headers(), **crumb, "Content-Type": "application/xml"}
                r = await client.post(f"{self.url}{path}", content=xml_body, headers=headers)
            r.raise_for_status()
            return r

    # ── 查询 ──────────────────────────────────────────────────────────────────

    async def get_all_jobs(self) -> list[dict]:
        """递归获取所有 Job（含文件夹内多级 Pipeline），name 为完整路径。"""
        data = await self._get("/api/json", {"tree": _JOBS_TREE})
        return _flatten_jobs(data.get("jobs", []))

    async def get_view_jobs(self, view: str) -> list[dict]:
        """获取指定 View 下所有 Job（含文件夹递归展开），name 为完整路径。"""
        from urllib.parse import quote
        data = await self._get(f"/view/{quote(view, safe='')}/api/json", {"tree": _JOBS_TREE})
        return _flatten_jobs(data.get("jobs", []))

    async def get_views_with_jobs(self) -> list[dict]:
        """获取所有 View 及其 Job 列表（含文件夹递归展开）。"""
        views_tree = (
            "views[name,url,"
            "jobs[name,color,url,_class,"
            "lastBuild[number,result,timestamp,duration],"
            "jobs[name,color,url,_class,"
            "lastBuild[number,result,timestamp,duration],"
            "jobs[name,color,url,_class,"
            "lastBuild[number,result,timestamp,duration]]]]]"
        )
        data = await self._get("/api/json", {"tree": views_tree})
        result = []
        for v in data.get("views", []):
            jobs = _flatten_jobs(v.get("jobs", []))
            fail_count = sum(1 for j in jobs if (j.get("color") or "").startswith("red"))
            result.append({
                "name":       v.get("name"),
                "url":        v.get("url"),
                "job_count":  len(jobs),
                "fail_count": fail_count,
                "jobs":       jobs,
            })
        return result

    async def search_jobs(self, query: str) -> list[dict]:
        jobs = await self.get_all_jobs()
        q = query.lower()
        return [j for j in jobs if q in j.get("name", "").lower()]

    async def get_build_info(self, job: str, build: int | str) -> dict:
        """支持文件夹路径，如 'folder/sub/job'。"""
        return await self._get(f"{_job_api_path(job)}/{build}/api/json")

    async def get_last_build_info(self, job: str) -> dict:
        return await self._get(f"{_job_api_path(job)}/lastBuild/api/json")

    async def get_build_logs(self, job: str, build: int | str, lines: int = 200) -> str:
        text = await self._get_text(f"{_job_api_path(job)}/{build}/consoleText")
        if lines and lines > 0:
            return "\n".join(text.splitlines()[-lines:])
        return text

    async def get_running_builds(self) -> list[dict]:
        """递归扫描所有层级，返回正在运行的构建。"""
        data = await self._get("/api/json", {"tree": _JOBS_TREE})
        all_jobs = _flatten_jobs(data.get("jobs", []))
        result = []
        for job in all_jobs:
            lb = job.get("lastBuild")
            if lb and lb.get("building"):
                result.append({"job": job["name"], **lb})
        return result

    async def get_test_results(self, job: str, build: int | str) -> dict:
        return await self._get(f"{_job_api_path(job)}/{build}/testReport/api/json")

    async def get_recent_builds(self, job: str, limit: int = 15) -> list[dict]:
        """获取最近 N 次构建记录（含状态/耗时/时间戳）。"""
        path = _job_api_path(job)
        data = await self._get(f"{path}/api/json", {
            "tree": f"builds[number,result,duration,timestamp,building,estimatedDuration]{{0,{limit}}}"
        })
        return data.get("builds", [])

    async def get_queue_items(self) -> list[dict]:
        data = await self._get("/queue/api/json")
        return data.get("items", [])

    # ── Job 配置（config.xml）────────────────────────────────────────────────

    async def get_job_config(self, job: str) -> str:
        """读取 Job 的 config.xml 原文，支持文件夹路径。"""
        path = _job_api_path(job)
        return await self._get_text(f"{path}/config.xml")

    async def update_job_config(self, job: str, xml_body: str) -> None:
        """POST 上传新的 config.xml，覆盖 Job 配置。"""
        path = _job_api_path(job)
        await self._post_xml(f"{path}/config.xml", xml_body)

    # ── 操作 ──────────────────────────────────────────────────────────────────

    async def build_job(self, job: str, params: dict | None = None) -> int:
        """支持文件夹路径触发构建。"""
        path = _job_api_path(job)
        if params:
            r = await self._post(f"{path}/buildWithParameters", data=params)
        else:
            r = await self._post(f"{path}/build")
        location = r.headers.get("Location", "")
        parts = [p for p in location.rstrip("/").split("/") if p]
        try:
            return int(parts[-1])
        except (ValueError, IndexError):
            return 0

    async def cancel_queue_item(self, queue_id: int) -> bool:
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
