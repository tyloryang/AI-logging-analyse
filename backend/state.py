"""共享状态：单例实例、配置常量和辅助函数。

注意：本模块在 import 时即读取 os.getenv()，
因此调用方必须在 import 本模块之前先调用 load_dotenv()。
"""
import json
import logging
import os
import shutil
import uuid
from copy import deepcopy
from pathlib import Path

from cryptography.fernet import Fernet

from loki_client import LokiClient
from ai_analyzer import AIAnalyzer
from log_clusterer import LogClusterer
from prom_client import PrometheusClient
from json_snapshot_store import (
    load_text_snapshot,
    read_json_file,
    save_text_snapshot,
    write_json_file,
)

logger = logging.getLogger(__name__)

# ── 配置常量（settings.json 优先级高于 .env）────────────────────────────────

DATA_DIR = Path("./data")
DATA_DIR.mkdir(exist_ok=True)
SETTINGS_FILE = DATA_DIR / "settings.json"
_JSON_FILE_CACHE: dict[Path, tuple[int, int, object]] = {}


def _read_cached_json(path: Path):
    try:
        stat = path.stat()
        cached = _JSON_FILE_CACHE.get(path)
        signature = (stat.st_mtime_ns, stat.st_size)
        if cached and cached[:2] == signature:
            return deepcopy(cached[2])
    except FileNotFoundError:
        _JSON_FILE_CACHE.pop(path, None)

    data = read_json_file(path, default=None)
    if data is None:
        _JSON_FILE_CACHE.pop(path, None)
        return None

    try:
        stat = path.stat()
        _JSON_FILE_CACHE[path] = (stat.st_mtime_ns, stat.st_size, data)
    except FileNotFoundError:
        _JSON_FILE_CACHE[path] = (0, 0, data)
    return deepcopy(data)


def _write_cached_json(path: Path, data, *, ensure_parent: bool = False) -> None:
    write_json_file(path, data, ensure_parent=ensure_parent)
    stat = path.stat()
    _JSON_FILE_CACHE[path] = (stat.st_mtime_ns, stat.st_size, deepcopy(data))


def _resolve_persistent_path(env_name: str, default_name: str) -> Path:
    env_value = os.getenv(env_name, "").strip()
    if env_value:
        return Path(env_value)

    target = DATA_DIR / default_name
    legacy = Path(f"./{default_name}")
    if legacy.exists() and not target.exists():
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy, target)
            logger.info("[storage] copied legacy %s to %s", legacy.resolve(), target.resolve())
        except Exception as exc:
            logger.warning("[storage] failed to copy legacy %s to %s: %s", legacy, target, exc)
    return target


def _load_settings() -> dict:
    """从 data/settings.json 读取运行时配置覆盖"""
    data = read_json_file(SETTINGS_FILE, default={})
    return data if isinstance(data, dict) else {}


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
CMDB_FILE        = _resolve_persistent_path("CMDB_FILE", "cmdb_hosts.json")
CREDENTIALS_FILE = _resolve_persistent_path("CREDENTIALS_FILE", "ssh_credentials.json")

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
_SSH_KEY_FILE   = _resolve_persistent_path("SSH_KEY_FILE", ".ssh_key")


def _load_ssh_key_from_file(path: Path) -> bytes:
    key = path.read_bytes().strip()
    Fernet(key)
    try:
        save_text_snapshot(path, key.decode("utf-8"))
    except Exception as exc:
        logger.warning("[安全] SSH 密钥快照保存失败 %s: %s", path, exc)
    return key


def _restore_ssh_key_from_snapshot(path: Path) -> bytes | None:
    payload = load_text_snapshot(path)
    if not payload:
        return None
    key = payload.encode("utf-8")
    try:
        Fernet(key)
    except Exception as exc:
        logger.warning("[安全] SSH 密钥快照无效 %s: %s", path, exc)
        return None

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(key)
        logger.warning("[安全] SSH 密钥文件缺失，已从快照恢复到 %s", path.resolve())
    except Exception as exc:
        logger.warning("[安全] SSH 密钥文件恢复失败 %s: %s", path, exc)
    return key


if _FERNET_KEY_ENV:
    _FERNET_KEY = _FERNET_KEY_ENV.encode()
    Fernet(_FERNET_KEY)
    logger.info("[启动] SSH 加密密钥来自 SSH_FERNET_KEY 环境变量")
elif _SSH_KEY_FILE.exists():
    _FERNET_KEY = _load_ssh_key_from_file(_SSH_KEY_FILE)
    logger.info("[启动] SSH 加密密钥来自文件: %s", _SSH_KEY_FILE)
else:
    restored_key = _restore_ssh_key_from_snapshot(_SSH_KEY_FILE)
    if restored_key:
        _FERNET_KEY = restored_key
        logger.info("[启动] SSH 加密密钥来自快照恢复: %s", _SSH_KEY_FILE)
    else:
        _FERNET_KEY = Fernet.generate_key()
        _SSH_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SSH_KEY_FILE.write_bytes(_FERNET_KEY)
        try:
            save_text_snapshot(_SSH_KEY_FILE, _FERNET_KEY.decode("utf-8"))
        except Exception as exc:
            logger.warning("[安全] SSH 密钥快照保存失败 %s: %s", _SSH_KEY_FILE, exc)
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
    """CMDB 主机列表。主存储 SQLite（services.cmdb_store），
    JSON 文件仅作首次迁移来源与导出镜像；DB 异常时回退 JSON。"""
    from services import cmdb_store

    try:
        hosts = cmdb_store.load_hosts()
    except Exception as exc:
        logger.warning("[CMDB] SQLite 读取异常，回退 JSON: %s", exc)
        return _load_hosts_from_json()

    if hosts is not None:
        return hosts

    # 尚未迁移：从 JSON 读取并一次性导入 SQLite
    legacy = _load_hosts_from_json()
    try:
        cmdb_store.save_hosts(legacy)
        logger.info("[CMDB] 已迁移 %d 台主机到 SQLite 主存储", len(legacy))
    except Exception as exc:
        logger.warning("[CMDB] 迁移到 SQLite 失败（继续用 JSON）: %s", exc)
    return legacy


def _load_hosts_from_json() -> list[dict]:
    """旧 JSON 存储读取 + 历史 dict 格式自动迁移（仅迁移期/降级期使用）。"""
    if CMDB_FILE.exists():
        try:
            data = _read_cached_json(CMDB_FILE)
            if isinstance(data, list):
                # 确保每条记录都有 id
                changed = False
                for h in data:
                    if not h.get("id"):
                        h["id"] = str(uuid.uuid4())
                        changed = True
                if changed:
                    _write_cached_json(CMDB_FILE, data)
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
            _write_cached_json(CMDB_FILE, result)
            logger.info("[CMDB] 旧格式自动迁移完成，共 %d 台主机", len(result))
            return result
        except Exception as exc:
            logger.warning("[CMDB] load_hosts_list 异常: %s", exc)
    return []


def save_hosts_list(hosts: list[dict]) -> None:
    """保存主机列表：SQLite 事务为主（失败抛给调用方），JSON 镜像为灾备/兼容。"""
    from services import cmdb_store

    cmdb_store.save_hosts(hosts)
    try:
        # 导出镜像：兼容直接读 cmdb_hosts.json 的模块（agent 工具等），
        # 且经 json_snapshot_store 再冗余一份到 sqlite 快照表
        _write_cached_json(CMDB_FILE, hosts, ensure_parent=True)
    except Exception as exc:
        logger.warning("[CMDB] JSON 镜像写入失败（主存储已保存）: %s", exc)


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
        data = _read_cached_json(CREDENTIALS_FILE)
        if isinstance(data, list):
            return data
    return []


def save_credentials(data: list[dict]) -> None:
    _write_cached_json(CREDENTIALS_FILE, data, ensure_parent=True)


# ── 慢日志定时报告目标配置 ────────────────────────────────────────────────────

GROUPS_FILE      = Path(os.getenv("GROUPS_FILE",      "./data/groups.json"))
USER_GROUPS_FILE = Path(os.getenv("USER_GROUPS_FILE", "./data/user_groups.json"))
K8S_USER_CLUSTERS_FILE = Path(os.getenv("K8S_USER_CLUSTERS_FILE", "./data/user_k8s_clusters.json"))


def _normalize_alert_matchers(matchers) -> list[dict]:
    normalized: list[dict] = []
    if not isinstance(matchers, list):
        return normalized
    for item in matchers:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("key") or "").strip()
        value = str(item.get("value") or "").strip()
        if not label:
            continue
        normalized.append({"label": label, "value": value})
    return normalized


def _normalize_group(group: dict) -> dict:
    item = dict(group or {})
    item["id"] = str(item.get("id", "")).strip()
    item["name"] = str(item.get("name", "")).strip()
    item["description"] = str(item.get("description", "") or "").strip()
    item["feishu_webhook"] = str(item.get("feishu_webhook", "") or "").strip()
    item["feishu_keyword"] = str(item.get("feishu_keyword", "") or "").strip()
    item["dingtalk_webhook"] = str(item.get("dingtalk_webhook", "") or "").strip()
    item["dingtalk_keyword"] = str(item.get("dingtalk_keyword", "") or "").strip()
    item["schedule_enabled"] = bool(item.get("schedule_enabled", False))
    item["schedule_time"] = str(item.get("schedule_time", "") or "08:00").strip() or "08:00"
    item["alert_matchers"] = _normalize_alert_matchers(item.get("alert_matchers"))
    return item


def load_groups() -> list[dict]:
    if GROUPS_FILE.exists():
        try:
            data = _read_cached_json(GROUPS_FILE)
            if isinstance(data, list):
                return [_normalize_group(item) for item in data if isinstance(item, dict)]
        except Exception:
            pass
    return []


def save_groups(data: list[dict]) -> None:
    normalized = [_normalize_group(item) for item in data if isinstance(item, dict)]
    _write_cached_json(GROUPS_FILE, normalized, ensure_parent=True)


def load_user_groups() -> dict[str, list[str]]:
    """返回 {user_id: [group_id, ...]}，表示每个普通用户可访问的 CMDB 分组。"""
    if USER_GROUPS_FILE.exists():
        try:
            data = _read_cached_json(USER_GROUPS_FILE)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def save_user_groups(data: dict[str, list[str]]) -> None:
    _write_cached_json(USER_GROUPS_FILE, data, ensure_parent=True)


def get_user_allowed_groups(user_id: str) -> list[str] | None:
    """返回用户允许访问的分组 ID 列表；None 表示超管（不限制）。"""
    ug = load_user_groups()
    return ug.get(user_id)  # 未配置的普通用户返回空列表


def load_user_k8s_clusters() -> dict[str, list[str]]:
    if K8S_USER_CLUSTERS_FILE.exists():
        try:
            data = _read_cached_json(K8S_USER_CLUSTERS_FILE)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def save_user_k8s_clusters(data: dict[str, list[str]]) -> None:
    _write_cached_json(K8S_USER_CLUSTERS_FILE, data, ensure_parent=True)


def get_user_allowed_k8s_clusters(user_id: str) -> list[str] | None:
    mapping = load_user_k8s_clusters()
    return mapping.get(user_id)


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
            data = _read_cached_json(SLOWLOG_TARGETS_FILE)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return dict(_SLOWLOG_DEFAULTS)


def save_slowlog_targets(data: dict) -> None:
    _write_cached_json(SLOWLOG_TARGETS_FILE, data, ensure_parent=True)


def encrypt_password(plain: str) -> str:
    return _fernet.encrypt(plain.encode()).decode()


def decrypt_password(cipher: str) -> str:
    return _fernet.decrypt(cipher.encode()).decode()
