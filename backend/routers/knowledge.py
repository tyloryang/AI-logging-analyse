"""运维知识库路由（参考 itops-agent-platform ai/Knowledge）。

路由前缀：/api/knowledge/*
知识条目：故障案例 / 最佳实践 / 操作手册 / 安全合规 / 性能优化。
支持关键字搜索 + 分类过滤 + 标签，CRUD + 使用次数统计。
存储：backend/data/knowledge.json（首次为空时 seed 几条示例）。
"""
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from json_snapshot_store import read_json_file, write_json_file
from auth.deps import current_user
from auth.models import User

logger = logging.getLogger(__name__)
router = APIRouter()

_KB_FILE = Path(__file__).resolve().parent.parent / "data" / "knowledge.json"

CATEGORIES = ["故障案例", "最佳实践", "操作手册", "安全合规", "性能优化"]

_SEED = [
    {
        "title": "Pod CrashLoopBackOff 排查手册",
        "category": "故障案例",
        "tags": ["k8s", "pod", "crashloop"],
        "content": "现象：Pod 反复重启，STATUS 显示 CrashLoopBackOff。\n\n排查步骤：\n1. kubectl describe pod 看 Events\n2. kubectl logs --previous 看上次退出日志\n3. 判断是 OOMKilled（内存不足）还是应用启动失败\n4. 检查 readinessProbe/livenessProbe 配置是否过严",
        "solutions": ["调大 resources.limits.memory", "修复应用启动依赖", "放宽探针 initialDelaySeconds"],
    },
    {
        "title": "MySQL 慢查询优化最佳实践",
        "category": "性能优化",
        "tags": ["mysql", "slow-query", "index"],
        "content": "定位慢 SQL：\n- SHOW PROCESSLIST 看当前执行\n- 慢查询日志 + pt-query-digest 聚合\n\n优化方向：\n- 为 WHERE/JOIN/ORDER BY 列加合适索引（注意最左前缀）\n- 避免 SELECT *，避免函数包裹索引列\n- 大表分页用游标而非 OFFSET",
        "solutions": ["加复合索引 (col_a, col_b)", "改写 SQL 消除全表扫", "应用层加缓存"],
    },
    {
        "title": "Nginx 502/504 分层排查",
        "category": "操作手册",
        "tags": ["nginx", "5xx", "upstream"],
        "content": "502 = upstream 拒接（后端挂）；504 = upstream 超时（后端慢）。\n\n排查：\n1. 看 access.log 的 upstream_addr / upstream_response_time\n2. 反查目标后端服务健康度\n3. 检查 keepalive / worker_connections 是否打满",
        "solutions": ["重启/扩容后端服务", "调大 proxy_read_timeout", "增大 worker_connections"],
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> list[dict]:
    data = read_json_file(_KB_FILE, default=None)
    if data is None:
        # 首次：seed 示例
        seeded = []
        for item in _SEED:
            seeded.append({
                "id": str(uuid.uuid4())[:8],
                "usage_count": 0,
                "created_at": _now(),
                "updated_at": _now(),
                **item,
            })
        write_json_file(_KB_FILE, seeded, ensure_parent=True)
        return seeded
    return data if isinstance(data, list) else []


def _save(items: list[dict]) -> None:
    write_json_file(_KB_FILE, items, ensure_parent=True)


class KnowledgePayload(BaseModel):
    title: str = Field(..., min_length=1)
    category: str = "故障案例"
    tags: list[str] = []
    content: str = ""
    solutions: list[str] = []


@router.get("/api/knowledge")
async def list_knowledge(
    search: Optional[str] = Query(None, description="标题/内容/标签关键字"),
    category: Optional[str] = Query(None, description="按分类过滤"),
    _: User = Depends(current_user),
):
    items = _load()
    if category:
        items = [k for k in items if k.get("category") == category]
    if search:
        kw = search.lower().strip()
        def hit(k):
            hay = " ".join([
                k.get("title", ""), k.get("content", ""),
                " ".join(k.get("tags", []) or []),
                " ".join(k.get("solutions", []) or []),
            ]).lower()
            return kw in hay
        items = [k for k in items if hit(k)]
    items.sort(key=lambda k: k.get("updated_at", ""), reverse=True)
    return {"data": items, "total": len(items), "categories": CATEGORIES}


@router.get("/api/knowledge/categories")
async def get_categories(_: User = Depends(current_user)):
    # 统计每个分类条数
    items = _load()
    counts = {c: 0 for c in CATEGORIES}
    for k in items:
        c = k.get("category")
        if c in counts:
            counts[c] += 1
        else:
            counts[c] = counts.get(c, 0) + 1
    return {"categories": CATEGORIES, "counts": counts, "total": len(items)}


@router.post("/api/knowledge")
async def create_knowledge(payload: KnowledgePayload, _: User = Depends(current_user)):
    items = _load()
    entry = {
        "id": str(uuid.uuid4())[:8],
        "title": payload.title.strip(),
        "category": payload.category,
        "tags": [t.strip() for t in payload.tags if t.strip()],
        "content": payload.content,
        "solutions": [s.strip() for s in payload.solutions if s.strip()],
        "usage_count": 0,
        "created_at": _now(),
        "updated_at": _now(),
    }
    items.append(entry)
    _save(items)
    return {"ok": True, "data": entry}


@router.put("/api/knowledge/{kid}")
async def update_knowledge(kid: str, payload: KnowledgePayload, _: User = Depends(current_user)):
    items = _load()
    for k in items:
        if k["id"] == kid:
            k.update({
                "title": payload.title.strip(),
                "category": payload.category,
                "tags": [t.strip() for t in payload.tags if t.strip()],
                "content": payload.content,
                "solutions": [s.strip() for s in payload.solutions if s.strip()],
                "updated_at": _now(),
            })
            _save(items)
            return {"ok": True, "data": k}
    raise HTTPException(status_code=404, detail=f"知识条目 {kid} 不存在")


@router.delete("/api/knowledge/{kid}")
async def delete_knowledge(kid: str, _: User = Depends(current_user)):
    items = _load()
    new_items = [k for k in items if k["id"] != kid]
    if len(new_items) == len(items):
        raise HTTPException(status_code=404, detail=f"知识条目 {kid} 不存在")
    _save(new_items)
    return {"ok": True}


@router.post("/api/knowledge/{kid}/use")
async def mark_used(kid: str, _: User = Depends(current_user)):
    """查看详情时 +1 使用次数（热门知识排序用）。"""
    items = _load()
    for k in items:
        if k["id"] == kid:
            k["usage_count"] = int(k.get("usage_count", 0)) + 1
            _save(items)
            return {"ok": True, "usage_count": k["usage_count"]}
    raise HTTPException(status_code=404, detail=f"知识条目 {kid} 不存在")
