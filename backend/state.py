"""共享状态：单例实例、配置常量和辅助函数。

注意：本模块在 import 时即读取 os.getenv()，
因此调用方必须在 import 本模块之前先调用 load_dotenv()。
"""
import json
import logging
import os
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

SCHEDULE_CRON     = os.getenv("SCHEDULE_CRON", "0 9 * * *")
SCHEDULE_CHANNELS = [
    ch.strip() for ch in os.getenv("SCHEDULE_CHANNELS", "").split(",") if ch.strip()
]

# ── SSH 密钥（自动生成并持久化）─────────────────────────────────────────────

_SSH_KEY_FILE = Path(os.getenv("SSH_KEY_FILE", "./.ssh_key"))
if not os.getenv("SSH_KEY_FILE"):
    logger.warning(
        "[安全] SSH_KEY_FILE 未配置，密钥存于工作目录 %s。"
        "容器重启/迁移时若该文件丢失，已存 SSH 密码将无法解密。"
        "建议通过 SSH_KEY_FILE 环境变量指向持久化路径。",
        _SSH_KEY_FILE.resolve(),
    )
if _SSH_KEY_FILE.exists():
    _FERNET_KEY = _SSH_KEY_FILE.read_bytes().strip()
else:
    _FERNET_KEY = Fernet.generate_key()
    _SSH_KEY_FILE.write_bytes(_FERNET_KEY)
    logger.info("[启动] 已生成 SSH 密码加密密钥: %s", _SSH_KEY_FILE)

_fernet = Fernet(_FERNET_KEY)

# ── 单例客户端 ────────────────────────────────────────────────────────────────

loki      = LokiClient(LOKI_URL, LOKI_USERNAME, LOKI_PASSWORD)
logger.info("[启动] PROMETHEUS_URL=%s, auth=%s", PROMETHEUS_URL, "yes" if PROMETHEUS_USERNAME else "no")
prom      = PrometheusClient(PROMETHEUS_URL, PROMETHEUS_USERNAME, PROMETHEUS_PASSWORD)
analyzer  = AIAnalyzer()
clusterer = LogClusterer()

# ── CMDB / 凭证辅助函数 ───────────────────────────────────────────────────────

def load_cmdb() -> dict:
    if CMDB_FILE.exists():
        return json.loads(CMDB_FILE.read_text(encoding="utf-8"))
    return {}


def save_cmdb(data: dict) -> None:
    CMDB_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_credentials() -> list[dict]:
    if CREDENTIALS_FILE.exists():
        return json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
    return []


def save_credentials(data: list[dict]) -> None:
    CREDENTIALS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 慢日志定时报告目标配置 ────────────────────────────────────────────────────

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
