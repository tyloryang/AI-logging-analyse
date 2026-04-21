"""主机分组管理路由。

路由前缀：/api/groups/*

每个分组可以配置独立的飞书/钉钉 Webhook，
主机巡检日报会按分组分别推送到对应群。
"""
import uuid
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from state import load_groups, save_groups, load_cmdb

logger = logging.getLogger(__name__)
router = APIRouter()


class GroupCreateRequest(BaseModel):
    name: str
    feishu_webhook: Optional[str] = ""
    feishu_keyword: Optional[str] = ""
    dingtalk_webhook: Optional[str] = ""
    dingtalk_keyword: Optional[str] = ""
    schedule_enabled: bool = False
    schedule_time: Optional[str] = "08:00"  # HH:MM


class GroupUpdateRequest(BaseModel):
    name: Optional[str] = None
    feishu_webhook: Optional[str] = None
    feishu_keyword: Optional[str] = None
    dingtalk_webhook: Optional[str] = None
    dingtalk_keyword: Optional[str] = None
    schedule_enabled: Optional[bool] = None
    schedule_time: Optional[str] = None


@router.get("/api/groups")
async def list_groups():
    """获取所有分组（附带每组主机数量）"""
    groups = load_groups()
    cmdb = load_cmdb()
    # 统计每组主机数量
    count: dict[str, int] = {}
    for meta in cmdb.values():
        gid = meta.get("group", "")
        if gid:
            count[gid] = count.get(gid, 0) + 1
    for g in groups:
        g["host_count"] = count.get(g["id"], 0)
    return {"data": groups}


@router.post("/api/groups")
async def create_group(body: GroupCreateRequest):
    """创建分组"""
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="分组名称不能为空")
    groups = load_groups()
    if any(g["name"] == body.name for g in groups):
        raise HTTPException(status_code=400, detail=f"分组名称 '{body.name}' 已存在")
    new_group = {
        "id": f"grp_{uuid.uuid4().hex[:8]}",
        "name": body.name.strip(),
        "feishu_webhook": body.feishu_webhook or "",
        "feishu_keyword": body.feishu_keyword or "",
        "dingtalk_webhook": body.dingtalk_webhook or "",
        "dingtalk_keyword": body.dingtalk_keyword or "",
        "schedule_enabled": body.schedule_enabled,
        "schedule_time": body.schedule_time or "08:00",
    }
    groups.append(new_group)
    save_groups(groups)
    logger.info("[groups] 创建分组: %s (%s)", new_group["name"], new_group["id"])
    return {"ok": True, "data": new_group}


@router.put("/api/groups/{group_id}")
async def update_group(group_id: str, body: GroupUpdateRequest):
    """更新分组信息"""
    groups = load_groups()
    group = next((g for g in groups if g["id"] == group_id), None)
    if not group:
        raise HTTPException(status_code=404, detail="分组不存在")
    # 检查名称重复
    if body.name is not None:
        if not body.name.strip():
            raise HTTPException(status_code=400, detail="分组名称不能为空")
        if any(g["name"] == body.name and g["id"] != group_id for g in groups):
            raise HTTPException(status_code=400, detail=f"分组名称 '{body.name}' 已存在")
        group["name"] = body.name.strip()
    for field in ("feishu_webhook", "feishu_keyword", "dingtalk_webhook", "dingtalk_keyword"):
        val = getattr(body, field)
        if val is not None:
            group[field] = val
    if body.schedule_enabled is not None:
        group["schedule_enabled"] = body.schedule_enabled
    if body.schedule_time is not None:
        group["schedule_time"] = body.schedule_time
    save_groups(groups)
    logger.info("[groups] 更新分组: %s (%s)", group["name"], group_id)
    return {"ok": True, "data": group}


@router.delete("/api/groups/{group_id}")
async def delete_group(group_id: str):
    """删除分组（同时清除所有主机的该分组关联）"""
    groups = load_groups()
    group = next((g for g in groups if g["id"] == group_id), None)
    if not group:
        raise HTTPException(status_code=404, detail="分组不存在")
    groups = [g for g in groups if g["id"] != group_id]
    save_groups(groups)
    # 清除 CMDB 中对该分组的引用
    from state import load_cmdb, save_cmdb
    cmdb = load_cmdb()
    changed = False
    for inst in cmdb:
        if cmdb[inst].get("group") == group_id:
            cmdb[inst]["group"] = ""
            changed = True
    if changed:
        save_cmdb(cmdb)
    logger.info("[groups] 删除分组: %s (%s)，已清除主机关联", group["name"], group_id)
    return {"ok": True}
