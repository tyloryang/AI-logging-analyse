"""数据库 / 中间件 AI 翻译助手 (参考 t8y2/dbx 的 built-in AI assistant 设计)

让用户用自然语言描述意图，AI 生成可执行命令：
- Redis:  "查找所有以 user: 开头的 key" → KEYS user:*
- ES:     "找出最近 1 小时 error 级别的日志" → DSL bool query

输出格式：JSON {command|dsl, explain, risk, notes}
"""
from __future__ import annotations

import json
import logging
from typing import Optional, Literal

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth.deps import current_user
from auth.models import User
from state import analyzer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai", tags=["ai-db"])


class TranslateRequest(BaseModel):
    scene: Literal["redis", "es", "kafka", "mysql"]
    query: str                   # 自然语言意图
    context: dict = {}           # 可选：当前连接 / 当前选中的 key / index 等
    stream: bool = False         # 是否流式


_SCENE_PROMPTS = {
    "redis": (
        "你是 Redis 专家。把用户自然语言转成最适合的 Redis 命令（单条或一组）。\n"
        "重要规则：\n"
        "• 危险命令（FLUSHALL/FLUSHDB/CONFIG SET/SHUTDOWN/DEBUG）必须把 risk 设为 high 并明确说明影响\n"
        "• 大表扫描优先用 SCAN 不用 KEYS *\n"
        "• 返回命令必须可直接粘贴到 redis-cli 执行（含参数完整）\n"
        "• 多个相关命令用换行分隔\n"
    ),
    "es": (
        "你是 Elasticsearch 专家。把用户自然语言转成 ES Query DSL JSON 或 SQL。\n"
        "重要规则：\n"
        "• 默认返回 DSL JSON（GET /index/_search 形式），用户明确要 SQL 才返回 SQL\n"
        "• 时间字段优先 @timestamp，没有则 timestamp/time/createTime\n"
        "• 涉及 update_by_query/delete_by_query 把 risk 设为 high\n"
        "• DSL 包含 size 限制（默认 100）\n"
    ),
    "kafka": (
        "你是 Kafka 专家。把用户自然语言转成 kafka-* CLI 命令（kafka-topics.sh / kafka-console-consumer.sh 等）。\n"
        "• delete-topics / alter-configs 危险，risk=high\n"
        "• 必须带 --bootstrap-server 参数占位（用 {{bootstrap}}）\n"
    ),
    "mysql": (
        "你是 MySQL 专家。把用户自然语言转成 SQL。\n"
        "• DML（UPDATE/DELETE）/ DDL（DROP/TRUNCATE/ALTER）risk=high，并提示加 LIMIT 或 WHERE\n"
        "• 大表查询提醒加索引或 LIMIT\n"
    ),
}


def _build_prompt(req: TranslateRequest) -> str:
    intro = _SCENE_PROMPTS.get(req.scene, "你是数据库专家。把用户意图转成可执行命令。")
    ctx_lines = []
    for k, v in (req.context or {}).items():
        v_str = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
        ctx_lines.append(f"- {k}: {v_str[:500]}")
    ctx_block = "\n".join(ctx_lines) if ctx_lines else "（无）"
    return f"""{intro}

当前上下文：
{ctx_block}

用户意图：{req.query}

请仅返回一个 JSON 对象（**禁止用代码块包裹**），结构：
{{
  "command": "可直接执行的命令字符串（多行用 \\n）",
  "explain": "1-3 句中文解释，说明这条命令在做什么",
  "risk": "low | medium | high",
  "risk_reason": "若 risk!=low 说明为什么有风险，否则空字符串",
  "notes": "可选的执行建议或注意事项"
}}
"""


@router.post("/translate")
async def translate_to_command(req: TranslateRequest, user: User = Depends(current_user)):
    """自然语言 → 数据库 / 中间件命令（非流式 JSON 直出）。"""
    prompt = _build_prompt(req)
    try:
        chunks = []
        async for ch in analyzer.provider.stream(prompt, max_tokens=800):
            chunks.append(ch)
        text = "".join(chunks).strip()
        # 提取首个完整 JSON 对象
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return {"command": text, "explain": "", "risk": "medium", "risk_reason": "AI 输出未识别为 JSON", "notes": text[:200]}
        try:
            parsed = json.loads(text[start: end + 1])
        except json.JSONDecodeError:
            parsed = {"command": text, "explain": "", "risk": "medium",
                      "risk_reason": "AI 输出 JSON 解析失败", "notes": text[:200]}
        parsed.setdefault("command", "")
        parsed.setdefault("explain", "")
        parsed.setdefault("risk", "low")
        parsed.setdefault("risk_reason", "")
        parsed.setdefault("notes", "")
        return parsed
    except Exception as e:
        logger.exception("[ai.translate] failed")
        raise HTTPException(500, f"AI 翻译失败：{e}")


@router.post("/translate/stream")
async def translate_stream(req: TranslateRequest, user: User = Depends(current_user)):
    """SSE 流式版本，前端可实时显示生成过程。"""
    prompt = _build_prompt(req)
    async def _gen():
        try:
            async for ch in analyzer.provider.stream(prompt, max_tokens=800):
                yield f"data: {json.dumps({'chunk': ch}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            yield "data: [DONE]\n\n"
    return StreamingResponse(_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class ExplainRequest(BaseModel):
    scene: Literal["redis", "es", "kafka", "mysql"]
    command: str              # 已有命令/DSL/SQL，请 AI 解释
    result: Optional[str] = None     # 可选执行结果，让 AI 一并解读


@router.post("/explain")
async def explain_command(req: ExplainRequest, user: User = Depends(current_user)):
    """让 AI 解释一条命令做什么，可附带执行结果做解读。"""
    prompt = f"""你是 {req.scene.upper()} 专家。请用 2-4 句中文解释下面的命令在做什么。
如果给了执行结果，也请用 1-2 句概括结果含义。

命令：
{req.command}

执行结果：
{(req.result or '（无）')[:2000]}

直接给解释，不要用 JSON 包裹。
"""
    chunks = []
    try:
        async for ch in analyzer.provider.stream(prompt, max_tokens=400):
            chunks.append(ch)
        return {"explain": "".join(chunks).strip()}
    except Exception as e:
        raise HTTPException(500, f"AI 解释失败：{e}")
