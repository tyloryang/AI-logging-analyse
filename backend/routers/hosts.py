"""CMDB 主机管理（手动录入）+ 主机巡检路由。

路由前缀：/api/hosts/*
"""
import json
import logging
import uuid
from datetime import datetime
from typing import Optional
from urllib.parse import quote

import asyncio
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import io

from state import (
    prom, analyzer,
    load_hosts_list, save_hosts_list,
    load_groups,
    encrypt_password, decrypt_password,
    load_credentials,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_NOW = lambda: datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

# ── 主机 CRUD ──────────────────────────────────────────────────────────────────

class HostCreateRequest(BaseModel):
    hostname:      str = ""   # 可选，留空时自动用 IP 填充
    ip:            str
    platform:      str = "Linux"        # Linux / Windows / Network / Other
    os_version:    str = ""
    cpu_cores:     Optional[int] = None
    memory_gb:     Optional[float] = None
    disk_gb:       Optional[float] = None
    status:        str = "active"       # active / offline / maintenance
    env:           str = "production"   # production / staging / development / testing / dr
    role:          str = ""
    owner:         str = ""
    datacenter:    str = ""
    group:         str = ""
    ssh_port:      int = 22
    ssh_user:      str = ""
    ssh_password:  str = ""
    credential_id: str = ""
    notes:         str = ""
    labels:        dict = {}


class HostUpdateRequest(BaseModel):
    hostname:      Optional[str] = None
    ip:            Optional[str] = None
    platform:      Optional[str] = None
    os_version:    Optional[str] = None
    cpu_cores:     Optional[int] = None
    memory_gb:     Optional[float] = None
    disk_gb:       Optional[float] = None
    status:        Optional[str] = None
    env:           Optional[str] = None
    role:          Optional[str] = None
    owner:         Optional[str] = None
    datacenter:    Optional[str] = None
    group:         Optional[str] = None
    ssh_port:      Optional[int] = None
    ssh_user:      Optional[str] = None
    ssh_password:  Optional[str] = None
    credential_id: Optional[str] = None
    notes:         Optional[str] = None
    labels:        Optional[dict] = None


@router.get("/api/hosts")
async def list_hosts():
    """获取所有手动录入的主机列表。"""
    hosts = load_hosts_list()
    # 脱敏：不返回加密密码
    safe = []
    for h in hosts:
        entry = dict(h)
        entry["ssh_saved"] = bool(entry.pop("ssh_password", ""))
        safe.append(entry)
    return {"data": safe, "total": len(safe)}


@router.post("/api/hosts")
async def create_host(body: HostCreateRequest):
    """新增主机。"""
    hosts = load_hosts_list()
    # 校验 IP 唯一性
    if any(h.get("ip") == body.ip for h in hosts):
        raise HTTPException(status_code=409, detail=f"IP {body.ip} 已存在")
    now = _NOW()
    entry: dict = {
        "id":           str(uuid.uuid4()),
        "hostname":     body.hostname.strip() or body.ip,  # 留空时用 IP
        "ip":           body.ip,
        "platform":     body.platform,
        "os_version":   body.os_version,
        "cpu_cores":    body.cpu_cores,
        "memory_gb":    body.memory_gb,
        "disk_gb":      body.disk_gb,
        "status":       body.status,
        "env":          body.env,
        "role":         body.role,
        "owner":        body.owner,
        "datacenter":   body.datacenter,
        "group":        body.group,
        "ssh_port":     body.ssh_port,
        "ssh_user":     body.ssh_user,
        "ssh_password": encrypt_password(body.ssh_password) if body.ssh_password else "",
        "credential_id": body.credential_id,
        "notes":        body.notes,
        "labels":       body.labels,
        "created_at":   now,
        "updated_at":   now,
    }
    hosts.append(entry)
    save_hosts_list(hosts)
    result = dict(entry)
    result["ssh_saved"] = bool(result.pop("ssh_password", ""))
    return result


@router.put("/api/hosts/{host_id}")
async def update_host(host_id: str, body: HostUpdateRequest):
    """更新主机信息。"""
    hosts = load_hosts_list()
    idx = next((i for i, h in enumerate(hosts) if h.get("id") == host_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="主机不存在")
    host = hosts[idx]
    fields = ["hostname", "ip", "platform", "os_version", "cpu_cores", "memory_gb",
              "disk_gb", "status", "env", "role", "owner", "datacenter", "group",
              "ssh_port", "ssh_user", "credential_id", "notes", "labels"]
    for f in fields:
        val = getattr(body, f)
        if val is not None:
            host[f] = val
    if body.ssh_password is not None:
        host["ssh_password"] = encrypt_password(body.ssh_password) if body.ssh_password else ""
    host["updated_at"] = _NOW()
    hosts[idx] = host
    save_hosts_list(hosts)
    result = dict(host)
    result["ssh_saved"] = bool(result.pop("ssh_password", ""))
    return result


@router.delete("/api/hosts/{host_id}")
async def delete_host(host_id: str):
    """删除主机。"""
    hosts = load_hosts_list()
    new_hosts = [h for h in hosts if h.get("id") != host_id]
    if len(new_hosts) == len(hosts):
        raise HTTPException(status_code=404, detail="主机不存在")
    save_hosts_list(new_hosts)
    return {"ok": True}


# ── SSH 同步系统信息 ─────────────────────────────────────────────────────────

_SYNC_SCRIPT_SHELL = r"""
OS=$(grep -m1 PRETTY_NAME /etc/os-release 2>/dev/null | cut -d'"' -f2)
[ -z "$OS" ] && OS=$(lsb_release -d 2>/dev/null | awk -F'\t' '{print $2}')
[ -z "$OS" ] && OS=$(uname -sr 2>/dev/null)
CPU=$(nproc 2>/dev/null)
[ -z "$CPU" ] && CPU=$(grep -c '^processor' /proc/cpuinfo 2>/dev/null)
[ -z "$CPU" ] && CPU=0
MEM_KB=$(awk '/MemTotal/{print $2}' /proc/meminfo 2>/dev/null)
[ -z "$MEM_KB" ] && MEM_KB=0
DISK_KB=$(df / 2>/dev/null | awk 'NR==2{print $2}')
[ -z "$DISK_KB" ] && DISK_KB=0
HN=$(hostname -s 2>/dev/null)
[ -z "$HN" ] && HN=$(hostname 2>/dev/null)
echo "OS_VER=${OS}"
echo "CPU_CORES=${CPU}"
echo "MEM_KB=${MEM_KB}"
echo "DISK_KB=${DISK_KB}"
echo "HOSTNAME=${HN}"
"""


def _ssh_error_msg(e: Exception) -> str:
    """把 asyncssh / asyncio 异常转为对用户友好的中文提示。"""
    import asyncssh as _assh
    name = type(e).__name__
    msg  = str(e).strip()
    if isinstance(e, (TimeoutError, asyncio.TimeoutError)) or name == "TimeoutError":
        return "连接超时，请检查主机 IP 是否可达、SSH 端口是否开放"
    if isinstance(e, _assh.PermissionDenied):
        return "SSH 认证失败，请检查用户名和密码是否正确"
    if isinstance(e, _assh.ConnectionLost):
        return "SSH 连接中断"
    if isinstance(e, _assh.DisconnectError):
        return f"SSH 断开连接：{msg or name}"
    if isinstance(e, OSError):
        if "refused" in msg.lower() or "111" in msg:
            return "SSH 连接被拒绝，请检查目标主机 SSH 服务是否运行"
        if "network" in msg.lower() or "unreachable" in msg.lower():
            return "网络不可达，请检查网络连接"
        return f"网络错误：{msg or name}"
    if isinstance(e, ValueError):
        return msg or name
    return f"{name}：{msg}" if msg else name


async def _ssh_sync(host: dict) -> dict:
    """通过 SSH 连接主机，读取系统基本信息，返回可更新字段 dict。"""
    import asyncssh

    ip       = host.get("ip", "")
    port     = int(host.get("ssh_port") or 22)
    username = host.get("ssh_user") or "root"

    # 凭证库优先
    password = None
    cred_id = host.get("credential_id", "")
    if cred_id:
        creds = load_credentials()
        cred = next((c for c in creds if c.get("id") == cred_id), None)
        if cred:
            username = cred.get("username", username)
            raw = cred.get("password", "")
            if raw:
                try:
                    password = decrypt_password(raw)
                except Exception:
                    password = raw

    # 主机自身密码
    if not password:
        enc_pw = host.get("ssh_password", "")
        if enc_pw:
            try:
                password = decrypt_password(enc_pw)
            except Exception:
                pass

    if not ip:
        raise ValueError("主机没有配置 IP")
    if not password:
        raise ValueError("主机未配置 SSH 密码，请先在编辑页面填写 SSH 密码或关联凭证")

    connect_kwargs = dict(
        host=ip, port=port, username=username, password=password,
        known_hosts=None, connect_timeout=8,
    )

    async with asyncssh.connect(**connect_kwargs) as conn:
        result = await conn.run(_SYNC_SCRIPT_SHELL, timeout=15)
        output = result.stdout or ""

    info: dict = {}
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("OS_VER="):
            v = line[7:].strip()
            if v:
                info["os_version"] = v
        elif line.startswith("CPU_CORES="):
            try:
                info["cpu_cores"] = int(line[10:].strip())
            except Exception:
                pass
        elif line.startswith("MEM_KB="):
            try:
                kb = int(line[7:].strip())
                info["memory_gb"] = round(kb / 1024 / 1024, 1) if kb > 0 else None
            except Exception:
                pass
        elif line.startswith("DISK_KB="):
            try:
                kb = int(line[8:].strip())
                info["disk_gb"] = round(kb / 1024 / 1024, 1) if kb > 0 else None
            except Exception:
                pass
        elif line.startswith("HOSTNAME="):
            v = line[9:].strip()
            if v:
                info["hostname"] = v

    return info


@router.post("/api/hosts/{host_id}/sync")
async def sync_host_info(host_id: str):
    """通过 SSH 同步主机系统信息（OS版本、CPU、内存、磁盘、主机名）。"""
    hosts = load_hosts_list()
    idx = next((i for i, h in enumerate(hosts) if h.get("id") == host_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="主机不存在")
    host = hosts[idx]
    try:
        info = await _ssh_sync(host)
    except Exception as e:
        logger.warning("[sync] 主机 %s (%s) 同步失败: %s: %s",
                       host.get("hostname"), host.get("ip"), type(e).__name__, e)
        raise HTTPException(status_code=400, detail=_ssh_error_msg(e))

    if not info:
        raise HTTPException(status_code=400, detail="SSH 连接成功但未获取到系统信息，请确认 shell 可正常执行")

    # 更新字段
    for k, v in info.items():
        if v is not None:
            host[k] = v
    host["updated_at"] = _NOW()
    hosts[idx] = host
    save_hosts_list(hosts)

    result = dict(host)
    result["ssh_saved"] = bool(result.pop("ssh_password", ""))
    return {"ok": True, "updated": info, "host": result}


# ── 巡检（基于 Prometheus，使用 CMDB 中的 IP 匹配实例）──────────────────────

def _inspection_issue_counts(results: list[dict]) -> list[tuple[str, int]]:
    counter: dict[str, int] = {}
    for result in results:
        for check in result.get("checks", []):
            if check.get("status") == "normal":
                continue
            item = check.get("item", "未知项")
            counter[item] = counter.get(item, 0) + 1
    return sorted(counter.items(), key=lambda item: item[1], reverse=True)


def _build_inspection_fallback_summary(
    results: list[dict], summary: dict, error: Exception | None = None
) -> str:
    total    = summary.get("total", len(results))
    normal   = summary.get("normal", 0)
    warning  = summary.get("warning", 0)
    critical = summary.get("critical", 0)
    issue_counts   = _inspection_issue_counts(results)
    top_issue_text = "、".join(
        f"{item}（{count}台）" for item, count in issue_counts[:3]
    ) or "暂未发现重复性异常项"

    abnormal_hosts = [r for r in results if r.get("overall") != "normal"]
    abnormal_hosts.sort(
        key=lambda item: (
            {"critical": 2, "warning": 1, "normal": 0}.get(item.get("overall", "normal"), 0),
            sum(1 for c in item.get("checks", []) if c.get("status") != "normal"),
        ),
        reverse=True,
    )
    top_host_text = "；".join(
        f"{host.get('hostname') or host.get('instance')}({host.get('ip', '-')})"
        for host in abnormal_hosts[:3]
    ) or "暂无异常主机"

    parts = [
        f"本次巡检共覆盖 {total} 台主机，其中正常 {normal} 台、警告 {warning} 台、严重 {critical} 台。",
        f"当前最集中的异常项为：{top_issue_text}。",
        f"需优先关注的主机：{top_host_text}。",
        "建议先处理严重主机，再按高频异常项排查资源瓶颈、容量风险和连接状态波动。",
        "未来24小时若不处理，异常项可能继续扩散到更多主机，并导致性能抖动、告警增加或服务稳定性下降。",
    ]
    if error:
        parts.append(f"AI 服务暂不可用，当前显示的是规则摘要（{error}）。")
    return "\n\n".join(parts)


def _cmdb_instances_for_group(group_id: str) -> tuple[Optional[list[str]], str]:
    """根据分组 ID 从 CMDB 获取 Prometheus 实例列表（ip:9100），返回 (instances, group_name)。"""
    hosts = load_hosts_list()
    groups = load_groups()
    g = next((g for g in groups if g["id"] == group_id), None)
    group_name = g["name"] if g else group_id
    # 用 ip:9100 作为 Prometheus instance 格式
    instances = [f"{h['ip']}:9100" for h in hosts if h.get("group") == group_id and h.get("ip")]
    return instances or None, group_name


@router.get("/api/hosts/inspect")
async def inspect_all_hosts(group_id: Optional[str] = Query(None)):
    """巡检主机，支持按分组过滤，SSE 流式返回。"""
    async def generate():
        try:
            instances: Optional[list[str]] = None
            group_name: str = ""
            if group_id:
                instances, group_name = _cmdb_instances_for_group(group_id)
                if not instances:
                    yield f"data: {json.dumps({'type': 'error', 'message': f'分组「{group_name}」下没有主机或主机无 IP'}, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"
                    return

            results = await prom.inspect_hosts(instances=instances)

            if group_id:
                host_map = {h["ip"]: h for h in load_hosts_list() if h.get("ip")}
                for r in results:
                    ip = r.get("ip", "")
                    r.setdefault("group", host_map.get(ip, {}).get("group", ""))

            summary = {
                "total":      len(results),
                "normal":     sum(1 for r in results if r["overall"] == "normal"),
                "warning":    sum(1 for r in results if r["overall"] == "warning"),
                "critical":   sum(1 for r in results if r["overall"] == "critical"),
                "group_id":   group_id or "",
                "group_name": group_name,
            }
            yield f"data: {json.dumps({'type': 'inspect_data', 'data': results, 'summary': summary}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            logger.exception("巡检 SSE 流异常")
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class InspectAIRequest(BaseModel):
    results: list
    summary: dict


@router.post("/api/hosts/inspect/ai")
async def inspect_ai_summary(req: InspectAIRequest):
    """对已有巡检结果做 AI 流式分析（按需调用）。"""
    async def generate():
        provider_name = analyzer.provider_name
        yield f"data: {json.dumps({'type': 'ai_meta', 'provider': provider_name, 'fallback': False}, ensure_ascii=False)}\n\n"
        try:
            async for chunk in analyzer.generate_inspection_summary(req.results, req.summary):
                yield f"data: {json.dumps({'type': 'ai_chunk', 'text': chunk}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            logger.exception("巡检 AI 流式总结失败，降级为规则摘要")
            fallback = _build_inspection_fallback_summary(req.results, req.summary, exc)
            yield f"data: {json.dumps({'type': 'ai_meta', 'provider': provider_name, 'fallback': True}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'ai_chunk', 'text': fallback}, ensure_ascii=False)}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class NotifyGroupsRequest(BaseModel):
    results: list
    summary: dict = {}
    ai_text: str = ""
    group_id: str = ""


@router.post("/api/hosts/inspect/notify-groups")
async def notify_groups_inspect(req: NotifyGroupsRequest):
    """将巡检结果按分组推送到飞书。"""
    try:
        from scheduler import _send_group_inspect_notifications
        results = await _send_group_inspect_notifications(
            req.results,
            force=True,
            group_id=(req.group_id or "").strip(),
        )
        sent    = [item for item in results if item.get("push", {}).get("ok")]
        failed  = [item for item in results if item.get("push") and not item.get("push", {}).get("ok")]
        skipped = [item for item in results if item.get("skipped")]
        target_group_name = next(
            (item.get("group_name") or item.get("group_id") for item in results
             if item.get("group_name") or item.get("group_id")),
            (req.group_id or "").strip(),
        )
        if sent:
            message = f"已推送分组「{target_group_name}」到飞书" if req.group_id else f"已推送 {len(sent)} 个分组到飞书"
            if failed:
                message += f"，{len(failed)} 个分组失败"
        else:
            message = (
                f"分组「{target_group_name}」没有成功推送，请检查巡检数据和飞书 Webhook 配置"
                if req.group_id else "没有成功推送的分组，请检查分组主机和飞书 Webhook 配置"
            )
        return {
            "ok": bool(sent),
            "message": message,
            "summary": {"sent": len(sent), "failed": len(failed), "skipped": len(skipped)},
            "results": results,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class InspectExcelRequest(BaseModel):
    results: list
    summary: dict
    ai_text: str = ""


@router.post("/api/hosts/inspect/excel")
async def export_inspect_excel(req: InspectExcelRequest):
    """根据传入的巡检结果生成 Excel 文件并下载。"""
    try:
        results = req.results
        summary = req.summary
        ai_text = req.ai_text
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        wb = Workbook()

        STATUS_COLOR = {"normal": "FF67C23A", "warning": "FFE6A23C", "critical": "FFF56C6C"}
        STATUS_TEXT  = {"normal": "正常", "warning": "警告", "critical": "严重"}

        def hfill(color="FF1F3A5F"):
            return PatternFill("solid", fgColor=color)

        def tborder():
            s = Side(style="thin", color="FFCCCCCC")
            return Border(left=s, right=s, top=s, bottom=s)

        def col_widths(ws, widths):
            for i, w in enumerate(widths, 1):
                ws.column_dimensions[get_column_letter(i)].width = w

        def header_row(ws, headers, row=1):
            for col, h in enumerate(headers, 1):
                c           = ws.cell(row=row, column=col, value=h)
                c.font      = Font(bold=True, color="FFFFFFFF", size=10)
                c.fill      = hfill()
                c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                c.border    = tborder()

        def data_cell(ws, row, col, value, status=None):
            c           = ws.cell(row=row, column=col, value=value)
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            c.border    = tborder()
            if status and status in STATUS_COLOR:
                c.fill = PatternFill("solid", fgColor=STATUS_COLOR[status])
                c.font = Font(color="FFFFFFFF", size=9)
            else:
                c.font = Font(size=9)

        ws1 = wb.active
        ws1.title = "巡检概况"
        ws1.column_dimensions["A"].width = 22
        ws1.column_dimensions["B"].width = 40

        def s1(r, k, v, bold=False):
            ck = ws1.cell(row=r, column=1, value=k)
            cv = ws1.cell(row=r, column=2, value=v)
            ck.font      = Font(bold=True, color="FFFFFFFF", size=10)
            ck.fill      = hfill("FF243850")
            cv.font      = Font(bold=bold, size=10)
            ck.alignment = cv.alignment = Alignment(vertical="center", wrap_text=True)
            ck.border    = cv.border    = tborder()
            ws1.row_dimensions[r].height = 18

        s1(1, "巡检时间",     now_str, bold=True)
        s1(2, "巡检主机总数", summary.get("total", 0))
        s1(3, "正常主机",     summary.get("normal", 0))
        s1(4, "警告主机",     summary.get("warning", 0))
        s1(5, "严重主机",     summary.get("critical", 0))

        issue_cnt: dict[str, int] = {}
        for r in results:
            for c in r.get("checks", []):
                if c.get("status") != "normal":
                    issue_cnt[c.get("item", "未知")] = issue_cnt.get(c.get("item", "未知"), 0) + 1
        top_issues = sorted(issue_cnt.items(), key=lambda x: x[1], reverse=True)[:8]

        ws1.cell(row=7, column=1, value="高频异常项").font = Font(bold=True, size=10)
        header_row(ws1, ["异常检查项", "影响主机数"], row=8)
        for i, (item, cnt) in enumerate(top_issues, 9):
            ws1.cell(row=i, column=1, value=item).border    = tborder()
            ws1.cell(row=i, column=2, value=cnt).border     = tborder()
            ws1.cell(row=i, column=1).font      = Font(size=9)
            ws1.cell(row=i, column=2).font      = Font(size=9)
            ws1.cell(row=i, column=1).alignment = Alignment(vertical="center")
            ws1.cell(row=i, column=2).alignment = Alignment(horizontal="center", vertical="center")

        ai_start = 9 + len(top_issues) + 2
        ws1.cell(row=ai_start, column=1, value="AI 分析总结").font = Font(bold=True, size=10)
        if ai_text:
            c           = ws1.cell(row=ai_start + 1, column=1, value=ai_text)
            c.font      = Font(size=9)
            c.alignment = Alignment(vertical="top", wrap_text=True)
            c.border    = tborder()
            ws1.merge_cells(start_row=ai_start + 1, start_column=1, end_row=ai_start + 1, end_column=2)
            ws1.row_dimensions[ai_start + 1].height = max(60, len(ai_text) // 3)

        ws2 = wb.create_sheet("全部主机明细")
        headers2 = [
            "主机名", "IP地址", "操作系统", "状态", "巡检结果",
            "CPU使用率(%)", "内存使用率(%)", "内存总量(GB)",
            "负载(5m)", "网络收(Mbps)", "网络发(Mbps)",
            "TCP连接数", "运行时长(天)", "磁盘分区详情",
        ]
        header_row(ws2, headers2)
        col_widths(ws2, [18, 16, 22, 10, 10, 14, 14, 14, 10, 14, 14, 12, 12, 40])
        ws2.row_dimensions[1].height = 22

        for ri, h in enumerate(results, 2):
            overall      = h.get("overall", "normal")
            status_label = STATUS_TEXT.get(overall, overall)

            def fmt(v, decimals=1):
                return round(v, decimals) if v is not None else "-"

            m           = h.get("metrics") or {}
            uptime_days = "-"
            us = m.get("uptime_seconds")
            if us is not None:
                uptime_days = round(us / 86400, 1)

            partitions = h.get("partitions") or []
            disk_text  = "  ".join(
                f"{pt.get('mountpoint','?')} {pt.get('usage_pct','-')}%"
                for pt in partitions
            ) if partitions else "-"

            row_vals = [
                h.get("hostname", "-"), h.get("ip", "-"), h.get("os", "-"),
                h.get("state", "-"), status_label,
                fmt(m.get("cpu_usage")), fmt(m.get("mem_usage")), fmt(m.get("mem_total_gb")),
                fmt(m.get("load5")), fmt(m.get("net_recv_mbps")), fmt(m.get("net_send_mbps")),
                m.get("tcp_estab") or "-", uptime_days, disk_text,
            ]
            for ci, val in enumerate(row_vals, 1):
                data_cell(ws2, ri, ci, val, overall if ci == 5 else None)
            ws2.row_dimensions[ri].height = 16

        ws2.freeze_panes = "A2"

        ws3 = wb.create_sheet("异常项明细")
        headers3 = ["主机名", "IP地址", "检查项", "当前值", "状态", "阈值说明"]
        header_row(ws3, headers3)
        col_widths(ws3, [18, 16, 20, 20, 10, 30])
        ws3.row_dimensions[1].height = 22

        ri3 = 2
        for h in results:
            for ck in [c for c in h.get("checks", []) if c.get("status") != "normal"]:
                status = ck.get("status", "warning")
                row3 = [
                    h.get("hostname", "-"), h.get("ip", "-"),
                    ck.get("item", "-"), ck.get("value", "-"),
                    STATUS_TEXT.get(status, status), ck.get("threshold", "-"),
                ]
                for ci, val in enumerate(row3, 1):
                    data_cell(ws3, ri3, ci, val, status if ci == 5 else None)
                ws3.row_dimensions[ri3].height = 16
                ri3 += 1

        ws3.freeze_panes = "A2"

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        filename     = f"主机巡检_{now_str.replace(':', '-')}.xlsx"
        encoded_name = quote(filename, encoding="utf-8")
        return Response(
            content=buf.read(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
        )
    except Exception as e:
        logger.exception("巡检 Excel 导出失败")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/hosts/{host_id}/inspect")
async def inspect_single_host(host_id: str):
    """巡检单台主机（按 CMDB ID 查找 IP，再查 Prometheus）。"""
    hosts = load_hosts_list()
    host = next((h for h in hosts if h.get("id") == host_id), None)
    if not host:
        raise HTTPException(status_code=404, detail="主机不存在")
    ip = host.get("ip", "")
    if not ip:
        raise HTTPException(status_code=400, detail="主机没有配置 IP")
    try:
        instance = f"{ip}:9100"
        results = await prom.inspect_hosts(instances=[instance])
        if not results:
            raise HTTPException(status_code=404, detail="Prometheus 中未找到该主机指标（请确认 node_exporter 已运行）")
        return results[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
