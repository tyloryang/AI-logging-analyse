"""CMDB 主机管理（手动录入）+ 主机巡检路由。

路由前缀：/api/hosts/*
"""
import json
import logging
import os
import shlex
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import asyncio
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Depends
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
from auth.deps import current_user
from auth.models import User

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import io

from state import (
    prom, analyzer,
    REPORTS_DIR,
    load_hosts_list, save_hosts_list,
    load_groups,
    encrypt_password, decrypt_password,
    load_credentials,
    get_user_allowed_groups,
    load_user_groups, save_user_groups,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_NOW = lambda: datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _filter_hosts_by_user(hosts: list[dict], user: User) -> list[dict]:
    """超管可见全部；普通用户只能看自己分组内的主机。"""
    if user.is_superuser:
        return hosts
    allowed = get_user_allowed_groups(user.id)
    if allowed is None:
        return hosts  # 兜底：超管标记缺失时放行
    # allowed 为空列表 → 只能看无分组主机；有值 → 只能看对应分组
    return [h for h in hosts if h.get("group", "") in allowed]


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
        return value if value > 0 else default
    except Exception:
        logger.warning("[hosts] 环境变量 %s=%r 不是有效数字，使用默认值 %s", name, raw, default)
        return default


_HOST_SYNC_SSH_CONNECT_TIMEOUT = _env_float("HOST_SYNC_SSH_CONNECT_TIMEOUT", 12.0)
_HOST_SYNC_SSH_COMMAND_TIMEOUT = _env_float("HOST_SYNC_SSH_COMMAND_TIMEOUT", 20.0)

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
async def list_hosts(user: User = Depends(current_user)):
    """获取主机列表（非管理员只能看自己分组内的主机）。"""
    hosts = _filter_hosts_by_user(load_hosts_list(), user)
    credentials = {c.get("id"): c for c in load_credentials()}
    # 脱敏：不返回加密密码
    safe = []
    for h in hosts:
        entry = dict(h)
        credential_id = entry.get("credential_id", "")
        entry["ssh_saved"] = bool(entry.pop("ssh_password", "")) or bool(credential_id)
        if credential_id and credential_id in credentials:
            cred = credentials[credential_id]
            entry["credential_name"] = cred.get("name", credential_id)
            entry["credential_username"] = cred.get("username", "")
            entry["credential_port"] = cred.get("port", 22)
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
        "ssh_password": "" if body.credential_id else (encrypt_password(body.ssh_password) if body.ssh_password else ""),
        "credential_id": body.credential_id,
        "notes":        body.notes,
        "labels":       body.labels,
        "created_at":   now,
        "updated_at":   now,
    }
    hosts.append(entry)
    save_hosts_list(hosts)
    result = dict(entry)
    result["ssh_saved"] = bool(result.pop("ssh_password", "")) or bool(result.get("credential_id"))
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
    if host.get("credential_id"):
        host["ssh_password"] = ""
    elif body.ssh_password:
        host["ssh_password"] = encrypt_password(body.ssh_password) if body.ssh_password else ""
    host["updated_at"] = _NOW()
    hosts[idx] = host
    save_hosts_list(hosts)
    result = dict(host)
    result["ssh_saved"] = bool(result.pop("ssh_password", "")) or bool(result.get("credential_id"))
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


# ── 导出 / 导入 ──────────────────────────────────────────────────────────────

_EXPORT_COLS = [
    ("hostname",    "主机名"),
    ("ip",          "IP 地址"),
    ("platform",    "平台"),
    ("os_version",  "操作系统版本"),
    ("cpu_cores",   "CPU 核心数"),
    ("memory_gb",   "内存(GB)"),
    ("disk_gb",     "磁盘(GB)"),
    ("status",      "状态"),
    ("env",         "环境"),
    ("role",        "用途/角色"),
    ("owner",       "负责人"),
    ("datacenter",  "机房/区域"),
    ("ssh_port",    "SSH 端口"),
    ("ssh_user",    "SSH 用户名"),
    ("notes",       "备注"),
]
_ENV_LABEL = {"production":"生产","staging":"预发","development":"开发","testing":"测试","dr":"容灾"}
_STATUS_LABEL = {"active":"在线","offline":"离线","maintenance":"维护中"}


@router.get("/api/hosts/export")
async def export_hosts(user: User = Depends(current_user)):
    """导出主机 Excel（非管理员只能导出自己分组的主机）。"""
    hosts = _filter_hosts_by_user(load_hosts_list(), user)
    groups = load_groups()
    group_map = {g["id"]: g["name"] for g in groups}

    wb = Workbook()
    ws = wb.active
    ws.title = "主机列表"

    header_fill = PatternFill("solid", fgColor="FF1F3A5F")
    header_font = Font(bold=True, color="FFFFFFFF", size=10)
    border_side = Side(style="thin", color="FFCCCCCC")
    cell_border = Border(left=border_side, right=border_side, top=border_side, bottom=border_side)
    center = Alignment(horizontal="center", vertical="center")

    # 表头（含"分组"列）
    headers = [label for _, label in _EXPORT_COLS] + ["分组"]
    for col, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=col, value=h)
        c.fill = header_fill
        c.font = header_font
        c.alignment = center
        c.border = cell_border

    # 列宽
    widths = [16, 16, 10, 22, 10, 10, 10, 10, 10, 18, 12, 16, 8, 12, 24, 16]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[1].height = 22
    ws.freeze_panes = "A2"

    for row_idx, h in enumerate(hosts, 2):
        for col_idx, (field, _) in enumerate(_EXPORT_COLS, 1):
            val = h.get(field, "")
            if field == "status":
                val = _STATUS_LABEL.get(val, val)
            elif field == "env":
                val = _ENV_LABEL.get(val, val)
            c = ws.cell(row=row_idx, column=col_idx, value=val if val is not None else "")
            c.alignment = Alignment(vertical="center", wrap_text=False)
            c.border = cell_border
            c.font = Font(size=9)
        # 分组列
        grp_col = len(_EXPORT_COLS) + 1
        c = ws.cell(row=row_idx, column=grp_col, value=group_map.get(h.get("group", ""), ""))
        c.alignment = Alignment(vertical="center")
        c.border = cell_border
        c.font = Font(size=9)
        ws.row_dimensions[row_idx].height = 16

    # 说明 sheet
    ws2 = wb.create_sheet("填写说明")
    tips = [
        ("字段", "可选值 / 说明"),
        ("主机名", "可选，留空自动用 IP"),
        ("IP 地址", "必填，不能重复"),
        ("平台", "Linux / Windows / Network / Other"),
        ("状态", "在线 / 离线 / 维护中"),
        ("环境", "生产 / 预发 / 开发 / 测试 / 容灾"),
        ("SSH 端口", "默认 22"),
        ("分组", "填写分组名称（导入时自动匹配）"),
    ]
    for r, (k, v) in enumerate(tips, 1):
        ws2.cell(row=r, column=1, value=k).font = Font(bold=True, size=10)
        ws2.cell(row=r, column=2, value=v).font = Font(size=10)
    ws2.column_dimensions["A"].width = 14
    ws2.column_dimensions["B"].width = 40

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    now_str = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"主机CMDB_{now_str}.xlsx"
    encoded = quote(filename, encoding="utf-8")
    return Response(
        content=buf.read(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )


@router.post("/api/hosts/import")
async def import_hosts(
    file: UploadFile = File(...),
    conflict: str = Query("skip", description="重复 IP 处理策略：skip=跳过 / update=覆盖"),
):
    """从 Excel 或 CSV 文件批量导入主机。返回导入摘要。"""
    from openpyxl import load_workbook
    import csv

    content = await file.read()
    filename = file.filename or ""
    now = _NOW()

    # 解析文件
    rows: list[dict] = []
    if filename.endswith(".csv"):
        text = content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(text.splitlines())
        rows = list(reader)
    elif filename.endswith((".xlsx", ".xls")):
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        headers_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), [])
        col_names = [str(h).strip() if h else "" for h in headers_row]
        for row in ws.iter_rows(min_row=2, values_only=True):
            rows.append({col_names[i]: (str(v).strip() if v is not None else "") for i, v in enumerate(row) if i < len(col_names)})
        wb.close()
    else:
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 或 .csv 文件")

    # 列名映射（中文表头 → 字段名）
    _col_map = {v: k for k, v in _EXPORT_COLS}
    _col_map.update({k: k for k, _ in _EXPORT_COLS})  # 英文字段名也接受

    groups = load_groups()
    group_name_map = {g["name"]: g["id"] for g in groups}

    hosts = load_hosts_list()
    existing_ips = {h.get("ip", ""): i for i, h in enumerate(hosts)}

    added = skipped = updated = errors = 0
    error_details: list[str] = []

    for row_num, raw in enumerate(rows, 2):
        # 映射列名
        entry: dict = {}
        for raw_key, val in raw.items():
            field = _col_map.get(raw_key.strip())
            if field:
                entry[field] = val

        ip = entry.get("ip", "").strip()
        if not ip:
            error_details.append(f"第 {row_num} 行：IP 地址为空，跳过")
            errors += 1
            continue

        # 数值转换
        for num_field in ("cpu_cores",):
            v = entry.get(num_field, "")
            try:
                entry[num_field] = int(float(v)) if v else None
            except (ValueError, TypeError):
                entry[num_field] = None
        for float_field in ("memory_gb", "disk_gb"):
            v = entry.get(float_field, "")
            try:
                entry[float_field] = round(float(v), 1) if v else None
            except (ValueError, TypeError):
                entry[float_field] = None
        # ssh_port
        try:
            entry["ssh_port"] = int(entry.get("ssh_port", 22) or 22)
        except (ValueError, TypeError):
            entry["ssh_port"] = 22

        # 中文状态/环境反转
        _rev_status = {v: k for k, v in _STATUS_LABEL.items()}
        _rev_env    = {v: k for k, v in _ENV_LABEL.items()}
        entry["status"] = _rev_status.get(entry.get("status", ""), entry.get("status", "active")) or "active"
        entry["env"]    = _rev_env.get(entry.get("env", ""), entry.get("env", "production")) or "production"

        # 分组名称 → ID
        grp_name = entry.pop("分组", "") or ""
        entry["group"] = group_name_map.get(grp_name, entry.get("group", ""))

        entry.setdefault("hostname", ip)
        entry.setdefault("platform", "Linux")

        if ip in existing_ips:
            if conflict == "update":
                idx = existing_ips[ip]
                # 保留原有 id / 密码 / 创建时间
                preserved = {k: hosts[idx].get(k) for k in ("id", "ssh_password", "credential_id", "created_at", "labels")}
                hosts[idx].update(entry)
                hosts[idx].update(preserved)
                hosts[idx]["updated_at"] = now
                updated += 1
            else:
                skipped += 1
        else:
            entry["id"] = str(uuid.uuid4())
            entry.setdefault("labels", {})
            entry["ssh_password"] = ""
            entry["credential_id"] = ""
            entry["created_at"] = now
            entry["updated_at"] = now
            hosts.append(entry)
            existing_ips[ip] = len(hosts) - 1
            added += 1

    save_hosts_list(hosts)
    return {
        "ok": True,
        "total": len(rows),
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "error_details": error_details[:20],
        "message": f"导入完成：新增 {added} 台，更新 {updated} 台，跳过 {skipped} 台，错误 {errors} 条",
    }


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

cpu_snapshot() {
  awk '/^cpu /{print $2" "$3" "$4" "$5" "$6" "$7" "$8" "$9}' /proc/stat 2>/dev/null
}
net_snapshot() {
  awk 'NR>2 {gsub(":","",$1); if ($1!="lo") {rx+=$2; tx+=$10}} END{print rx+0" "tx+0}' /proc/net/dev 2>/dev/null
}
diskio_snapshot() {
  awk '$3 ~ /^(sd[a-z]+|vd[a-z]+|xvd[a-z]+|hd[a-z]+|nvme[0-9]+n[0-9]+)$/ {r+=$6; w+=$10} END{print (r+0)*512" "(w+0)*512}' /proc/diskstats 2>/dev/null
}

CPU_A=$(cpu_snapshot)
NET_A=$(net_snapshot)
DIO_A=$(diskio_snapshot)
sleep 1
CPU_B=$(cpu_snapshot)
NET_B=$(net_snapshot)
DIO_B=$(diskio_snapshot)

CPU_USAGE=$(awk -v a="$CPU_A" -v b="$CPU_B" 'BEGIN{
  split(a,x); split(b,y);
  idle1=x[4]+x[5]; idle2=y[4]+y[5];
  for(i=1;i<=8;i++){total1+=x[i]; total2+=y[i]}
  dt=total2-total1; di=idle2-idle1;
  if(dt>0) printf "%.1f", (dt-di)*100/dt; else print "";
}')
MEM_USAGE=$(awk '/MemTotal/{t=$2}/MemAvailable/{a=$2}END{if(t>0) printf "%.1f", (t-a)*100/t; else print ""}' /proc/meminfo 2>/dev/null)
LOAD5=$(awk '{print $2}' /proc/loadavg 2>/dev/null)
UPTIME_SECONDS=$(awk '{printf "%.0f", $1}' /proc/uptime 2>/dev/null)
NET_RX_BPS=$(awk -v a="$NET_A" -v b="$NET_B" 'BEGIN{split(a,x); split(b,y); v=y[1]-x[1]; print v>0?v:0}')
NET_TX_BPS=$(awk -v a="$NET_A" -v b="$NET_B" 'BEGIN{split(a,x); split(b,y); v=y[2]-x[2]; print v>0?v:0}')
DIO_READ_BPS=$(awk -v a="$DIO_A" -v b="$DIO_B" 'BEGIN{split(a,x); split(b,y); v=y[1]-x[1]; print v>0?v:0}')
DIO_WRITE_BPS=$(awk -v a="$DIO_A" -v b="$DIO_B" 'BEGIN{split(a,x); split(b,y); v=y[2]-x[2]; print v>0?v:0}')

if command -v ss >/dev/null 2>&1; then
  TCP_CONN=$(ss -ant 2>/dev/null | awk 'NR>1{c++}END{print c+0}')
  TCP_TIME_WAIT=$(ss -ant state time-wait 2>/dev/null | awk 'NR>1{c++}END{print c+0}')
elif command -v netstat >/dev/null 2>&1; then
  TCP_CONN=$(netstat -ant 2>/dev/null | awk 'NR>2{c++}END{print c+0}')
  TCP_TIME_WAIT=$(netstat -ant 2>/dev/null | awk '$NF=="TIME_WAIT"{c++}END{print c+0}')
else
  TCP_CONN=$(awk 'FNR>1{c++}END{print c+0}' /proc/net/tcp /proc/net/tcp6 2>/dev/null)
  TCP_TIME_WAIT=$(awk 'FNR>1 && $4=="06"{c++}END{print c+0}' /proc/net/tcp /proc/net/tcp6 2>/dev/null)
fi

echo "OS_VER=${OS}"
echo "CPU_CORES=${CPU}"
echo "MEM_KB=${MEM_KB}"
echo "DISK_KB=${DISK_KB}"
echo "HOSTNAME=${HN}"
echo "CPU_USAGE_PCT=${CPU_USAGE}"
echo "MEM_USAGE_PCT=${MEM_USAGE}"
echo "LOAD5=${LOAD5}"
echo "UPTIME_SECONDS=${UPTIME_SECONDS}"
echo "DISK_IO_READ_BPS=${DIO_READ_BPS}"
echo "DISK_IO_WRITE_BPS=${DIO_WRITE_BPS}"
echo "NETWORK_RX_BPS=${NET_RX_BPS}"
echo "NETWORK_TX_BPS=${NET_TX_BPS}"
echo "TCP_CONNECTIONS=${TCP_CONN}"
echo "TCP_TIME_WAIT=${TCP_TIME_WAIT}"
df -P -k -x tmpfs -x devtmpfs -x squashfs 2>/dev/null | awk 'NR>1 {
  pct=$5; gsub("%","",pct);
  printf "DISK_USAGE=%s|%s|%s|%s|%s\n", $6, $2, $3, $4, pct
}'
"""


def _is_ssh_timeout(e: Exception) -> bool:
    name = type(e).__name__
    return isinstance(e, (TimeoutError, asyncio.TimeoutError)) or name == "TimeoutError"


def _ssh_error_msg(e: Exception, host: dict | None = None) -> str:
    """把 asyncssh / asyncio 异常转为对用户友好的中文提示。"""
    import asyncssh as _assh
    name = type(e).__name__
    msg  = str(e).strip()
    if _is_ssh_timeout(e):
        target = ""
        if host:
            target = f"（{host.get('ip') or '-'}:{host.get('ssh_port') or 22}）"
        return (
            f"SSH 连接超时{target}，请检查主机 IP 是否可达、SSH 端口是否开放；"
            f"当前连接超时 {_HOST_SYNC_SSH_CONNECT_TIMEOUT:g}s，可通过 HOST_SYNC_SSH_CONNECT_TIMEOUT 调整"
        )
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


def _to_int(value: str) -> int | None:
    try:
        return int(float(value.strip()))
    except Exception:
        return None


def _to_float(value: str) -> float | None:
    try:
        return round(float(value.strip()), 1)
    except Exception:
        return None


def _format_uptime(seconds: int | None) -> str:
    if seconds is None or seconds < 0:
        return ""
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}天")
    if hours or days:
        parts.append(f"{hours}小时")
    parts.append(f"{minutes}分钟")
    return "".join(parts)


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
            port = int(cred.get("port") or port)
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
        known_hosts=None, connect_timeout=_HOST_SYNC_SSH_CONNECT_TIMEOUT,
    )

    async with asyncssh.connect(**connect_kwargs) as conn:
        result = await conn.run(_SYNC_SCRIPT_SHELL, timeout=_HOST_SYNC_SSH_COMMAND_TIMEOUT)
        output = result.stdout or ""

    info: dict = {}
    disk_usage: list[dict] = []
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("OS_VER="):
            v = line[7:].strip()
            if v:
                info["os_version"] = v
        elif line.startswith("CPU_CORES="):
            value = _to_int(line[10:])
            if value is not None:
                info["cpu_cores"] = value
        elif line.startswith("MEM_KB="):
            kb = _to_int(line[7:])
            if kb is not None:
                info["memory_gb"] = round(kb / 1024 / 1024, 1) if kb > 0 else None
        elif line.startswith("DISK_KB="):
            kb = _to_int(line[8:])
            if kb is not None:
                info["disk_gb"] = round(kb / 1024 / 1024, 1) if kb > 0 else None
        elif line.startswith("HOSTNAME="):
            v = line[9:].strip()
            if v:
                info["hostname"] = v
        elif line.startswith("CPU_USAGE_PCT="):
            value = _to_float(line[14:])
            if value is not None:
                info["cpu_usage_pct"] = value
        elif line.startswith("MEM_USAGE_PCT="):
            value = _to_float(line[14:])
            if value is not None:
                info["memory_usage_pct"] = value
        elif line.startswith("LOAD5="):
            value = _to_float(line[6:])
            if value is not None:
                info["load5"] = value
        elif line.startswith("UPTIME_SECONDS="):
            value = _to_int(line[15:])
            if value is not None:
                info["uptime_seconds"] = value
                info["uptime_text"] = _format_uptime(value)
        elif line.startswith("DISK_IO_READ_BPS="):
            value = _to_int(line[17:])
            if value is not None:
                info["disk_io_read_bps"] = value
        elif line.startswith("DISK_IO_WRITE_BPS="):
            value = _to_int(line[18:])
            if value is not None:
                info["disk_io_write_bps"] = value
        elif line.startswith("NETWORK_RX_BPS="):
            value = _to_int(line[15:])
            if value is not None:
                info["network_rx_bps"] = value
        elif line.startswith("NETWORK_TX_BPS="):
            value = _to_int(line[15:])
            if value is not None:
                info["network_tx_bps"] = value
        elif line.startswith("TCP_CONNECTIONS="):
            value = _to_int(line[16:])
            if value is not None:
                info["tcp_connections"] = value
        elif line.startswith("TCP_TIME_WAIT="):
            value = _to_int(line[14:])
            if value is not None:
                info["tcp_time_wait"] = value
        elif line.startswith("DISK_USAGE="):
            parts = line[11:].split("|")
            if len(parts) == 5:
                mount, size_kb_raw, used_kb_raw, avail_kb_raw, pct_raw = parts
                size_kb = _to_int(size_kb_raw)
                used_kb = _to_int(used_kb_raw)
                avail_kb = _to_int(avail_kb_raw)
                pct = _to_float(pct_raw)
                if mount and size_kb is not None and used_kb is not None:
                    disk_usage.append({
                        "mount": mount,
                        "size_gb": round(size_kb / 1024 / 1024, 1),
                        "used_gb": round(used_kb / 1024 / 1024, 1),
                        "avail_gb": round((avail_kb or 0) / 1024 / 1024, 1),
                        "used_pct": pct,
                    })

    if disk_usage:
        info["disk_usage"] = disk_usage
    if any(k in info for k in (
        "cpu_usage_pct", "memory_usage_pct", "load5", "disk_usage",
        "disk_io_read_bps", "network_rx_bps", "tcp_connections", "uptime_seconds",
    )):
        info["metrics_updated_at"] = _NOW()

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
        detail = _ssh_error_msg(e, host)
        logger.warning(
            "[sync] 主机 %s (%s:%s) 同步失败: %s; raw=%r",
            host.get("hostname"),
            host.get("ip"),
            host.get("ssh_port") or 22,
            detail,
            e,
        )
        raise HTTPException(status_code=408 if _is_ssh_timeout(e) else 400, detail=detail)

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
    result["ssh_saved"] = bool(result.pop("ssh_password", "")) or bool(result.get("credential_id"))
    return {"ok": True, "updated": info, "host": result}


@router.post("/api/hosts/sync-all")
async def sync_all_hosts(user: User = Depends(current_user)):
    """一键同步（非管理员只同步自己分组的主机）。"""
    async def generate():
        all_hosts = load_hosts_list()
        visible   = _filter_hosts_by_user(all_hosts, user)
        hosts     = all_hosts  # 写回时用全量
        targets   = [h for h in visible if h.get("ssh_password") or h.get("credential_id")]
        total = len(targets)

        if total == 0:
            yield f"data: {json.dumps({'type':'done','success':0,'fail':0,'total':0,'message':'没有配置 SSH 凭证的主机'}, ensure_ascii=False)}\n\n"
            return

        yield f"data: {json.dumps({'type':'start','total':total}, ensure_ascii=False)}\n\n"

        sem = asyncio.Semaphore(5)

        async def _do_sync(host: dict) -> dict:
            async with sem:
                try:
                    info = await _ssh_sync(host)
                    return {
                        "ok": True,
                        "id": host["id"],
                        "hostname": host.get("hostname", ""),
                        "ip": host.get("ip", ""),
                        "info": info,
                    }
                except Exception as e:
                    return {
                        "ok": False,
                        "id": host["id"],
                        "hostname": host.get("hostname", ""),
                        "ip": host.get("ip", ""),
                        "error": _ssh_error_msg(e, host),
                    }

        # 全部并发执行，等待所有结果
        results = await asyncio.gather(*[_do_sync(h) for h in targets], return_exceptions=True)

        id_to_host = {h["id"]: h for h in hosts}
        success = fail = 0

        for res in results:
            if isinstance(res, Exception):
                fail += 1
                yield f"data: {json.dumps({'type':'progress','ok':False,'error':str(res),'success':success,'fail':fail,'total':total}, ensure_ascii=False)}\n\n"
                continue

            host_id = res["id"]
            h = id_to_host.get(host_id)

            if res["ok"] and h:
                for k, v in res["info"].items():
                    if v is not None:
                        h[k] = v
                h["updated_at"] = _NOW()
                success += 1
                yield f"data: {json.dumps({'type':'progress','id':host_id,'hostname':res['hostname'],'ip':res['ip'],'ok':True,'updated':res['info'],'success':success,'fail':fail,'total':total}, ensure_ascii=False)}\n\n"
            else:
                fail += 1
                yield f"data: {json.dumps({'type':'progress','id':host_id,'hostname':res['hostname'],'ip':res['ip'],'ok':False,'error':res.get('error',''),'success':success,'fail':fail,'total':total}, ensure_ascii=False)}\n\n"

        # 所有主机处理完后统一保存
        save_hosts_list(hosts)

        msg = f"同步完成：成功 {success} 台，失败 {fail} 台"
        yield f"data: {json.dumps({'type':'done','success':success,'fail':fail,'total':total,'message':msg}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── 进程列表 ─────────────────────────────────────────────────────────────────

# 服务特征规则：(匹配关键字列表, 显示名, 颜色代号)
_SERVICE_RULES: list[tuple[list[str], str, str]] = [
    (["mysqld", "mysql"],              "MySQL",         "mysql"),
    (["java"],                         "Java",          "java"),
    (["python", "python3", "python2"], "Python",        "python"),
    (["node", "nodejs"],               "Node.js",       "node"),
    (["nginx"],                        "Nginx",         "nginx"),
    (["redis-server", "redis"],        "Redis",         "redis"),
    (["postgres", "postgresql"],       "PostgreSQL",    "postgres"),
    (["elasticsearch", "kibana"],      "Elastic",       "elastic"),
    (["docker", "containerd"],         "Docker",        "docker"),
    (["kubelet", "kube-proxy", "etcd"],"Kubernetes",    "k8s"),
    (["mongod", "mongo"],              "MongoDB",       "mongo"),
    (["rabbitmq"],                     "RabbitMQ",      "rabbit"),
    (["kafka", "zookeeper"],           "Kafka/ZK",      "kafka"),
    (["sshd"],                         "SSH",           "ssh"),
    (["php", "php-fpm"],               "PHP",           "php"),
    (["go"],                           "Go",            "go"),
]

_PROC_CMD = r"""
ps -eo pid,ppid,user,%cpu,%mem,rss,stat,comm,args --sort=-%cpu --no-headers 2>/dev/null | head -30 | awk '{
  pid=$1; ppid=$2; user=$3; cpu=$4; mem=$5; rss=$6; stat=$7; comm=$8;
  args="";
  for(i=9;i<=NF;i++) args=args" "$i;
  sub(/^ /,"",args);
  printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n", pid,ppid,user,cpu,mem,rss,stat,comm,args
}'
"""


def _classify_process(comm: str, args: str) -> tuple[str, str] | None:
    """返回 (service_name, color_key) 或 None。"""
    target = (comm + " " + args).lower()
    for keywords, name, color in _SERVICE_RULES:
        if any(kw in target for kw in keywords):
            return name, color
    return None


def _parse_processes(raw: str) -> list[dict]:
    """解析 ps 输出为进程列表，附加服务分类信息。"""
    procs: list[dict] = []
    for line in raw.strip().splitlines():
        parts = line.split("\t", 8)
        if len(parts) < 8:
            continue
        pid, ppid, user, cpu, mem, rss, stat, comm = parts[:8]
        args = parts[8] if len(parts) > 8 else comm
        try:
            cpu_f = float(cpu)
            mem_f = float(mem)
            rss_mb = round(int(rss) / 1024, 1)
        except (ValueError, TypeError):
            continue

        svc = _classify_process(comm, args)
        # 截断过长的命令行
        display_args = args[:120] + "…" if len(args) > 120 else args

        procs.append({
            "pid":      int(pid) if pid.isdigit() else 0,
            "user":     user,
            "cpu":      cpu_f,
            "mem":      mem_f,
            "rss_mb":   rss_mb,
            "stat":     stat,
            "comm":     comm,
            "args":     display_args,
            "service":  svc[0] if svc else None,
            "color":    svc[1] if svc else None,
        })
    return procs


def _prioritize(procs: list[dict]) -> list[dict]:
    """服务进程置顶，同层内按 CPU 排序，最多返回 15 条。"""
    service = [p for p in procs if p["service"]]
    others  = [p for p in procs if not p["service"]]
    # 服务进程按 CPU 降序，但去掉空闲的 kthreadd/idle 等
    service.sort(key=lambda p: -p["cpu"])
    others.sort(key=lambda p: -p["cpu"])
    combined = service + others
    return combined[:15]


_JAVA_DIAG_DIR = REPORTS_DIR / "java_diagnostics"
_JAVA_DIAG_DIR.mkdir(exist_ok=True)

_ARTHAS_PRESETS = {
    "dashboard": "dashboard -n 1",
    "jvm": "jvm",
    "thread_top": "thread -n 5",
    "thread_blocked": "thread -b",
    "memory": "memory",
}

_JAVA_FLAME_EVENTS = {"cpu", "alloc", "lock", "wall"}


class JavaArthasRequest(BaseModel):
    pid: int
    preset: str = "dashboard"
    command: str = ""


class JavaFlamegraphRequest(BaseModel):
    pid: int
    seconds: int = 30
    event: str = "cpu"


def _get_host_or_404(host_id: str) -> dict:
    host = next((h for h in load_hosts_list() if h.get("id") == host_id), None)
    if not host:
        raise HTTPException(status_code=404, detail="主机不存在")
    return host


def _resolve_host_ssh_auth(host: dict) -> tuple[str, str, int, str]:
    ip = str(host.get("ip") or "").strip()
    port = int(host.get("ssh_port") or 22)
    username = str(host.get("ssh_user") or "root").strip() or "root"
    password = None

    cred_id = host.get("credential_id", "")
    if cred_id:
        creds = load_credentials()
        cred = next((c for c in creds if c.get("id") == cred_id), None)
        if cred:
            username = str(cred.get("username") or username).strip() or username
            raw_pw = cred.get("password", "")
            if raw_pw:
                try:
                    password = decrypt_password(raw_pw)
                except Exception:
                    password = raw_pw

    if not password:
        enc_pw = host.get("ssh_password", "")
        if enc_pw:
            try:
                password = decrypt_password(enc_pw)
            except Exception:
                password = None

    if not ip:
        raise HTTPException(status_code=400, detail="主机没有配置 IP")
    if not password:
        raise HTTPException(status_code=400, detail="主机未配置 SSH 密码，无法执行诊断")
    return ip, username, port, password


def _java_artifact_url(filename: str) -> str:
    return f"/api/hosts/java-diagnostics/artifacts/{quote(filename)}"


def _save_java_artifact(filename: str, content: str, encoding: str = "utf-8") -> Path:
    path = _JAVA_DIAG_DIR / filename
    path.write_text(content, encoding=encoding)
    return path


async def _ssh_run(host: dict, command: str, timeout: float):
    import asyncssh

    ip, username, port, password = _resolve_host_ssh_auth(host)
    return await asyncssh.connect(
        host=ip,
        port=port,
        username=username,
        password=password,
        known_hosts=None,
        connect_timeout=_HOST_SYNC_SSH_CONNECT_TIMEOUT,
    )


def _build_arthas_command(pid: int, arthas_command: str) -> str:
    return f"""set -e
WORKDIR=/tmp/aiops-java-tools
BOOT="$WORKDIR/arthas-boot.jar"
mkdir -p "$WORKDIR"

# 自动探测 java 路径（不依赖 PATH）
_find_java() {{
  # 1. PATH 里直接找
  if command -v java >/dev/null 2>&1; then echo "java"; return; fi
  # 2. 从目标 JVM 进程的符号链接找
  local exe
  exe=$(readlink -f /proc/{pid}/exe 2>/dev/null)
  if [ -n "$exe" ] && [ -x "$exe" ]; then echo "$exe"; return; fi
  # 3. 从进程 JAVA_HOME 环境变量找
  local jhome
  jhome=$(cat /proc/{pid}/environ 2>/dev/null | tr '\\0' '\\n' | grep '^JAVA_HOME=' | cut -d= -f2)
  if [ -n "$jhome" ] && [ -x "$jhome/bin/java" ]; then echo "$jhome/bin/java"; return; fi
  # 4. 常见安装路径
  for p in /usr/local/java/bin/java /usr/lib/jvm/*/bin/java /opt/jdk*/bin/java /opt/java/*/bin/java; do
    [ -x "$p" ] && {{ echo "$p"; return; }}
  done
  echo ""
}}
JAVA=$(_find_java)
if [ -z "$JAVA" ]; then
  echo "未找到 java 命令，请确认 JDK 已安装或 /proc/{pid} 进程存在" >&2
  exit 2
fi
echo "使用 Java: $JAVA"

if [ ! -s "$BOOT" ]; then
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL -o "$BOOT" https://arthas.aliyun.com/arthas-boot.jar
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$BOOT" https://arthas.aliyun.com/arthas-boot.jar
  else
    echo "缺少 curl/wget，无法下载 Arthas" >&2
    exit 2
  fi
fi
"$JAVA" -jar "$BOOT" {pid} --action exec --command {shlex.quote(arthas_command)} 2>&1
"""


def _build_async_profiler_command(pid: int, seconds: int, event: str, remote_output: str) -> str:
    return f"""set -e
WORKDIR=/tmp/aiops-java-tools
PROFILE_HOME="$WORKDIR/async-profiler"
ARCH="$(uname -m)"
mkdir -p "$WORKDIR"

_find_java() {{
  if command -v java >/dev/null 2>&1; then echo "java"; return; fi
  local exe; exe=$(readlink -f /proc/{pid}/exe 2>/dev/null)
  if [ -n "$exe" ] && [ -x "$exe" ]; then echo "$exe"; return; fi
  local jhome; jhome=$(cat /proc/{pid}/environ 2>/dev/null | tr '\\0' '\\n' | grep '^JAVA_HOME=' | cut -d= -f2)
  if [ -n "$jhome" ] && [ -x "$jhome/bin/java" ]; then echo "$jhome/bin/java"; return; fi
  for p in /usr/local/java/bin/java /usr/lib/jvm/*/bin/java /opt/jdk*/bin/java /opt/java/*/bin/java; do
    [ -x "$p" ] && {{ echo "$p"; return; }}
  done
  echo ""
}}
JAVA=$(_find_java)
if [ -z "$JAVA" ]; then
  echo "未找到 java 命令，请确认 JDK 已安装" >&2
  exit 2
fi
case "$ARCH" in
  x86_64|amd64) PKG="linux-x64" ;;
  aarch64|arm64) PKG="linux-arm64" ;;
  *)
    echo "不支持的架构: $ARCH" >&2
    exit 2
    ;;
esac
if [ ! -x "$PROFILE_HOME/profiler.sh" ]; then
  cd "$WORKDIR"
  rm -rf "$PROFILE_HOME" async-profiler async-profiler-*.tar.gz async-profiler-*
  URL="https://github.com/async-profiler/async-profiler/releases/download/v3.0/async-profiler-3.0-$PKG.tar.gz"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$URL" -o async-profiler.tar.gz
  elif command -v wget >/dev/null 2>&1; then
    wget -qO async-profiler.tar.gz "$URL"
  else
    echo "缺少 curl/wget，无法下载 async-profiler" >&2
    exit 2
  fi
  tar -xzf async-profiler.tar.gz
  SRC_DIR="$(find "$WORKDIR" -maxdepth 1 -type d -name 'async-profiler-*' | head -1)"
  if [ -z "$SRC_DIR" ]; then
    echo "async-profiler 解压失败" >&2
    exit 2
  fi
  mv "$SRC_DIR" "$PROFILE_HOME"
fi
"$PROFILE_HOME/profiler.sh" -d {seconds} -e {event} -f {shlex.quote(remote_output)} {pid}
"""


@router.get("/api/hosts/{host_id}/processes")
async def get_host_processes(host_id: str):
    """通过 SSH 获取主机 Top 进程列表（服务进程置顶）。"""
    host = _get_host_or_404(host_id)

    try:
        async with await _ssh_run(host, _PROC_CMD, timeout=10) as conn:
            result = await conn.run(_PROC_CMD, timeout=10)
            raw = result.stdout or ""
    except Exception as e:
        raise HTTPException(status_code=400, detail=_ssh_error_msg(e, host))

    procs = _parse_processes(raw)
    procs = _prioritize(procs)

    # 统计检测到的服务
    detected = sorted({p["service"] for p in procs if p["service"]})
    return {"data": procs, "detected_services": detected, "total": len(procs)}


@router.post("/api/hosts/{host_id}/java-diagnostics/arthas")
async def run_java_arthas(host_id: str, body: JavaArthasRequest):
    host = _get_host_or_404(host_id)
    pid = int(body.pid or 0)
    if pid <= 0:
        raise HTTPException(status_code=400, detail="PID 必须大于 0")

    preset = (body.preset or "dashboard").strip()
    if preset == "custom":
        arthas_command = (body.command or "").strip()
        if not arthas_command:
            raise HTTPException(status_code=400, detail="自定义 Arthas 命令不能为空")
    else:
        arthas_command = _ARTHAS_PRESETS.get(preset)
        if not arthas_command:
            raise HTTPException(status_code=400, detail="不支持的 Arthas 预设")

    command = _build_arthas_command(pid, arthas_command)
    try:
        async with await _ssh_run(host, command, timeout=90) as conn:
            result = await conn.run(command, timeout=90, check=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail=_ssh_error_msg(e, host))

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if result.exit_status != 0:
        detail = stderr or stdout or "Arthas 执行失败"
        raise HTTPException(status_code=400, detail=detail)

    artifact_name = f"arthas_{host_id}_{pid}_{uuid.uuid4().hex[:8]}.txt"
    preview = stdout or stderr or "(无输出)"
    _save_java_artifact(artifact_name, preview)
    return {
        "ok": True,
        "tool": "arthas",
        "pid": pid,
        "preset": preset,
        "command": arthas_command,
        "stdout": stdout,
        "stderr": stderr,
        "download_url": _java_artifact_url(artifact_name),
    }


@router.post("/api/hosts/{host_id}/java-diagnostics/flamegraph")
async def run_java_flamegraph(host_id: str, body: JavaFlamegraphRequest):
    host = _get_host_or_404(host_id)
    pid = int(body.pid or 0)
    seconds = int(body.seconds or 0)
    event = (body.event or "cpu").strip().lower()

    if pid <= 0:
        raise HTTPException(status_code=400, detail="PID 必须大于 0")
    if seconds < 10 or seconds > 300:
        raise HTTPException(status_code=400, detail="采样时长必须在 10 到 300 秒之间")
    if event not in _JAVA_FLAME_EVENTS:
        raise HTTPException(status_code=400, detail="不支持的火焰图事件类型")

    artifact_name = f"flamegraph_{host_id}_{pid}_{event}_{uuid.uuid4().hex[:8]}.html"
    remote_output = f"/tmp/aiops-java-tools/{artifact_name}"
    command = _build_async_profiler_command(pid, seconds, event, remote_output)

    try:
        async with await _ssh_run(host, command, timeout=seconds + 120) as conn:
            result = await conn.run(command, timeout=seconds + 120, check=False)
            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            if result.exit_status != 0:
                detail = stderr or stdout or "火焰图生成失败"
                raise HTTPException(status_code=400, detail=detail)

            async with conn.start_sftp_client() as sftp:
                local_path = _JAVA_DIAG_DIR / artifact_name
                await sftp.get(remote_output, str(local_path))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=_ssh_error_msg(e, host))

    size_bytes = (_JAVA_DIAG_DIR / artifact_name).stat().st_size
    return {
        "ok": True,
        "tool": "flamegraph",
        "pid": pid,
        "seconds": seconds,
        "event": event,
        "size_bytes": size_bytes,
        "download_url": _java_artifact_url(artifact_name),
        "stdout": stdout,
    }


@router.get("/api/hosts/java-diagnostics/artifacts/{filename}")
async def download_java_diag_artifact(filename: str):
    safe_name = Path(filename).name
    if safe_name != filename:
        raise HTTPException(status_code=400, detail="非法文件名")

    path = _JAVA_DIAG_DIR / safe_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="诊断结果不存在")

    suffix = path.suffix.lower()
    media_type = {
        ".html": "text/html; charset=utf-8",
        ".txt": "text/plain; charset=utf-8",
        ".svg": "image/svg+xml",
    }.get(suffix, "application/octet-stream")
    encoded = quote(path.name)
    disposition = "inline" if suffix in {".html", ".svg"} else "attachment"
    return Response(
        content=path.read_bytes(),
        media_type=media_type,
        headers={"Content-Disposition": f"{disposition}; filename*=UTF-8''{encoded}"},
    )


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


def _cmdb_instances_for_group(group_id: str) -> tuple[list[str], str]:
    """根据分组 ID 从 CMDB 获取 Prometheus 实例列表（ip:9100），返回 (instances, group_name)。"""
    hosts = load_hosts_list()
    groups = load_groups()
    g = next((g for g in groups if g["id"] == group_id), None)
    group_name = g["name"] if g else group_id
    instances = [f"{h['ip']}:9100" for h in hosts if h.get("group") == group_id and h.get("ip")]
    return instances, group_name


@router.get("/api/hosts/inspect")
async def inspect_all_hosts(group_id: Optional[str] = Query(None)):
    """巡检主机 — 以 CMDB 为基准，有 Prometheus 指标的正常巡检，无指标的标记为离线。"""
    async def generate():
        try:
            group_name: str = ""
            all_hosts  = load_hosts_list()

            # 确定本次巡检的目标主机列表
            if group_id:
                groups_list = load_groups()
                g = next((g for g in groups_list if g["id"] == group_id), None)
                group_name = g["name"] if g else group_id
                target_hosts = [h for h in all_hosts if h.get("group") == group_id and h.get("ip")]
                if not target_hosts:
                    yield f"data: {json.dumps({'type': 'error', 'message': f'分组「{group_name}」下没有主机'}, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"
                    return
            else:
                target_hosts = [h for h in all_hosts if h.get("ip")]
                if not target_hosts:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'CMDB 中没有主机，请先录入主机'}, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"
                    return

            # 从 Prometheus 获取全量指标（不按 instance 过滤，因为 node-exporter 的 instance 是主机名而非 ip:port）
            try:
                prom_results = await prom.inspect_hosts(instances=None)
            except Exception:
                prom_results = []

            # 建立 ip → prom_result 映射（通过 Prometheus 返回的 ip 字段匹配）
            prom_map: dict[str, dict] = {}
            for r in prom_results:
                ip = r.get("ip", "")
                if ip:
                    prom_map[ip] = r

            # 合并：CMDB 主机为基准
            results = []
            for h in target_hosts:
                ip = h["ip"]
                if ip in prom_map:
                    # 有 Prometheus 数据：使用巡检结果，补全 CMDB 信息
                    r = dict(prom_map[ip])
                    r["hostname"] = h.get("hostname") or r.get("hostname") or ip
                    r["group"]    = h.get("group", "")
                    r["env"]      = h.get("env", "")
                    results.append(r)
                else:
                    # 无 Prometheus 数据：以"无数据"状态显示，确保主机出现在报告中
                    results.append({
                        "instance": f"{ip}:9100",
                        "ip":       ip,
                        "hostname": h.get("hostname") or ip,
                        "os":       h.get("os_version", ""),
                        "job":      "",
                        "state":    "offline",
                        "group":    h.get("group", ""),
                        "env":      h.get("env", ""),
                        "overall":  "warning",
                        "checks": [{
                            "item":      "Prometheus 数据",
                            "value":     "无指标",
                            "status":    "warning",
                            "threshold": "需要安装 node_exporter 或检查 Prometheus 配置",
                        }],
                        "metrics":    {},
                        "partitions": [],
                    })

            # 严重 → 警告 → 正常排序
            sev = {"critical": 2, "warning": 1, "normal": 0}
            results.sort(key=lambda x: -sev.get(x["overall"], 0))

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
