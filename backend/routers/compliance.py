"""服务器安全基线合规检查（参考 itops-agent-platform servers/compliance）。

在现有 CMDB + SSH 基础上，对主机跑一组等保/CIS 风格的只读基线检查项，
逐项判定 pass/warn/fail，给出总分与失败清单，并存历史。

路由前缀：/api/compliance/*
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException, Depends

from json_snapshot_store import read_json_file, write_json_file
from auth.deps import current_user
from auth.models import User

logger = logging.getLogger(__name__)
router = APIRouter()

_HISTORY_FILE = Path(__file__).resolve().parent.parent / "data" / "compliance_history.json"


# ── 判定辅助 ─────────────────────────────────────────────────────────
def _j(status: str, actual: str, reason: str) -> dict:
    return {"status": status, "actual": actual[:200], "reason": reason}


# 每个检查项：id / 名称 / 分类 / 严重度 / SSH 命令 / 判定函数(stdout)->dict
# 判定只读，命令全部无副作用。
CHECKS: list[dict] = [
    {
        "id": "ssh_root_login", "name": "SSH 禁止 root 直接登录", "category": "访问控制", "severity": "high",
        "cmd": "grep -Ei '^\\s*PermitRootLogin' /etc/ssh/sshd_config 2>/dev/null | tail -1 || echo MISSING",
        "judge": lambda o: _j("pass", o, "已禁用 root 登录") if "no" in o.lower()
                 else _j("fail", o, "应设置 PermitRootLogin no"),
    },
    {
        "id": "ssh_empty_pass", "name": "SSH 禁止空密码登录", "category": "访问控制", "severity": "high",
        "cmd": "grep -Ei '^\\s*PermitEmptyPasswords' /etc/ssh/sshd_config 2>/dev/null | tail -1 || echo DEFAULT",
        "judge": lambda o: _j("pass", o, "已禁止空密码") if ("no" in o.lower() or "DEFAULT" in o)
                 else _j("fail", o, "应设置 PermitEmptyPasswords no"),
    },
    {
        "id": "empty_pass_account", "name": "无空密码账户", "category": "账户安全", "severity": "high",
        "cmd": "awk -F: '($2==\"\"){print $1}' /etc/shadow 2>/dev/null | tr '\\n' ' '; echo END",
        "judge": lambda o: _j("pass", o, "无空密码账户") if o.strip() in ("END", "")
                 else _j("fail", o, f"存在空密码账户: {o.replace('END','').strip()}"),
    },
    {
        "id": "pass_max_days", "name": "密码最长有效期 ≤ 90 天", "category": "账户安全", "severity": "medium",
        "cmd": "grep -E '^PASS_MAX_DAYS' /etc/login.defs 2>/dev/null | awk '{print $2}' || echo NONE",
        "judge": lambda o: (
            _j("pass", o, "密码有效期合规") if o.strip().isdigit() and int(o.strip()) <= 90
            else _j("warn", o, "建议 PASS_MAX_DAYS ≤ 90") if o.strip().isdigit()
            else _j("warn", o, "未配置密码有效期")
        ),
    },
    {
        "id": "passwd_perm", "name": "/etc/passwd 权限 644", "category": "文件权限", "severity": "medium",
        "cmd": "stat -c '%a' /etc/passwd 2>/dev/null || echo NA",
        "judge": lambda o: _j("pass", o, "权限合规") if o.strip() in ("644", "600")
                 else _j("fail", o, "应为 644"),
    },
    {
        "id": "shadow_perm", "name": "/etc/shadow 权限 ≤ 640", "category": "文件权限", "severity": "high",
        "cmd": "stat -c '%a' /etc/shadow 2>/dev/null || echo NA",
        "judge": lambda o: _j("pass", o, "权限合规") if o.strip() in ("000", "400", "600", "640")
                 else _j("fail", o, "应为 000/400/600/640"),
    },
    {
        "id": "firewall", "name": "防火墙已启用", "category": "网络安全", "severity": "medium",
        "cmd": "systemctl is-active firewalld 2>/dev/null || ufw status 2>/dev/null | head -1 || echo none",
        "judge": lambda o: _j("pass", o, "防火墙运行中") if ("active" in o.lower() and "inactive" not in o.lower())
                 else _j("warn", o, "未检测到运行中的防火墙"),
    },
    {
        "id": "time_sync", "name": "时间同步服务运行", "category": "系统配置", "severity": "low",
        "cmd": "systemctl is-active chronyd 2>/dev/null || systemctl is-active ntpd 2>/dev/null || systemctl is-active systemd-timesyncd 2>/dev/null || echo none",
        "judge": lambda o: _j("pass", o, "时间同步正常") if "active" in o.lower() and "inactive" not in o.lower()
                 else _j("warn", o, "未启用时间同步"),
    },
    {
        "id": "auditd", "name": "审计服务 auditd 运行", "category": "审计日志", "severity": "medium",
        "cmd": "systemctl is-active auditd 2>/dev/null || echo none",
        "judge": lambda o: _j("pass", o, "审计已启用") if "active" in o.lower() and "inactive" not in o.lower()
                 else _j("warn", o, "建议启用 auditd"),
    },
    {
        "id": "rsyslog", "name": "系统日志服务运行", "category": "审计日志", "severity": "low",
        "cmd": "systemctl is-active rsyslog 2>/dev/null || systemctl is-active syslog 2>/dev/null || echo none",
        "judge": lambda o: _j("pass", o, "日志服务运行中") if "active" in o.lower() and "inactive" not in o.lower()
                 else _j("warn", o, "未检测到日志服务"),
    },
]

_SEV_WEIGHT = {"high": 3, "medium": 2, "low": 1}


def _find_host(host_id: str) -> dict:
    from state import load_hosts_list
    for h in load_hosts_list():
        if str(h.get("id")) == str(host_id) or h.get("ip") == host_id:
            return h
    raise HTTPException(status_code=404, detail=f"主机 {host_id} 不存在")


def _load_history() -> dict:
    data = read_json_file(_HISTORY_FILE, default={})
    return data if isinstance(data, dict) else {}


def _save_history(data: dict) -> None:
    write_json_file(_HISTORY_FILE, data, ensure_parent=True)


@router.get("/api/compliance/checks")
async def list_checks(_: User = Depends(current_user)):
    """列出所有基线检查项定义（不执行）。"""
    return {
        "checks": [
            {"id": c["id"], "name": c["name"], "category": c["category"], "severity": c["severity"]}
            for c in CHECKS
        ],
        "total": len(CHECKS),
    }


@router.post("/api/compliance/hosts/{host_id}/run")
async def run_compliance(host_id: str, _: User = Depends(current_user)):
    """对指定主机跑全部基线检查，返回逐项结果 + 评分，并记入历史。"""
    host = _find_host(host_id)
    from routers.hosts import _ssh_run

    results: list[dict] = []
    try:
        async with await _ssh_run(host, "", timeout=30) as conn:
            for c in CHECKS:
                try:
                    r = await conn.run(c["cmd"], check=False, timeout=15)
                    out = (r.stdout or "") + (r.stderr or "")
                    verdict = c["judge"](out.strip())
                except Exception as exc:
                    verdict = _j("error", str(exc), "检查执行失败")
                results.append({
                    "id": c["id"], "name": c["name"], "category": c["category"],
                    "severity": c["severity"], **verdict,
                })
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SSH 连接失败：{exc}")

    # 评分：加权通过率（error 记为 fail）
    total_w = sum(_SEV_WEIGHT.get(r["severity"], 1) for r in results)
    pass_w = sum(_SEV_WEIGHT.get(r["severity"], 1) for r in results if r["status"] == "pass")
    score = round(pass_w / total_w * 100) if total_w else 0
    summary = {
        "pass": sum(1 for r in results if r["status"] == "pass"),
        "warn": sum(1 for r in results if r["status"] == "warn"),
        "fail": sum(1 for r in results if r["status"] in ("fail", "error")),
        "total": len(results),
    }
    record = {
        "host_id": str(host.get("id") or host_id),
        "hostname": host.get("hostname") or host.get("ip", ""),
        "ip": host.get("ip", ""),
        "score": score,
        "summary": summary,
        "results": results,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    # 存历史（每主机保留最近 20 次）
    hist = _load_history()
    key = str(host.get("id") or host_id)
    hist.setdefault(key, []).insert(0, {k: record[k] for k in ("score", "summary", "checked_at")})
    hist[key] = hist[key][:20]
    _save_history(hist)

    return record


@router.get("/api/compliance/hosts/{host_id}/history")
async def compliance_history(host_id: str, _: User = Depends(current_user)):
    """某主机的合规评分历史（最近 20 次）。"""
    host = _find_host(host_id)
    key = str(host.get("id") or host_id)
    return {"host_id": key, "history": _load_history().get(key, [])}
