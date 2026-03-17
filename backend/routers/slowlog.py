"""MySQL 慢日志分析路由

路由前缀：/api/slowlog/*
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

import asyncssh
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from slow_log_parser import parse_slow_log, build_summary
from sql_cluster import cluster_slow_queries
from state import load_cmdb, load_credentials, decrypt_password, analyzer

logger = logging.getLogger(__name__)
router = APIRouter()


# ── SSH 读文件辅助 ─────────────────────────────────────────────────────────────

async def _read_remote_file(
    host: str,
    port: int,
    username: str,
    password: str,
    filepath: str,
) -> str:
    """通过 SSH 读取远端文件内容"""
    try:
        async with asyncssh.connect(
            host, port=port, username=username, password=password,
            known_hosts=None, connect_timeout=15,
        ) as conn:
            result = await conn.run(f"cat {filepath}", check=True)
            return result.stdout
    except asyncssh.PermissionDenied:
        raise HTTPException(403, detail=f"SSH 认证失败：{username}@{host}")
    except asyncssh.ConnectionLost:
        raise HTTPException(502, detail=f"SSH 连接断开：{host}:{port}")
    except Exception as e:
        raise HTTPException(502, detail=f"SSH 读取失败：{e}")


def _resolve_credential(
    host_ip: str,
    credential_id: str = "",
    username: str = "",
    password: str = "",
    port: int = 22,
) -> tuple[str, str, str, int]:
    """从 CMDB / 凭证库解析 SSH 连接信息，返回 (username, password, host, port)"""
    # 1. 直传参数优先
    if username and password:
        return username, password, host_ip, port

    # 2. 指定凭证 ID
    if credential_id:
        creds = load_credentials()
        c = next((x for x in creds if x["id"] == credential_id), None)
        if c:
            return (
                c["username"],
                decrypt_password(c["password"]),
                host_ip,
                c.get("port", 22),
            )

    # 3. CMDB 中匹配的主机凭证
    cmdb = load_cmdb()
    for instance, info in cmdb.items():
        if info.get("ip") == host_ip:
            if info.get("credential_id"):
                creds = load_credentials()
                c = next((x for x in creds if x["id"] == info["credential_id"]), None)
                if c:
                    return (
                        c["username"],
                        decrypt_password(c["password"]),
                        host_ip,
                        c.get("port", 22),
                    )
            if info.get("ssh_password"):
                return (
                    info.get("ssh_user", "root"),
                    decrypt_password(info["ssh_password"]),
                    host_ip,
                    info.get("ssh_port", 22),
                )

    raise HTTPException(
        400,
        detail=f"未找到主机 {host_ip} 的 SSH 凭证，请在 CMDB 配置或手动输入用户名密码",
    )


# ── API 模型 ──────────────────────────────────────────────────────────────────

class FetchRequest(BaseModel):
    host_ip:       str
    log_path:      str = "/mysqldata/mysql/data/3306/mysql-slow.log"
    date_from:     Optional[str] = None       # "YYYY-MM-DD" 起始（含）
    date_to:       Optional[str] = None       # "YYYY-MM-DD" 结束（含）
    threshold_sec: float = 1.0
    alert_sec:     float = 10.0
    ssh_port:      int   = 22
    ssh_user:      str   = ""
    ssh_password:  str   = ""
    credential_id: str   = ""


# ── 接口 ─────────────────────────────────────────────────────────────────────

@router.post("/api/slowlog/fetch")
async def fetch_slow_log(body: FetchRequest):
    """SSH 读取远端慢日志并解析，返回结构化慢查询列表 + 汇总 + drain3 聚合"""
    username, password, host, port = _resolve_credential(
        body.host_ip,
        credential_id=body.credential_id,
        username=body.ssh_user,
        password=body.ssh_password,
        port=body.ssh_port,
    )

    try:
        text = await _read_remote_file(host, port, username, password, body.log_path)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, detail=f"SSH 读取失败：{e}")

    try:
        entries = parse_slow_log(
            text,
            date_from=body.date_from,
            date_to=body.date_to,
            threshold_sec=body.threshold_sec,
            alert_sec=body.alert_sec,
        )
    except Exception as e:
        logger.exception("[slowlog] parse_slow_log 解析异常")
        raise HTTPException(500, detail=f"日志解析失败：{e}")

    summary = build_summary(entries)

    try:
        clusters = cluster_slow_queries(entries)
    except Exception as e:
        logger.warning("[slowlog] cluster_slow_queries 异常，跳过聚合: %s", e)
        clusters = []

    return {
        "host":      body.host_ip,
        "path":      body.log_path,
        "date_from": body.date_from,
        "date_to":   body.date_to,
        "summary":   summary,
        "entries":   entries,
        "clusters":  clusters,
    }


@router.get("/api/slowlog/hosts")
async def list_mysql_hosts():
    """返回 CMDB 中有 SSH 凭证的主机列表，供前端下拉选择"""
    cmdb = load_cmdb()
    creds = load_credentials()
    cred_map = {c["id"]: c for c in creds}
    hosts = []
    for instance, info in cmdb.items():
        has_cred = bool(info.get("credential_id") or info.get("ssh_password"))
        hosts.append({
            "instance":      instance,
            "ip":            info.get("ip", ""),
            "hostname":      info.get("hostname", instance),
            "has_credential": has_cred,
            "credential_name": cred_map.get(info.get("credential_id", ""), {}).get("name", ""),
        })
    return {"data": hosts}


@router.get("/api/slowlog/analyze/stream")
async def analyze_stream(
    entries_json: str = Query(..., description="JSON 序列化的慢查询列表"),
    host_ip: str = Query("", description="MySQL 主机 IP"),
    date: str = Query("", description="分析日期"),
):
    """流式 AI 分析慢查询，SSE 格式返回"""
    try:
        entries = json.loads(entries_json)
    except Exception:
        raise HTTPException(400, detail="entries_json 格式错误")

    if not entries:
        raise HTTPException(400, detail="没有可分析的慢查询")

    # 构造分析提示词
    summary = build_summary(entries)
    slow_top = entries[:10]  # 只传前 10 条给 AI，避免 token 超限

    prompt = f"""你是一位 MySQL 数据库性能专家，请分析以下慢查询日志并给出优化建议。

**分析目标**
- 主机：{host_ip or '未知'}
- 日期：{date or '未知'}
- 慢查询总数：{summary['total']}
- 告警数（≥10s）：{summary['alert_count']}
- 平均耗时：{summary['avg_query_time']}s
- 最长耗时：{summary['max_query_time']}s

**TOP 慢查询（最多10条）**
"""
    for i, e in enumerate(slow_top, 1):
        prompt += f"""
[{i}] 耗时={e['query_time']}s | 扫描行={e['rows_examined']} | 返回行={e['rows_sent']} | 用户={e['user']}@{e['host']}
SQL: {e['sql'][:300]}{'...' if len(e['sql']) > 300 else ''}
"""

    prompt += """
**请按以下结构输出分析报告**：
1. 整体评估（问题等级：严重/警告/正常）
2. 主要问题分析（每条 SQL 的问题原因）
3. 具体优化建议（加索引、改写 SQL、分页、缓存等）
4. 优先处理顺序

使用中文输出，格式清晰，直接给出可操作的建议。
"""

    async def event_stream():
        try:
            async for chunk in analyzer.provider.stream(prompt, max_tokens=2048):
                data = json.dumps({"chunk": chunk}, ensure_ascii=False)
                yield f"data: {data}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
