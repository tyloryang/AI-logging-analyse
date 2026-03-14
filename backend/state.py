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

# ── 配置常量 ──────────────────────────────────────────────────────────────────

LOKI_URL          = os.getenv("LOKI_URL", "http://localhost:3100")
LOKI_USERNAME     = os.getenv("LOKI_USERNAME", "")
LOKI_PASSWORD     = os.getenv("LOKI_PASSWORD", "")
PROMETHEUS_URL    = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
PROMETHEUS_USERNAME = os.getenv("PROMETHEUS_USERNAME", "")
PROMETHEUS_PASSWORD = os.getenv("PROMETHEUS_PASSWORD", "")

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


def encrypt_password(plain: str) -> str:
    return _fernet.encrypt(plain.encode()).decode()


def decrypt_password(cipher: str) -> str:
    return _fernet.decrypt(cipher.encode()).decode()
