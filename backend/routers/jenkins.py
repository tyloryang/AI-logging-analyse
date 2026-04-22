"""Jenkins CI/CD 管理路由。

路由前缀：/api/jenkins/*
"""
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from jenkins_client import JenkinsClient

logger = logging.getLogger(__name__)
router = APIRouter()

JENKINS_SETTINGS_FILE = __import__("pathlib").Path(__file__).resolve().parent.parent / "data" / "jenkins.json"


def _load_cfg() -> dict:
    if JENKINS_SETTINGS_FILE.exists():
        try:
            return json.loads(JENKINS_SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_cfg(data: dict) -> None:
    JENKINS_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    JENKINS_SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _client() -> JenkinsClient:
    cfg = _load_cfg()
    url = cfg.get("url") or os.getenv("JENKINS_URL", "")
    username = cfg.get("username") or os.getenv("JENKINS_USERNAME", "")
    token = cfg.get("token") or os.getenv("JENKINS_TOKEN", "")
    if not url:
        raise HTTPException(status_code=503, detail="Jenkins 未配置，请在设置页填写 Jenkins URL")
    return JenkinsClient(url, username, token)


# ── 配置 ──────────────────────────────────────────────────────────────────────

class JenkinsConfig(BaseModel):
    url: str
    username: str = ""
    token: str = ""


@router.get("/api/jenkins/config")
async def get_jenkins_config():
    cfg = _load_cfg()
    return {
        "url": cfg.get("url", os.getenv("JENKINS_URL", "")),
        "username": cfg.get("username", os.getenv("JENKINS_USERNAME", "")),
        "token_set": bool(cfg.get("token") or os.getenv("JENKINS_TOKEN", "")),
    }


@router.put("/api/jenkins/config")
async def save_jenkins_config(body: JenkinsConfig):
    cfg = _load_cfg()
    cfg["url"] = body.url
    cfg["username"] = body.username
    if body.token:
        cfg["token"] = body.token
    _save_cfg(cfg)
    os.environ["JENKINS_URL"]      = body.url
    os.environ["JENKINS_USERNAME"] = body.username
    if body.token:
        os.environ["JENKINS_TOKEN"] = body.token
    return {"ok": True}


@router.get("/api/jenkins/test")
async def test_jenkins_connection():
    try:
        ok = await _client().ping()
        return {"ok": ok, "message": "连接成功" if ok else "连接失败"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


# ── Job 查询 ──────────────────────────────────────────────────────────────────

@router.get("/api/jenkins/jobs")
async def get_all_jobs():
    """获取所有 Job 列表。"""
    try:
        jobs = await _client().get_all_jobs()
        return {"data": jobs, "total": len(jobs)}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/api/jenkins/jobs/search")
async def search_jobs(q: str = Query(..., description="关键字")):
    """按关键字搜索 Job。"""
    try:
        jobs = await _client().search_jobs(q)
        return {"data": jobs}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/api/jenkins/jobs/{job_name}/builds/{build_num}")
async def get_build_info(job_name: str, build_num: str):
    """获取指定构建信息。"""
    try:
        info = await _client().get_build_info(job_name, build_num)
        return info
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/api/jenkins/jobs/{job_name}/builds/{build_num}/logs")
async def get_build_logs(job_name: str, build_num: str, lines: int = Query(200)):
    """获取构建日志（末尾 N 行）。"""
    try:
        text = await _client().get_build_logs(job_name, build_num, lines)
        return {"job": job_name, "build": build_num, "log": text}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/api/jenkins/jobs/{job_name}/builds/{build_num}/tests")
async def get_test_results(job_name: str, build_num: str):
    """获取测试报告。"""
    try:
        result = await _client().get_test_results(job_name, build_num)
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/api/jenkins/running")
async def get_running_builds():
    """获取当前正在运行的构建。"""
    try:
        builds = await _client().get_running_builds()
        return {"data": builds}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/api/jenkins/queue")
async def get_queue():
    """获取构建队列。"""
    try:
        items = await _client().get_queue_items()
        return {"data": items}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ── 操作 ──────────────────────────────────────────────────────────────────────

class BuildRequest(BaseModel):
    job: str
    params: Optional[dict] = None


@router.post("/api/jenkins/build")
async def trigger_build(body: BuildRequest):
    """触发 Job 构建。"""
    try:
        queue_id = await _client().build_job(body.job, body.params)
        return {"ok": True, "queue_id": queue_id, "message": f"已触发 {body.job} 构建，队列 ID: {queue_id}"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


class CancelRequest(BaseModel):
    queue_id: int


@router.post("/api/jenkins/queue/cancel")
async def cancel_queue_item(body: CancelRequest):
    """取消队列中的构建。"""
    try:
        ok = await _client().cancel_queue_item(body.queue_id)
        return {"ok": ok}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
