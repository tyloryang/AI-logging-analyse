"""共享状态：单例实例、配置常量和辅助函数。

注意：本模块在 import 时即读取 os.getenv()，
因此调用方必须在 import 本模块之前先调用 load_dotenv()。
"""
import json
import logging
import os
import uuid
from pathlib import Path

from cryptography.fernet import Fernet

from loki_client import LokiClient
from ai_analyzer import AIAnalyzer
from log_clusterer import LogClusterer
from prom_client import PrometheusClient

logger = logging.getLogger(__name__)

# ── 配置常量（settings.json 优先级高于 .env）────────────────────────────────

SETTINGS_FILE = Path("./data/settings.json")


def _load_settings() -> dict:
    """从 data/settings.json 读取运行时配置覆盖"""
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _cfg(s: dict, key: str, env_key: str, default: str = "") -> str:
    return s.get(key) or os.getenv(env_key, default)


_s = _load_settings()

LOKI_URL            = _cfg(_s, "loki_url",             "LOKI_URL",             "http://localhost:3100")
LOKI_USERNAME       = _cfg(_s, "loki_username",         "LOKI_USERNAME",        "")
LOKI_PASSWORD       = _cfg(_s, "loki_password",         "LOKI_PASSWORD",        "")
PROMETHEUS_URL      = _cfg(_s, "prometheus_url",        "PROMETHEUS_URL",       "http://localhost:9090")
PROMETHEUS_USERNAME = _cfg(_s, "prometheus_username",   "PROMETHEUS_USERNAME",  "")
PROMETHEUS_PASSWORD = _cfg(_s, "prometheus_password",   "PROMETHEUS_PASSWORD",  "")

REPORTS_DIR      = Path(os.getenv("REPORTS_DIR", "./reports"))
REPORTS_DIR.mkdir(exist_ok=True)
CMDB_FILE        = Path(os.getenv("CMDB_FILE", "./cmdb_hosts.json"))
CREDENTIALS_FILE = Path(os.getenv("CREDENTIALS_FILE", "./ssh_credentials.json"))

FEISHU_WEBHOOK   = os.getenv("FEISHU_WEBHOOK", "")
FEISHU_KEYWORD   = os.getenv("FEISHU_KEYWORD", "")
DINGTALK_WEBHOOK = os.getenv("DINGTALK_WEBHOOK", "")
DINGTALK_KEYWORD = os.getenv("DINGTALK_KEYWORD", "")
APP_URL          = os.getenv("APP_URL", "").rstrip("/")

SCHEDULE_CRON          = os.getenv("SCHEDULE_CRON", "0 9 * * *")
REPORT_RETENTION_DAYS  = int(os.getenv("REPORT_RETENTION_DAYS", "90"))  # 0 = 不清理
SCHEDULE_CHANNELS = [
    ch.strip() for ch in os.getenv("SCHEDULE_CHANNELS", "").split(",") if ch.strip()
]

# ── SSH 密钥（支持三种来源：env 直传 > 文件 > 自动生成）─────────────────────

_FERNET_KEY_ENV = os.getenv("SSH_FERNET_KEY", "").strip()  # Base64 Fernet key，容器部署推荐
_SSH_KEY_FILE   = Path(os.getenv("SSH_KEY_FILE", "./.ssh_key"))

if _FERNET_KEY_ENV:
    _FERNET_KEY = _FERNET_KEY_ENV.encode()
    logger.info("[启动] SSH 加密密钥来自 SSH_FERNET_KEY 环境变量")
elif _SSH_KEY_FILE.exists():
    _FERNET_KEY = _SSH_KEY_FILE.read_bytes().strip()
    logger.info("[启动] SSH 加密密钥来自文件: %s", _SSH_KEY_FILE)
else:
    _FERNET_KEY = Fernet.generate_key()
    _SSH_KEY_FILE.write_bytes(_FERNET_KEY)
    logger.warning(
        "[安全] SSH_FERNET_KEY 未配置，已自动生成密钥并写入 %s。"
        "容器重启若该文件丢失则已存密码无法解密，"
        "建议设置 SSH_FERNET_KEY 环境变量（值为 `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`）。",
        _SSH_KEY_FILE.resolve(),
    )

_fernet = Fernet(_FERNET_KEY)

# ── 单例客户端 ────────────────────────────────────────────────────────────────

loki      = LokiClient(LOKI_URL, LOKI_USERNAME, LOKI_PASSWORD)
logger.info("[启动] PROMETHEUS_URL=%s, auth=%s", PROMETHEUS_URL, "yes" if PROMETHEUS_USERNAME else "no")
prom      = PrometheusClient(PROMETHEUS_URL, PROMETHEUS_USERNAME, PROMETHEUS_PASSWORD)
analyzer  = AIAnalyzer()
clusterer = LogClusterer()

# ── CMDB / 凭证辅助函数 ───────────────────────────────────────────────────────

def load_hosts_list() -> list[dict]:
    """新格式：主机列表（手动录入，UUID 主键）。"""
    if CMDB_FILE.exists():
        try:
            data = json.loads(CMDB_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                # 确保每条记录都有 id
                changed = False
                for h in data:
                    if not h.get("id"):
                        h["id"] = str(uuid.uuid4())
                        changed = True
                if changed:
                    CMDB_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                return data
            # 兼容旧 dict 格式：自动迁移为列表并回写，确保 ID 稳定
            now = __import__("datetime").datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            # 用户主动录入的字段（与 Prometheus 自动发现区别）
            _user_fields = {"owner", "group", "role", "ssh_user", "ssh_password", "notes"}
            # 先处理"命名主机"（key 不含冒号且不是 undefined），再处理 ip:port 条目
            items = list(data.items())
            named   = [(k, v) for k, v in items if ":" not in k and k not in ("undefined",)]
            ported  = [(k, v) for k, v in items if ":" in k]
            ordered = named + ported
            result: list[dict] = []
            seen_ips: set[str] = set()
            for instance, meta in ordered:
                if instance == "undefined":
                    continue
                host = dict(meta)
                ip = host.get("ip") or instance.split(":")[0]
                if not ip or ip == "undefined":
                    continue
                # 跳过重复 IP（命名主机优先，port 条目排后，所以命名主机不会被覆盖）
                if ip in seen_ips:
                    continue
                # 过滤纯 Prometheus 发现节点（只有 ip 字段，无任何用户信息）
                has_user_info = any(host.get(f) for f in _user_fields)
                is_named = ":" not in instance
                if not has_user_info and not is_named:
                    continue
                seen_ips.add(ip)
                host["ip"] = ip
                host.setdefault("id", str(uuid.uuid4()))
                # 使用 key 作为 hostname（如果 key 是有意义的名字）
                if is_named and instance not in (ip, "undefined"):
                    host.setdefault("hostname", instance)
                else:
                    host.setdefault("hostname", ip)
                host.setdefault("platform", "Linux")
                host.setdefault("status", "active")
                host.setdefault("env", host.get("env") or "production")
                host.setdefault("created_at", now)
                host.setdefault("updated_at", now)
                result.append(host)
            # 回写 list 格式，ID 固定下来
            CMDB_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info("[CMDB] 旧格式自动迁移完成，共 %d 台主机", len(result))
            return result
        except Exception as exc:
            logger.warning("[CMDB] load_hosts_list 异常: %s", exc)
    return []


def save_hosts_list(hosts: list[dict]) -> None:
    CMDB_FILE.write_text(json.dumps(hosts, ensure_ascii=False, indent=2), encoding="utf-8")


def load_cmdb() -> dict:
    """向后兼容：返回以 ip 为键的 dict，供 SSH/慢日志/报告等模块使用。"""
    hosts = load_hosts_list()
    return {h["ip"]: h for h in hosts if h.get("ip")}


def save_cmdb(data: dict) -> None:
    """向后兼容写入（仅供旧代码路径使用，新代码请用 save_hosts_list）。"""
    hosts = load_hosts_list()
    host_map = {h["ip"]: h for h in hosts if h.get("ip")}
    for ip, meta in data.items():
        if ip in host_map:
            host_map[ip].update(meta)
        else:
            entry = dict(meta)
            entry.setdefault("id", str(uuid.uuid4()))
            entry.setdefault("ip", ip)
            entry.setdefault("hostname", ip)
            host_map[ip] = entry
    save_hosts_list(list(host_map.values()))


def load_credentials() -> list[dict]:
    if CREDENTIALS_FILE.exists():
        return json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
    return []


def save_credentials(data: list[dict]) -> None:
    CREDENTIALS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 慢日志定时报告目标配置 ────────────────────────────────────────────────────

GROUPS_FILE      = Path(os.getenv("GROUPS_FILE",      "./data/groups.json"))
USER_GROUPS_FILE = Path(os.getenv("USER_GROUPS_FILE", "./data/user_groups.json"))


def load_groups() -> list[dict]:
    if GROUPS_FILE.exists():
        try:
            return json.loads(GROUPS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def save_groups(data: list[dict]) -> None:
    GROUPS_FILE.parent.mkdir(exist_ok=True)
    GROUPS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_user_groups() -> dict[str, list[str]]:
    """返回 {user_id: [group_id, ...]}，表示每个普通用户可访问的 CMDB 分组。"""
    if USER_GROUPS_FILE.exists():
        try:
            return json.loads(USER_GROUPS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_user_groups(data: dict[str, list[str]]) -> None:
    USER_GROUPS_FILE.parent.mkdir(parents=True, exist_ok=True)
    USER_GROUPS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_user_allowed_groups(user_id: str) -> list[str] | None:
    """返回用户允许访问的分组 ID 列表；None 表示超管（不限制）。"""
    ug = load_user_groups()
    return ug.get(user_id)  # 未配置的普通用户返回空列表


SLOWLOG_TARGETS_FILE = Path(os.getenv("SLOWLOG_TARGETS_FILE", "./data/slowlog_targets.json"))

_SLOWLOG_DEFAULTS = {
    "enabled": False,
    "date_days": 1,
    "threshold_sec": 1.0,
    "alert_sec": 10.0,
    "targets": [],
}


def load_slowlog_targets() -> dict:
    if SLOWLOG_TARGETS_FILE.exists():
        try:
            return json.loads(SLOWLOG_TARGETS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return dict(_SLOWLOG_DEFAULTS)


def save_slowlog_targets(data: dict) -> None:
    SLOWLOG_TARGETS_FILE.parent.mkdir(exist_ok=True)
    SLOWLOG_TARGETS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def encrypt_password(plain: str) -> str:
    return _fernet.encrypt(plain.encode()).decode()


def decrypt_password(cipher: str) -> str:
    return _fernet.decrypt(cipher.encode()).decode()
