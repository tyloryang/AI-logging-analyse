"""Jenkins CI/CD 管理路由 — 支持多实例 + Views 分类。

路由前缀：/api/jenkins/*
"""
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from jenkins_client import JenkinsClient

logger = logging.getLogger(__name__)
router = APIRouter()

_JENKINS_FILE = Path(__file__).resolve().parent.parent / "data" / "jenkins.json"


# ── 持久化（多实例列表）─────────────────────────────────────────────────────────

def _load_instances() -> list[dict]:
    """加载所有 Jenkins 实例配置。兼容旧单对象格式。"""
    if not _JENKINS_FILE.exists():
        return []
    try:
        data = json.loads(_JENKINS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        # 兼容旧单对象格式
        if isinstance(data, dict) and data.get("url"):
            inst = {
                "id":       data.get("id", str(uuid.uuid4())[:8]),
                "name":     data.get("name", "默认 Jenkins"),
                "url":      data["url"],
                "username": data.get("username", ""),
                "token":    data.get("token", ""),
                "default":  True,
            }
            _save_instances([inst])
            return [inst]
    except Exception:
        pass
    return []


def _save_instances(instances: list[dict]) -> None:
    _JENKINS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _JENKINS_FILE.write_text(json.dumps(instances, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_instance(instance_id: str) -> dict:
    instances = _load_instances()
    inst = next((i for i in instances if i["id"] == instance_id), None)
    if not inst:
        raise HTTPException(status_code=404, detail=f"Jenkins 实例 {instance_id} 不存在")
    return inst


def _make_client(inst: dict) -> JenkinsClient:
    url      = inst.get("url", "").rstrip("/")
    username = inst.get("username", "")
    token    = inst.get("token", "")
    if not url:
        raise HTTPException(status_code=503, detail="Jenkins 实例未配置 URL")
    return JenkinsClient(url, username, token)


# ── 实例管理 CRUD ──────────────────────────────────────────────────────────────

class InstanceCreate(BaseModel):
    name:     str
    url:      str
    username: str = ""
    token:    str = ""
    default:  bool = False


@router.get("/api/jenkins/instances")
async def list_instances():
    """列出所有 Jenkins 实例（token 脱敏）。"""
    instances = _load_instances()
    safe = []
    for inst in instances:
        item = dict(inst)
        item["token_set"] = bool(item.pop("token", ""))
        safe.append(item)
    return {"data": safe}


@router.post("/api/jenkins/instances")
async def create_instance(body: InstanceCreate):
    instances = _load_instances()
    if body.default:
        for i in instances:
            i["default"] = False
    inst = {
        "id":       str(uuid.uuid4())[:8],
        "name":     body.name,
        "url":      body.url.rstrip("/"),
        "username": body.username,
        "token":    body.token,
        "default":  body.default or not instances,  # 首个默认设为 default
    }
    instances.append(inst)
    _save_instances(instances)
    result = dict(inst)
    result["token_set"] = bool(result.pop("token", ""))
    return result


@router.put("/api/jenkins/instances/{instance_id}")
async def update_instance(instance_id: str, body: InstanceCreate):
    instances = _load_instances()
    idx = next((i for i, x in enumerate(instances) if x["id"] == instance_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="实例不存在")
    if body.default:
        for i in instances:
            i["default"] = False
    inst = instances[idx]
    inst["name"]     = body.name
    inst["url"]      = body.url.rstrip("/")
    inst["username"] = body.username
    inst["default"]  = body.default
    if body.token:
        inst["token"] = body.token
    _save_instances(instances)
    result = dict(inst)
    result["token_set"] = bool(result.pop("token", ""))
    return result


@router.delete("/api/jenkins/instances/{instance_id}")
async def delete_instance(instance_id: str):
    instances = _load_instances()
    new_instances = [i for i in instances if i["id"] != instance_id]
    if len(new_instances) == len(instances):
        raise HTTPException(status_code=404, detail="实例不存在")
    # 若删除的是 default，设下一个为 default
    if new_instances and not any(i.get("default") for i in new_instances):
        new_instances[0]["default"] = True
    _save_instances(new_instances)
    return {"ok": True}


@router.post("/api/jenkins/instances/{instance_id}/default")
async def set_default_instance(instance_id: str):
    instances = _load_instances()
    for inst in instances:
        inst["default"] = inst["id"] == instance_id
    _save_instances(instances)
    return {"ok": True}


@router.get("/api/jenkins/instances/{instance_id}/test")
async def test_instance(instance_id: str):
    inst = _get_instance(instance_id)
    try:
        ok = await _make_client(inst).ping()
        return {"ok": ok, "message": "连接成功" if ok else "连接失败"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


# ── 兼容旧单实例配置接口 ────────────────────────────────────────────────────────

@router.get("/api/jenkins/config")
async def get_jenkins_config():
    instances = _load_instances()
    default = next((i for i in instances if i.get("default")), instances[0] if instances else {})
    return {
        "url":       default.get("url", os.getenv("JENKINS_URL", "")),
        "username":  default.get("username", os.getenv("JENKINS_USERNAME", "")),
        "token_set": bool(default.get("token") or os.getenv("JENKINS_TOKEN", "")),
        "instances": len(instances),
    }


@router.get("/api/jenkins/test")
async def test_default_jenkins():
    instances = _load_instances()
    default = next((i for i in instances if i.get("default")), instances[0] if instances else None)
    if not default:
        return {"ok": False, "message": "没有配置 Jenkins 实例"}
    try:
        ok = await _make_client(default).ping()
        return {"ok": ok, "message": "连接成功" if ok else "连接失败"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


# ── Views（分类视图）──────────────────────────────────────────────────────────

@router.get("/api/jenkins/instances/{instance_id}/views")
async def get_views(instance_id: str):
    """获取 Jenkins 实例的所有 View（视图分类）。"""
    inst = _get_instance(instance_id)
    try:
        client = _make_client(inst)
        data = await client._get("/api/json", {
            "tree": "views[name,url,jobs[name,color,url,lastBuild[number,result,timestamp,duration]]]"
        })
        views = data.get("views", [])
        # 统计每个 view 的 job 数和失败数
        result = []
        for v in views:
            jobs = v.get("jobs", [])
            fail_count = sum(1 for j in jobs if (j.get("color") or "").startswith("red"))
            result.append({
                "name":       v.get("name"),
                "url":        v.get("url"),
                "job_count":  len(jobs),
                "fail_count": fail_count,
                "jobs":       jobs,
            })
        return {"data": result}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ── Job 查询（按实例）─────────────────────────────────────────────────────────

@router.get("/api/jenkins/instances/{instance_id}/jobs")
async def get_jobs(
    instance_id: str,
    view: Optional[str] = Query(None, description="按视图名过滤"),
):
    inst = _get_instance(instance_id)
    try:
        client = _make_client(inst)
        if view:
            # 获取指定 view 下的 jobs
            data = await client._get(f"/view/{view}/api/json", {
                "tree": "jobs[name,url,color,lastBuild[number,result,timestamp,duration]]"
            })
            jobs = data.get("jobs", [])
        else:
            jobs = await client.get_all_jobs()
        return {"data": jobs, "total": len(jobs)}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/api/jenkins/instances/{instance_id}/jobs/search")
async def search_jobs(instance_id: str, q: str = Query(...)):
    inst = _get_instance(instance_id)
    try:
        jobs = await _make_client(inst).search_jobs(q)
        return {"data": jobs}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/api/jenkins/instances/{instance_id}/jobs/{job_name}/builds/{build_num}")
async def get_build_info(instance_id: str, job_name: str, build_num: str):
    inst = _get_instance(instance_id)
    try:
        return await _make_client(inst).get_build_info(job_name, build_num)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/api/jenkins/instances/{instance_id}/jobs/{job_name}/builds/{build_num}/logs")
async def get_build_logs(instance_id: str, job_name: str, build_num: str, lines: int = Query(200)):
    inst = _get_instance(instance_id)
    try:
        text = await _make_client(inst).get_build_logs(job_name, build_num, lines)
        return {"job": job_name, "build": build_num, "log": text}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/api/jenkins/instances/{instance_id}/running")
async def get_running_builds(instance_id: str):
    inst = _get_instance(instance_id)
    try:
        builds = await _make_client(inst).get_running_builds()
        return {"data": builds}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/api/jenkins/instances/{instance_id}/queue")
async def get_queue(instance_id: str):
    inst = _get_instance(instance_id)
    try:
        items = await _make_client(inst).get_queue_items()
        return {"data": items}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ── 操作 ──────────────────────────────────────────────────────────────────────

class BuildRequest(BaseModel):
    job:    str
    params: Optional[dict] = None


@router.post("/api/jenkins/instances/{instance_id}/build")
async def trigger_build(instance_id: str, body: BuildRequest):
    inst = _get_instance(instance_id)
    try:
        queue_id = await _make_client(inst).build_job(body.job, body.params)
        return {"ok": True, "queue_id": queue_id, "message": f"已触发 {body.job}，队列 ID: {queue_id}"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


class CancelRequest(BaseModel):
    queue_id: int


@router.post("/api/jenkins/instances/{instance_id}/queue/cancel")
async def cancel_queue_item(instance_id: str, body: CancelRequest):
    inst = _get_instance(instance_id)
    try:
        ok = await _make_client(inst).cancel_queue_item(body.queue_id)
        return {"ok": ok}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ── 旧接口兼容（使用 default 实例）────────────────────────────────────────────

def _default_client() -> JenkinsClient:
    instances = _load_instances()
    default = next((i for i in instances if i.get("default")), instances[0] if instances else None)
    if not default:
        raise HTTPException(status_code=503, detail="没有配置 Jenkins 实例")
    return _make_client(default)


@router.get("/api/jenkins/jobs")
async def get_jobs_default():
    try:
        jobs = await _default_client().get_all_jobs()
        return {"data": jobs, "total": len(jobs)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/api/jenkins/build")
async def trigger_build_default(body: BuildRequest):
    try:
        queue_id = await _default_client().build_job(body.job, body.params)
        return {"ok": True, "queue_id": queue_id, "message": f"已触发 {body.job}，队列 ID: {queue_id}"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
