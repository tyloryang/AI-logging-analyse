"""主机分组管理路由。

路由前缀：/api/groups/*

每个分组可以配置独立的飞书/钉钉 Webhook，
主机巡检日报会按分组分别推送到对应群。
"""
import uuid
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from state import load_groups, save_groups, load_hosts_list, save_hosts_list

logger = logging.getLogger(__name__)
router = APIRouter()


class AlertMatcherRequest(BaseModel):
    label: str
    value: str = ""


def _sanitize_alert_matchers(matchers: list[AlertMatcherRequest] | None) -> list[dict]:
    result: list[dict] = []
    for item in matchers or []:
        label = str(item.label or "").strip()
        value = str(item.value or "").strip()
        if not label:
            continue
        result.append({"label": label, "value": value})
    return result


class GroupCreateRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    feishu_webhook: Optional[str] = ""
    feishu_keyword: Optional[str] = ""
    dingtalk_webhook: Optional[str] = ""
    dingtalk_keyword: Optional[str] = ""
    schedule_enabled: bool = False
    schedule_time: Optional[str] = "08:00"  # HH:MM
    alert_matchers: list[AlertMatcherRequest] = Field(default_factory=list)


class GroupUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    feishu_webhook: Optional[str] = None
    feishu_keyword: Optional[str] = None
    dingtalk_webhook: Optional[str] = None
    dingtalk_keyword: Optional[str] = None
    schedule_enabled: Optional[bool] = None
    schedule_time: Optional[str] = None
    alert_matchers: Optional[list[AlertMatcherRequest]] = None


@router.get("/api/groups")
async def list_groups():
    """获取所有分组（附带每组主机数量）。"""
    groups = load_groups()
    hosts  = load_hosts_list()
    valid_group_ids = {g["id"] for g in groups}
    count: dict[str, int] = {}
    for h in hosts:
        gid = h.get("group", "")
        # 只统计有效分组 ID 的主机
        if gid and gid in valid_group_ids:
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
        "description": body.description or "",
        "feishu_webhook": body.feishu_webhook or "",
        "feishu_keyword": body.feishu_keyword or "",
        "dingtalk_webhook": body.dingtalk_webhook or "",
        "dingtalk_keyword": body.dingtalk_keyword or "",
        "schedule_enabled": body.schedule_enabled,
        "schedule_time": body.schedule_time or "08:00",
        "alert_matchers": _sanitize_alert_matchers(body.alert_matchers),
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
    if body.description is not None:
        group["description"] = body.description
    for field in ("feishu_webhook", "feishu_keyword", "dingtalk_webhook", "dingtalk_keyword"):
        val = getattr(body, field)
        if val is not None:
            group[field] = val
    if body.schedule_enabled is not None:
        group["schedule_enabled"] = body.schedule_enabled
    if body.schedule_time is not None:
        group["schedule_time"] = body.schedule_time
    if body.alert_matchers is not None:
        group["alert_matchers"] = _sanitize_alert_matchers(body.alert_matchers)
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
    # 清除主机列表中对该分组的引用
    hosts = load_hosts_list()
    changed = False
    for h in hosts:
        if h.get("group") == group_id:
            h["group"] = ""
            changed = True
    if changed:
        save_hosts_list(hosts)
    logger.info("[groups] 删除分组: %s (%s)，已清除主机关联", group["name"], group_id)
    return {"ok": True}
