"""智能体配置路由

端点：
  GET  /api/agent-config            — 读取完整配置
  PUT  /api/agent-config            — 保存基础配置
  GET  /api/agent-config/mcps       — MCP 列表
  POST /api/agent-config/mcps       — 添加 MCP
  PUT  /api/agent-config/mcps/{id}  — 更新 MCP（启停）
  DELETE /api/agent-config/mcps/{id} — 删除 MCP
  GET  /api/agent-config/skills     — Skill 列表
  PUT  /api/agent-config/skills/{id} — 更新 Skill（启停）
  GET  /api/agent-config/behaviors  — 行为开关列表
  PUT  /api/agent-config/behaviors  — 批量更新行为开关
  GET  /api/agent-config/models     — 模型列表
  PUT  /api/agent-config/models/active — 切换激活模型
  GET  /api/agent-config/sa         — SA 列表
  POST /api/agent-config/sa         — 接入 SA
  PUT  /api/agent-config/sa/{id}    — 更新 SA（启停）
  DELETE /api/agent-config/sa/{id}  — 删除 SA
  GET  /api/agent-config/stats      — 统计摘要
"""
import json
import logging
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent-config", tags=["agent-config"])

# 配置文件路径
_CONFIG_FILE = Path("./data/agent_config.json")

# ── 默认配置 ────────────────────────────────────────────────────────────────

_DEFAULT_CONFIG = {
    "sa": [
        {"id": "1", "name": "order-service SA",     "endpoint": "http://order-service:8080/sa",     "token": "", "active": True,  "conversations": 23},
        {"id": "2", "name": "payment-service SA",   "endpoint": "http://payment-service:8080/sa",   "token": "", "active": True,  "conversations": 11},
        {"id": "3", "name": "inventory-service SA", "endpoint": "http://inventory-service:8080/sa", "token": "", "active": False, "conversations": 4},
        {"id": "4", "name": "gateway-service SA",   "endpoint": "http://gateway:8080/sa",           "token": "", "active": True,  "conversations": 8},
    ],
    "basic": {
        "name":       "SxDevOps 智能运维助手",
        "definition": "你是一名资深 SRE 工程师，负责保障平台稳定性。你拥有丰富的故障排查经验，能够快速定位问题根因并给出修复建议。",
        "mcp_desc":   "你可以通过下方的 MCP 与 Redis、Nacos 通信，获取业务配置数据，也可以调用 Prometheus API 获取实时指标。",
        "skill_desc": "还可以通过调用 Skill 完成自动化巡检 order-service 等能力，以及执行 Ansible Playbook 对目标主机进行操作。",
        "skill_mode": "confirm",
        "max_turns":  20,
        "stream":     True,
        "confirm_mode": "ask",
    },
    "mcps": [
        {"id": "1", "name": "Prometheus MCP", "type": "http",  "url": "http://localhost:9090/api", "enabled": True,  "ok": True},
        {"id": "2", "name": "Redis MCP",       "type": "stdio", "url": "localhost:6379",            "enabled": True,  "ok": True},
        {"id": "3", "name": "Nacos MCP",       "type": "http",  "url": "http://localhost:8848",     "enabled": False, "ok": False},
        {"id": "4", "name": "MySQL MCP",       "type": "stdio", "url": "localhost:3306",            "enabled": True,  "ok": True},
    ],
    "skills": [
        {"id": "1", "icon": "🔍", "name": "主机巡检",          "desc": "自动巡检所有主机 CPU/内存/磁盘，生成异常报告",   "tags": ["Ansible", "Prometheus"], "enabled": True},
        {"id": "2", "icon": "📋", "name": "Ansible Playbook", "desc": "在目标主机上执行 Ansible Playbook 自动化任务",  "tags": ["Ansible", "SSH"],        "enabled": True},
        {"id": "3", "icon": "🚨", "name": "告警静默",          "desc": "对指定服务告警进行临时静默操作",                "tags": ["Alertmanager"],          "enabled": False},
        {"id": "4", "icon": "📊", "name": "慢查询导出",        "desc": "导出 MySQL/Redis 慢查询日志并分析 Top 10",      "tags": ["MySQL", "Redis"],        "enabled": True},
        {"id": "5", "icon": "🔄", "name": "服务重启",          "desc": "对 K8s Deployment 执行滚动重启",                "tags": ["Kubernetes"],            "enabled": False},
        {"id": "6", "icon": "📦", "name": "日志打包",          "desc": "收集并打包指定时间段的服务日志",                "tags": ["Loki", "S3"],            "enabled": True},
    ],
    "behaviors": [
        {"key": "rag",    "name": "主动检索增强",  "desc": "AI 将主动查询日志、指标等数据后再回答",         "enabled": True},
        {"key": "auto",   "name": "自动执行动作",  "desc": "允许 AI 在无需确认时直接调用 Skill 执行",      "enabled": False},
        {"key": "trace",  "name": "链路追踪关联",  "desc": "自动关联 SkyWalking Trace 进行根因分析",      "enabled": True},
        {"key": "alert",  "name": "告警实时感知",  "desc": "接收告警推送，AI 可主动发起分析",              "enabled": True},
        {"key": "report", "name": "生成巡检报告",  "desc": "巡检完成后自动汇总为结构化 Markdown 报告",    "enabled": False},
    ],
    "models": [
        {"id": "claude-opus",   "name": "claude-opus-4-6",  "provider": "Anthropic", "active": True},
        {"id": "claude-sonnet", "name": "claude-sonnet-4-6","provider": "Anthropic", "active": False},
        {"id": "qwen3-32b",     "name": "Qwen3-32B",         "provider": "Local",     "active": False},
    ],
}


# ── 配置读写辅助 ─────────────────────────────────────────────────────────────

def _load() -> dict:
    if _CONFIG_FILE.exists():
        try:
            data = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
            # 迁移：旧版本无 sa 字段时，填充默认值
            if "sa" not in data:
                data["sa"] = json.loads(json.dumps(_DEFAULT_CONFIG["sa"]))
                _save(data)
            return data
        except Exception as e:
            logger.warning("[agent_config] 配置文件读取失败，使用默认值: %s", e)
    return json.loads(json.dumps(_DEFAULT_CONFIG))  # deep copy


def _save(data: dict) -> None:
    _CONFIG_FILE.parent.mkdir(exist_ok=True)
    _CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/agent-config  — 读取完整配置
# ══════════════════════════════════════════════════════════════════════════════

@router.get("")
async def get_config():
    return _load()


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/agent-config/stats  — 统计摘要
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/stats")
async def get_stats():
    cfg = _load()
    mcps   = cfg.get("mcps", [])
    skills = cfg.get("skills", [])
    models = cfg.get("models", [])
    sas    = cfg.get("sa", [])
    return {
        "models":  len([m for m in models if m.get("active")]),
        "mcps":    len([m for m in mcps if m.get("enabled")]),
        "skills":  len([s for s in skills if s.get("enabled")]),
        "sa":      len([s for s in sas if s.get("active")]),
        "actions": sum(s.get("conversations", 0) for s in sas if s.get("active")),
    }


# ══════════════════════════════════════════════════════════════════════════════
# PUT /api/agent-config  — 保存基础配置
# ══════════════════════════════════════════════════════════════════════════════

class BasicConfig(BaseModel):
    name:         Optional[str] = None
    definition:   Optional[str] = None
    mcp_desc:     Optional[str] = None
    skill_desc:   Optional[str] = None
    skill_mode:   Optional[str] = None
    max_turns:    Optional[int] = None
    stream:       Optional[bool] = None
    confirm_mode: Optional[str] = None


@router.put("")
async def save_config(body: BasicConfig):
    cfg = _load()
    basic = cfg.setdefault("basic", {})
    for field, value in body.model_dump(exclude_none=True).items():
        basic[field] = value
    _save(cfg)
    return {"ok": True, "basic": basic}


# ══════════════════════════════════════════════════════════════════════════════
# MCP 管理
# ══════════════════════════════════════════════════════════════════════════════

class McpCreate(BaseModel):
    name:    str
    type:    str = "http"
    url:     str
    enabled: bool = True


@router.get("/mcps")
async def list_mcps():
    cfg = _load()
    return {"data": cfg.get("mcps", [])}


@router.post("/mcps")
async def add_mcp(body: McpCreate):
    cfg = _load()
    mcps = cfg.setdefault("mcps", [])
    new_mcp = {
        "id":      str(uuid.uuid4())[:8],
        "name":    body.name,
        "type":    body.type,
        "url":     body.url,
        "enabled": body.enabled,
        "ok":      False,
    }
    mcps.append(new_mcp)
    _save(cfg)
    return new_mcp


@router.delete("/mcps/{mcp_id}")
async def delete_mcp(mcp_id: str):
    cfg = _load()
    mcps = cfg.get("mcps", [])
    orig_len = len(mcps)
    cfg["mcps"] = [m for m in mcps if m["id"] != mcp_id]
    if len(cfg["mcps"]) == orig_len:
        raise HTTPException(status_code=404, detail="MCP 不存在")
    _save(cfg)
    return {"ok": True}


class McpToggle(BaseModel):
    enabled: bool

@router.put("/mcps/{mcp_id}")
async def update_mcp(mcp_id: str, body: McpToggle):
    cfg = _load()
    for m in cfg.get("mcps", []):
        if m["id"] == mcp_id:
            m["enabled"] = body.enabled
            _save(cfg)
            return m
    raise HTTPException(status_code=404, detail="MCP 不存在")


# ══════════════════════════════════════════════════════════════════════════════
# Skill 管理
# ══════════════════════════════════════════════════════════════════════════════

class SkillToggle(BaseModel):
    enabled: bool


@router.get("/skills")
async def list_skills():
    cfg = _load()
    return {"data": cfg.get("skills", [])}


@router.put("/skills/{skill_id}")
async def update_skill(skill_id: str, body: SkillToggle):
    cfg = _load()
    for s in cfg.get("skills", []):
        if s["id"] == skill_id:
            s["enabled"] = body.enabled
            _save(cfg)
            return s
    raise HTTPException(status_code=404, detail="Skill 不存在")


# ══════════════════════════════════════════════════════════════════════════════
# 行为开关管理
# ══════════════════════════════════════════════════════════════════════════════

class BehaviorItem(BaseModel):
    key:     str
    enabled: bool


class BehaviorsUpdate(BaseModel):
    behaviors: list[BehaviorItem]


@router.get("/behaviors")
async def list_behaviors():
    cfg = _load()
    return {"data": cfg.get("behaviors", [])}


@router.put("/behaviors")
async def update_behaviors(body: BehaviorsUpdate):
    cfg = _load()
    behavior_map = {b["key"]: b for b in cfg.get("behaviors", [])}
    for item in body.behaviors:
        if item.key in behavior_map:
            behavior_map[item.key]["enabled"] = item.enabled
    cfg["behaviors"] = list(behavior_map.values())
    _save(cfg)
    return {"ok": True, "data": cfg["behaviors"]}


# ══════════════════════════════════════════════════════════════════════════════
# 模型管理
# ══════════════════════════════════════════════════════════════════════════════

class ModelSelect(BaseModel):
    model_id: str


@router.get("/models")
async def list_models():
    cfg = _load()
    return {"data": cfg.get("models", [])}


@router.put("/models/active")
async def set_active_model(body: ModelSelect):
    cfg = _load()
    found = False
    for m in cfg.get("models", []):
        m["active"] = (m["id"] == body.model_id)
        if m["id"] == body.model_id:
            found = True
    if not found:
        raise HTTPException(status_code=404, detail="模型不存在")
    _save(cfg)
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# SA 接入管理
# ══════════════════════════════════════════════════════════════════════════════

class SaCreate(BaseModel):
    name:     str
    endpoint: str
    token:    Optional[str] = ""
    active:   bool = True


class SaToggle(BaseModel):
    active: bool


@router.get("/sa")
async def list_sa():
    cfg = _load()
    return {"data": cfg.get("sa", [])}


@router.post("/sa")
async def add_sa(body: SaCreate):
    cfg = _load()
    sas = cfg.setdefault("sa", [])
    new_sa = {
        "id":            str(uuid.uuid4())[:8],
        "name":          body.name,
        "endpoint":      body.endpoint,
        "token":         body.token or "",
        "active":        body.active,
        "conversations": 0,
    }
    sas.append(new_sa)
    _save(cfg)
    return new_sa


@router.put("/sa/{sa_id}")
async def update_sa(sa_id: str, body: SaToggle):
    cfg = _load()
    for s in cfg.get("sa", []):
        if s["id"] == sa_id:
            s["active"] = body.active
            _save(cfg)
            return s
    raise HTTPException(status_code=404, detail="SA 不存在")


@router.delete("/sa/{sa_id}")
async def delete_sa(sa_id: str):
    cfg = _load()
    sas = cfg.get("sa", [])
    orig_len = len(sas)
    cfg["sa"] = [s for s in sas if s["id"] != sa_id]
    if len(cfg["sa"]) == orig_len:
        raise HTTPException(status_code=404, detail="SA 不存在")
    _save(cfg)
    return {"ok": True}
