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

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from json_snapshot_store import read_json_file, write_json_file

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
        "name":       "AIOps 智能运维助手",
        "definition": "你是一名资深 SRE 工程师，负责保障平台稳定性。你拥有丰富的故障排查经验，能够快速定位问题根因并给出修复建议。",
        "mcp_desc":   "你可以通过下方的 MCP 与 Redis、Nacos 通信，获取业务配置数据，也可以调用 Prometheus API 获取实时指标。",
        "skill_desc": "还可以通过调用 Skill 完成自动化巡检 order-service 等能力，以及执行 Ansible Playbook 对目标主机进行操作。",
        "home_dir":   "",
        "model_type": "",
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
        {"id": "5", "name": "K8S MCP",         "type": "sse",   "url": "http://localhost:8002",     "enabled": False, "ok": False},
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
        {"key": "rag",        "name": "主动检索增强",  "desc": "AI 将主动查询日志、指标等数据后再回答",                        "enabled": True},
        {"key": "auto",       "name": "自动执行动作",  "desc": "允许 AI 在无需确认时直接调用 Skill 执行",                     "enabled": False},
        {"key": "trace",      "name": "链路追踪关联",  "desc": "自动关联 SkyWalking Trace 进行根因分析",                     "enabled": True},
        {"key": "alert",      "name": "告警实时感知",  "desc": "接收告警推送，AI 可主动发起分析",                             "enabled": True},
        {"key": "report",     "name": "生成巡检报告",  "desc": "巡检完成后自动汇总为结构化 Markdown 报告",                   "enabled": False},
        {"key": "show_trace", "name": "显示执行轨迹",  "desc": "飞书回复中展示 ReAct 工具调用步骤（关闭则只返回最终结果）",  "enabled": False},
    ],
    "models": [],
}


_LEGACY_SEED_MODEL_SIGNATURES = {
    ("claude-opus", "claude-opus-4-6", "claude-opus-4-6", "anthropic"),
    ("claude-sonnet", "claude-sonnet-4-6", "claude-sonnet-4-6", "anthropic"),
    ("qwen3-32b", "Qwen3-32B", "qwen3-32b", "openai"),
}


_ALLOWED_RUNTIME_PROVIDERS = {"anthropic", "openai"}
_ALLOWED_WIRE_APIS = {"", "chat", "responses"}


def _deepcopy_json(value):
    return json.loads(json.dumps(value))


def _coerce_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _normalize_runtime_provider(runtime_provider: str | None, provider: str | None = None) -> str:
    candidate = str(runtime_provider or "").strip().lower()
    if candidate in _ALLOWED_RUNTIME_PROVIDERS:
        return candidate
    provider_lower = str(provider or "").strip().lower()
    if provider_lower in {"openai", "local", "ollama", "vllm", "oneapi", "qwen", "deepseek", "gemini", "gpt"}:
        return "openai"
    return "anthropic"


def _normalize_wire_api(value: str | None) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in _ALLOWED_WIRE_APIS:
        return candidate
    return ""


def _mask_secret(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if len(raw) <= 6:
        return "*" * len(raw)
    return f"{raw[:3]}***{raw[-2:]}"


def _normalize_model_record(model: dict) -> tuple[dict, bool]:
    mutated = False
    current = dict(model or {})

    model_id = str(current.get("id", "")).strip()
    if not model_id:
        current["id"] = str(uuid.uuid4())[:8]
        mutated = True

    runtime_provider = _normalize_runtime_provider(
        current.get("runtime_provider"),
        current.get("provider"),
    )
    if current.get("runtime_provider") != runtime_provider:
        current["runtime_provider"] = runtime_provider
        mutated = True

    provider = str(current.get("provider", "")).strip()
    if not provider:
        current["provider"] = runtime_provider.title()
        mutated = True

    name = str(current.get("name", "")).strip()
    runtime_model = str(current.get("runtime_model", "")).strip()
    if not name and runtime_model:
        current["name"] = runtime_model
        mutated = True
        name = runtime_model
    if not runtime_model and name:
        current["runtime_model"] = name
        mutated = True

    base_url = str(current.get("base_url", "")).strip()
    if current.get("base_url", "") != base_url:
        current["base_url"] = base_url
        mutated = True

    api_key = str(current.get("api_key", "")).strip()
    if current.get("api_key", "") != api_key:
        current["api_key"] = api_key
        mutated = True

    wire_api = _normalize_wire_api(current.get("wire_api"))
    if current.get("wire_api", "") != wire_api:
        current["wire_api"] = wire_api
        mutated = True

    enable_thinking = _coerce_bool(current.get("enable_thinking"), default=False)
    if current.get("enable_thinking") is not enable_thinking:
        current["enable_thinking"] = enable_thinking
        mutated = True

    active = bool(current.get("active"))
    if current.get("active") is not active:
        current["active"] = active
        mutated = True

    return current, mutated


def _serialize_model_public(model: dict) -> dict:
    item = _deepcopy_json(model)
    api_key = str(item.get("api_key", "")).strip()
    item["api_key_set"] = bool(api_key)
    if api_key:
        item["api_key"] = _mask_secret(api_key)
    else:
        item.pop("api_key", None)
    return item


def _serialize_models_public(models: list[dict]) -> list[dict]:
    return [_serialize_model_public(model) for model in models]


def _maybe_clear_legacy_seed_models(cfg: dict) -> bool:
    models = cfg.get("models", [])
    if not isinstance(models, list) or len(models) != len(_LEGACY_SEED_MODEL_SIGNATURES):
        return False

    normalized_models: list[dict] = []
    for raw in models:
        if not isinstance(raw, dict):
            return False
        normalized, _ = _normalize_model_record(raw)
        signature = (
            str(normalized.get("id", "")).strip(),
            str(normalized.get("name", "")).strip(),
            str(normalized.get("runtime_model", "")).strip(),
            str(normalized.get("runtime_provider", "")).strip().lower(),
        )
        if signature not in _LEGACY_SEED_MODEL_SIGNATURES:
            return False
        if any(
            str(normalized.get(field, "")).strip()
            for field in ("base_url", "api_key", "wire_api")
        ):
            return False
        if bool(normalized.get("enable_thinking")):
            return False
        normalized_models.append(normalized)

    cfg["models"] = []
    cfg.setdefault("basic", {})["model_type"] = ""
    return True


def _ensure_models(cfg: dict) -> bool:
    mutated = False
    models = cfg.setdefault("models", [])
    normalized_models: list[dict] = []
    for raw in models:
        normalized, model_mutated = _normalize_model_record(raw if isinstance(raw, dict) else {})
        normalized_models.append(normalized)
        mutated = mutated or model_mutated or normalized != raw

    if normalized_models != models:
        cfg["models"] = normalized_models
        models = normalized_models
        mutated = True

    if models:
        active_indexes = [idx for idx, model in enumerate(models) if model.get("active")]
        if not active_indexes:
            models[0]["active"] = True
            active_indexes = [0]
            mutated = True
        if len(active_indexes) > 1:
            keep = active_indexes[0]
            for idx, model in enumerate(models):
                should_active = idx == keep
                if bool(model.get("active")) != should_active:
                    model["active"] = should_active
                    mutated = True
        active_model = next((model for model in models if model.get("active")), models[0])
        basic = cfg.setdefault("basic", {})
        desired_type = str(active_model.get("provider") or active_model.get("runtime_provider") or "").strip().lower()
        if basic.get("model_type") != desired_type:
            basic["model_type"] = desired_type
            mutated = True
    return mutated


def _get_active_model(cfg: dict) -> dict | None:
    models = cfg.get("models", [])
    return next((model for model in models if model.get("active")), models[0] if models else None)


def _apply_active_model_env(model: dict | None) -> None:
    if not model:
        return
    import os

    current, _ = _normalize_model_record(model)
    provider = current.get("runtime_provider", "anthropic")
    os.environ["AI_PROVIDER"] = provider
    os.environ["AI_MODEL"] = str(current.get("runtime_model", "")).strip()

    base_url = str(current.get("base_url", "")).strip()
    if base_url:
        os.environ["AI_BASE_URL"] = base_url
    elif provider != "openai":
        os.environ.pop("AI_BASE_URL", None)

    wire_api = str(current.get("wire_api", "")).strip()
    if wire_api:
        os.environ["AI_WIRE_API"] = wire_api
    else:
        os.environ.pop("AI_WIRE_API", None)

    os.environ["AI_ENABLE_THINKING"] = "1" if current.get("enable_thinking") else "0"

    api_key = str(current.get("api_key", "")).strip()
    if not api_key:
        return
    if provider == "openai":
        os.environ["AI_API_KEY"] = api_key
    else:
        os.environ["ANTHROPIC_API_KEY"] = api_key


def resolve_agent_model_overrides(
    model_id: str = "",
    model_name: str = "",
    model_provider: str = "",
    model_base_url: str = "",
    model_api_key: str = "",
    model_wire_api: str = "",
    model_enable_thinking: bool | str | None = None,
) -> dict:
    cfg = _load()
    models = cfg.get("models", [])
    provider_hint = str(model_provider or "").strip().lower()
    runtime_provider_hint = _normalize_runtime_provider(provider_hint) if provider_hint else ""
    target = None

    model_id = str(model_id or "").strip()
    model_name = str(model_name or "").strip()
    if model_id:
        target = next((model for model in models if str(model.get("id", "")).strip() == model_id), None)

    if target is None and model_name:
        candidates = [
            model
            for model in models
            if str(model.get("runtime_model", "")).strip() == model_name
            or str(model.get("name", "")).strip() == model_name
        ]
        if provider_hint:
            candidates = [
                model
                for model in candidates
                if str(model.get("runtime_provider", "")).strip().lower() == runtime_provider_hint
                or str(model.get("provider", "")).strip().lower() == provider_hint
            ]
        target = candidates[0] if candidates else None

    if target is None and provider_hint:
        candidates = [
            model
            for model in models
            if str(model.get("runtime_provider", "")).strip().lower() == runtime_provider_hint
            or str(model.get("provider", "")).strip().lower() == provider_hint
        ]
        target = next((model for model in candidates if model.get("active")), None) or (
            candidates[0] if candidates else None
        )

    if target is None and not (model_id or model_name or provider_hint):
        target = _get_active_model(cfg)

    resolved: dict = {}
    if target:
        normalized, _ = _normalize_model_record(target)
        resolved.update(
            {
                "model_id": str(normalized.get("id", "")).strip(),
                "model_name": str(normalized.get("runtime_model", "")).strip(),
                "model_provider": str(normalized.get("runtime_provider", "")).strip().lower(),
                "model_base_url": str(normalized.get("base_url", "")).strip(),
                "model_api_key": str(normalized.get("api_key", "")).strip(),
                "model_wire_api": str(normalized.get("wire_api", "")).strip().lower(),
                "model_enable_thinking": bool(normalized.get("enable_thinking")),
            }
        )

    if model_id:
        resolved["model_id"] = model_id
    if model_name:
        resolved["model_name"] = model_name
    if provider_hint:
        resolved["model_provider"] = runtime_provider_hint
    if model_base_url not in (None, ""):
        resolved["model_base_url"] = str(model_base_url).strip()
    if model_api_key not in (None, ""):
        resolved["model_api_key"] = str(model_api_key).strip()
    if model_wire_api not in (None, ""):
        resolved["model_wire_api"] = _normalize_wire_api(model_wire_api)
    if model_enable_thinking is not None:
        resolved["model_enable_thinking"] = _coerce_bool(model_enable_thinking)

    return resolved


# ── 配置读写辅助 ─────────────────────────────────────────────────────────────

def _load() -> dict:
    data = read_json_file(_CONFIG_FILE, default=None, ensure_parent=True)
    if isinstance(data, dict):
        try:
            mutated = False
            # 迁移：旧版本无 sa 字段时，填充默认值
            if "sa" not in data:
                data["sa"] = json.loads(json.dumps(_DEFAULT_CONFIG["sa"]))
                mutated = True
            if not any(
                any(keyword in str(item.get("name", "")).lower() for keyword in ("k8s", "kubernetes", "kube"))
                for item in data.get("mcps", [])
            ):
                k8s_default = next(
                    (
                        item
                        for item in _DEFAULT_CONFIG["mcps"]
                        if str(item.get("name", "")).lower() == "k8s mcp"
                    ),
                    None,
                )
                if k8s_default:
                    data.setdefault("mcps", []).append(json.loads(json.dumps(k8s_default)))
                    mutated = True
            # 迁移：补充新行为开关（旧配置文件缺少时自动追加）
            existing_keys = {b["key"] for b in data.get("behaviors", [])}
            for b in _DEFAULT_CONFIG["behaviors"]:
                if b["key"] not in existing_keys:
                    data.setdefault("behaviors", []).append(json.loads(json.dumps(b)))
                    mutated = True

            basic = data.setdefault("basic", {})
            for key, value in _DEFAULT_CONFIG["basic"].items():
                if key not in basic:
                    basic[key] = _deepcopy_json(value)
                    mutated = True

            mutated = _maybe_clear_legacy_seed_models(data) or mutated
            mutated = _ensure_models(data) or mutated

            if mutated:
                _save(data)
            return data
        except Exception as e:
            logger.warning("[agent_config] 配置文件读取失败，使用默认值: %s", e)
    default_cfg = _deepcopy_json(_DEFAULT_CONFIG)
    _ensure_models(default_cfg)
    return default_cfg


def _save(data: dict) -> None:
    _ensure_models(data)
    write_json_file(_CONFIG_FILE, data, ensure_parent=True)


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/agent-config  — 读取完整配置
# ══════════════════════════════════════════════════════════════════════════════

@router.get("")
async def get_config():
    cfg = _deepcopy_json(_load())
    cfg["models"] = _serialize_models_public(cfg.get("models", []))
    return cfg


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
        "models":  len(models),
        "mcps":    len([m for m in mcps if m.get("enabled")]),
        "skills":  len([s for s in skills if s.get("enabled")]),
        "sa":      len([s for s in sas if s.get("active")]),
        "actions": sum(s.get("conversations", 0) for s in sas if s.get("active")),
    }


# ══════════════════════════════════════════════════════════════════════════════
# PUT /api/agent-config  — 保存基础配置
# ══════════════════════════════════════════════════════════════════════════════

class BasicConfig(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    name:         Optional[str] = None
    definition:   Optional[str] = None
    mcp_desc:     Optional[str] = None
    skill_desc:   Optional[str] = None
    home_dir:     Optional[str] = None
    model_type:   Optional[str] = None
    skill_mode:   Optional[str] = None
    max_turns:    Optional[int] = None
    stream:       Optional[bool] = None
    confirm_mode: Optional[str] = None


@router.put("")
async def save_config(body: BasicConfig):
    cfg = _load()
    basic = cfg.setdefault("basic", {})
    for field, value in body.model_dump(exclude_none=True).items():
        if field == "home_dir":
            basic[field] = str(value).strip()
            continue
        if field == "model_type":
            basic[field] = str(value).strip().lower()
            continue
        basic[field] = value
    _save(cfg)
    return {"ok": True, "basic": basic}


@router.get("/workspace/discover")
async def discover_workspace():
    cfg = _load()
    basic = cfg.get("basic", {}) if isinstance(cfg, dict) else {}
    from services.claude_workspace import discover_claude_workspaces

    return discover_claude_workspaces(str(basic.get("home_dir") or "").strip())


# ══════════════════════════════════════════════════════════════════════════════
# MCP 管理
# ══════════════════════════════════════════════════════════════════════════════

class McpCreate(BaseModel):
    name:    str
    type:    str = "http"
    url:     str
    enabled: bool = True


class McpUpdate(BaseModel):
    name:    Optional[str] = None
    type:    Optional[str] = None
    url:     Optional[str] = None
    enabled: Optional[bool] = None


@router.get("/mcps")
async def list_mcps():
    cfg = _load()
    return {"data": cfg.get("mcps", [])}


async def _ping_mcp(mcp_type: str, url: str) -> bool:
    """尝试连通 MCP，返回是否在线。"""
    if mcp_type == "stdio":
        return True  # stdio 无法远程探测，默认认为在线
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(url)
            return resp.status_code < 500
    except Exception:
        return False


@router.post("/mcps")
async def add_mcp(body: McpCreate):
    cfg = _load()
    mcps = cfg.setdefault("mcps", [])
    ok = await _ping_mcp(body.type, body.url)
    new_mcp = {
        "id":      str(uuid.uuid4())[:8],
        "name":    body.name,
        "type":    body.type,
        "url":     body.url,
        "enabled": body.enabled,
        "ok":      ok,
    }
    mcps.append(new_mcp)
    _save(cfg)
    return new_mcp


@router.post("/mcps/{mcp_id}/ping")
async def ping_mcp(mcp_id: str):
    """手动刷新单个 MCP 连通状态。"""
    cfg = _load()
    for m in cfg.get("mcps", []):
        if m["id"] == mcp_id:
            m["ok"] = await _ping_mcp(m.get("type", "http"), m.get("url", ""))
            _save(cfg)
            return {"ok": m["ok"]}
    raise HTTPException(status_code=404, detail="MCP 不存在")


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


@router.put("/mcps/{mcp_id}")
async def update_mcp(mcp_id: str, body: McpUpdate):
    cfg = _load()
    for m in cfg.get("mcps", []):
        if m["id"] == mcp_id:
            payload = body.model_dump(exclude_none=True)
            if "name" in payload:
                name = str(payload["name"]).strip()
                if not name:
                    raise HTTPException(status_code=400, detail="MCP 名称不能为空")
                m["name"] = name
            if "type" in payload:
                mcp_type = str(payload["type"]).strip().lower()
                if mcp_type not in {"http", "sse", "stdio"}:
                    raise HTTPException(status_code=400, detail="MCP 类型仅支持 http / sse / stdio")
                m["type"] = mcp_type
            if "url" in payload:
                url = str(payload["url"]).strip()
                if not url:
                    raise HTTPException(status_code=400, detail="MCP 地址不能为空")
                m["url"] = url
            if "enabled" in payload:
                m["enabled"] = bool(payload["enabled"])

            if "type" in payload or "url" in payload:
                m["ok"] = await _ping_mcp(m.get("type", "http"), m.get("url", ""))
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
    model_config = ConfigDict(protected_namespaces=())
    model_id: str


class ModelCreate(BaseModel):
    name: str
    provider: Optional[str] = None
    runtime_model: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    runtime_provider: Optional[str] = None
    wire_api: Optional[str] = None
    enable_thinking: bool | str | None = None
    active: bool = False


class ModelEdit(BaseModel):
    name:             Optional[str] = None   # 显示名
    provider:         Optional[str] = None   # 展示 Provider
    runtime_model:    Optional[str] = None   # 实际发给 API 的 model 字符串
    base_url:         Optional[str] = None   # Local/OpenAI-compat 的 Base URL
    api_key:          Optional[str] = None   # API Key（Local 模型可选）
    runtime_provider: Optional[str] = None   # anthropic | openai
    wire_api:         Optional[str] = None   # chat | responses
    enable_thinking:  bool | str | None = None
    active:           Optional[bool] = None


def _update_model_from_payload(target: dict, payload: dict) -> dict:
    if "name" in payload:
        target["name"] = str(payload["name"] or "").strip()
    if "provider" in payload:
        target["provider"] = str(payload["provider"] or "").strip()
    if "runtime_model" in payload:
        target["runtime_model"] = str(payload["runtime_model"] or "").strip()
    if "base_url" in payload:
        target["base_url"] = str(payload["base_url"] or "").strip()
    if "api_key" in payload:
        target["api_key"] = str(payload["api_key"] or "").strip()
    if "runtime_provider" in payload:
        target["runtime_provider"] = str(payload["runtime_provider"] or "").strip().lower()
    if "wire_api" in payload:
        target["wire_api"] = str(payload["wire_api"] or "").strip().lower()
    if "enable_thinking" in payload:
        target["enable_thinking"] = _coerce_bool(payload.get("enable_thinking"))
    if "active" in payload:
        target["active"] = bool(payload["active"])

    normalized, _ = _normalize_model_record(target)
    if not str(normalized.get("name", "")).strip():
        raise HTTPException(status_code=400, detail="模型显示名称不能为空")
    if not str(normalized.get("runtime_model", "")).strip():
        raise HTTPException(status_code=400, detail="运行时模型名不能为空")
    return normalized


def _activate_model(cfg: dict, model_id: str) -> dict:
    models = cfg.get("models", [])
    target = next((model for model in models if model["id"] == model_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="模型不存在")
    for model in models:
        model["active"] = model["id"] == model_id
    cfg.setdefault("basic", {})["model_type"] = str(
        target.get("provider") or target.get("runtime_provider") or ""
    ).strip().lower()
    _save(cfg)
    _apply_active_model_env(target)
    return target


@router.get("/models")
async def list_models():
    cfg = _load()
    return {"data": _serialize_models_public(cfg.get("models", []))}


@router.post("/models")
async def create_model(body: ModelCreate):
    cfg = _load()
    models = cfg.setdefault("models", [])
    target = _update_model_from_payload(
        {
            "id": str(uuid.uuid4())[:8],
            "name": body.name,
            "provider": body.provider or "",
            "runtime_model": body.runtime_model or "",
            "base_url": body.base_url or "",
            "api_key": body.api_key or "",
            "runtime_provider": body.runtime_provider or "",
            "wire_api": body.wire_api or "",
            "enable_thinking": body.enable_thinking,
            "active": body.active,
        },
        {
            "name": body.name,
            "provider": body.provider,
            "runtime_model": body.runtime_model,
            "base_url": body.base_url,
            "api_key": body.api_key,
            "runtime_provider": body.runtime_provider,
            "wire_api": body.wire_api,
            "enable_thinking": body.enable_thinking,
            "active": body.active,
        },
    )
    models.append(target)
    _save(cfg)

    if target.get("active") or len(models) == 1:
        target = _activate_model(cfg, target["id"])

    return {"ok": True, "data": _serialize_model_public(target)}


@router.put("/models/active")
async def set_active_model(body: ModelSelect):
    cfg = _load()
    target = _activate_model(cfg, body.model_id)
    return {"ok": True, "data": _serialize_model_public(target)}


@router.put("/models/{model_id}")
async def edit_model(model_id: str, body: ModelEdit):
    """编辑模型参数。"""
    cfg = _load()
    target = next((m for m in cfg.get("models", []) if m["id"] == model_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="模型不存在")

    updated = _update_model_from_payload(target, body.model_dump(exclude_none=True))
    target.clear()
    target.update(updated)
    _save(cfg)

    if body.active:
        target = _activate_model(cfg, model_id)
    elif target.get("active"):
        _apply_active_model_env(target)
    return {"ok": True, "data": _serialize_model_public(target)}


@router.delete("/models/{model_id}")
async def delete_model(model_id: str):
    cfg = _load()
    models = cfg.get("models", [])
    target = next((model for model in models if model["id"] == model_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="模型不存在")

    cfg["models"] = [model for model in models if model["id"] != model_id]
    remaining = cfg["models"]
    if remaining:
        if target.get("active") or not any(model.get("active") for model in remaining):
            for idx, model in enumerate(remaining):
                model["active"] = idx == 0
            _apply_active_model_env(remaining[0])
        active_model = next((model for model in remaining if model.get("active")), remaining[0])
        cfg.setdefault("basic", {})["model_type"] = str(
            active_model.get("provider") or active_model.get("runtime_provider") or ""
        ).strip().lower()
    else:
        cfg.setdefault("basic", {})["model_type"] = ""
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
