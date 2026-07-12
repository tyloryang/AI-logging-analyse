"""MySQL 慢日志分析路由

路由前缀：/api/slowlog/*
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
from typing import List, Optional

import asyncssh
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import uuid
from pathlib import Path

from slow_log_parser import parse_slow_log, build_summary
from sql_cluster import cluster_slow_queries
from state import load_cmdb, load_credentials, decrypt_password, analyzer
from ssh_utils import ssh_connect_options
from json_snapshot_store import read_json_file, write_json_file

logger = logging.getLogger(__name__)
router = APIRouter()

# SSH 读取超时（秒）
_SSH_READ_TIMEOUT = 120
# 默认读取文件尾部大小（MB）
_DEFAULT_TAIL_MB = 50
# 慢日志固定配置持久化文件（只存 IP/路径/凭证引用，不存明文密码）
_SLOWLOG_CONFIG_FILE = Path(__file__).parent.parent / "data" / "slowlog_configs.json"


# ── SSH 读文件辅助 ─────────────────────────────────────────────────────────────

async def _read_remote_file(
    host: str,
    port: int,
    username: str,
    password: str,
    filepath: str,
    tail_mb: float = _DEFAULT_TAIL_MB,
    date_from: Optional[str] = None,
) -> str:
    """通过 SSH 读取远端文件尾部内容，默认取最后 tail_mb MB 避免超大文件超时"""
    # 构造读取命令：优先按日期行过滤，否则按字节尾截取
    size_bytes = max(1, int(tail_mb * 1024 * 1024))
    if date_from:
        # 找到第一个 >= date_from 的 "# Time:" 行所在位置后读取，兼容大文件
        safe_date = date_from.replace("'", "").replace('"', "")[:10]
        cmd = (
            f"awk '/^# Time:/ && $0 >= \"# Time: {safe_date}\" {{found=1}} found' "
            f"{filepath} || tail -c {size_bytes} {filepath}"
        )
    else:
        cmd = f"tail -c {size_bytes} {filepath}"

    try:
        async with asyncssh.connect(
            **ssh_connect_options(
                host=host,
                port=port,
                username=username,
                password=password,
                connect_timeout=15,
            )
        ) as conn:
            try:
                result = await asyncio.wait_for(
                    conn.run(cmd, check=False),
                    timeout=_SSH_READ_TIMEOUT,
                )
            except asyncio.TimeoutError:
                raise HTTPException(
                    504,
                    detail=f"SSH 读取超时（>{_SSH_READ_TIMEOUT}s），文件过大，请缩小 tail_mb 或设置日期范围",
                )
            if result.returncode not in (0, 1):  # awk 无匹配返回 1 是正常的
                raise HTTPException(502, detail=f"远端命令失败：{result.stderr[:200]}")
            return result.stdout
    except HTTPException:
        raise
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
    date_from:     Optional[str] = None       # "YYYY-MM-DD" 或 "YYYY-MM-DDTHH:MM:SS"
    date_to:       Optional[str] = None       # 纯日期含全天，也支持精确结束时间
    threshold_sec: float = 1.0
    alert_sec:     float = 10.0
    ssh_port:      int   = 22
    ssh_user:      str   = ""
    ssh_password:  str   = ""
    credential_id: str   = ""
    tail_mb:       float = _DEFAULT_TAIL_MB   # 读取文件尾部 MB 数，0=全量（慎用）


class ExportRequest(BaseModel):
    entries:    List[dict]
    host_ip:    str = ""
    date_from:  Optional[str] = None
    date_to:    Optional[str] = None
    fmt:        str = "csv"    # csv | log | json


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

    tail_mb = body.tail_mb if body.tail_mb > 0 else _DEFAULT_TAIL_MB
    try:
        text = await _read_remote_file(
            host, port, username, password, body.log_path,
            tail_mb=tail_mb, date_from=body.date_from,
        )
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


# ── 固定配置 CRUD（保存多组 IP+慢日志路径，选择性查询）──────────────────────────

class SlowLogConfig(BaseModel):
    id:            str   = ""
    name:          str                              # 配置名，如 "订单库-主"
    host_ip:       str
    log_path:      str   = "/mysqldata/mysql/data/3306/mysql-slow.log"
    ssh_port:      int   = 22
    ssh_user:      str   = ""
    credential_id: str   = ""
    threshold_sec: float = 1.0
    alert_sec:     float = 10.0
    tail_mb:       float = _DEFAULT_TAIL_MB


def _load_slowlog_configs() -> list[dict]:
    data = read_json_file(_SLOWLOG_CONFIG_FILE, default=[])
    return data if isinstance(data, list) else []


def _save_slowlog_configs(items: list[dict]) -> None:
    write_json_file(_SLOWLOG_CONFIG_FILE, items, ensure_parent=True)


@router.get("/api/slowlog/configs")
async def list_slowlog_configs():
    """返回已保存的慢日志固定配置列表"""
    return {"data": _load_slowlog_configs()}


@router.post("/api/slowlog/configs")
async def upsert_slowlog_config(body: SlowLogConfig):
    """新增或更新一条固定配置（有 id 则更新，无 id 则新建）"""
    if not body.name.strip():
        raise HTTPException(400, detail="配置名不能为空")
    if not body.host_ip.strip():
        raise HTTPException(400, detail="主机 IP 不能为空")
    configs = _load_slowlog_configs()
    payload = body.model_dump()
    if payload["id"]:
        idx = next((i for i, c in enumerate(configs) if c.get("id") == payload["id"]), -1)
        if idx < 0:
            raise HTTPException(404, detail="配置不存在")
        configs[idx] = payload
    else:
        payload["id"] = uuid.uuid4().hex[:12]
        configs.append(payload)
    _save_slowlog_configs(configs)
    return {"ok": True, "config": payload}


@router.delete("/api/slowlog/configs/{config_id}")
async def delete_slowlog_config(config_id: str):
    """删除一条固定配置"""
    configs = _load_slowlog_configs()
    remaining = [c for c in configs if c.get("id") != config_id]
    if len(remaining) == len(configs):
        raise HTTPException(404, detail="配置不存在")
    _save_slowlog_configs(remaining)
    return {"ok": True}


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


# ── 导出 ──────────────────────────────────────────────────────────────────────

@router.post("/api/slowlog/export")
async def export_slow_log(body: ExportRequest):
    """
    将慢查询列表导出为文件下载。
    fmt=csv  → CSV 表格（Excel 可直接打开）
    fmt=log  → 重建为标准 MySQL 慢日志格式（.log）
    fmt=json → 格式化 JSON（.json）
    """
    entries = body.entries
    if not entries:
        raise HTTPException(400, detail="entries 为空")

    host     = body.host_ip or "unknown"
    date_tag = ""
    if body.date_from:
        date_tag = body.date_from
        if body.date_to and body.date_to != body.date_from:
            date_tag += f"~{body.date_to}"
    filename_date_tag = (date_tag or "all").replace("T", "_").replace(":", "-").replace(" ", "_")

    fmt = (body.fmt or "csv").lower()

    # ── CSV ────────────────────────────────────────────────────────────────
    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "序号", "时间", "耗时(s)", "锁定(s)",
            "扫描行", "返回行", "严重程度",
            "用户", "主机", "告警", "SQL",
        ])
        for e in entries:
            writer.writerow([
                e.get("id", ""),
                e.get("time_str", e.get("time_raw", "")),
                e.get("query_time", ""),
                e.get("lock_time", ""),
                e.get("rows_examined", ""),
                e.get("rows_sent", ""),
                e.get("severity", ""),
                e.get("user", ""),
                e.get("host", ""),
                "是" if e.get("is_alert") else "",
                e.get("sql", "").replace("\n", " "),
            ])
        content  = "\ufeff" + buf.getvalue()   # BOM 保证 Excel 正确识别 UTF-8
        filename = f"slowlog_{host}_{filename_date_tag}.csv"
        return StreamingResponse(
            iter([content.encode("utf-8-sig")]),
            media_type="text/csv; charset=utf-8-sig",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # ── MySQL slow log 格式 ────────────────────────────────────────────────
    if fmt == "log":
        lines = [
            f"# Exported MySQL slow log — host: {host}  date: {date_tag or 'all'}\n",
            f"# Total: {len(entries)} entries\n\n",
        ]
        for e in entries:
            time_str = e.get("time_raw") or e.get("time_str", "")
            lines.append(f"# Time: {time_str}\n")
            lines.append(
                f"# User@Host: {e.get('user','unknown')}[{e.get('user','unknown')}] @ "
                f"[{e.get('host','')}]  Id: {e.get('id','')}\n"
            )
            lines.append(
                f"# Query_time: {e.get('query_time',0):.6f}  "
                f"Lock_time: {e.get('lock_time',0):.6f}  "
                f"Rows_sent: {e.get('rows_sent',0)}  "
                f"Rows_examined: {e.get('rows_examined',0)}\n"
            )
            lines.append(f"SET timestamp={int(0)};\n")
            lines.append(e.get("sql", "").strip() + ";\n\n")

        content  = "".join(lines)
        filename = f"slowlog_{host}_{filename_date_tag}.log"
        return StreamingResponse(
            iter([content.encode("utf-8")]),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # ── JSON ───────────────────────────────────────────────────────────────
    summary  = build_summary(entries)
    payload  = {
        "host":      host,
        "date_from": body.date_from,
        "date_to":   body.date_to,
        "summary":   summary,
        "entries":   entries,
    }
    content  = json.dumps(payload, ensure_ascii=False, indent=2)
    filename = f"slowlog_{host}_{filename_date_tag}.json"
    return StreamingResponse(
        iter([content.encode("utf-8")]),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
