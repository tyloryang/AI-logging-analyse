import asyncio
import base64
import gzip
import json
import os
import shlex
import sys
import time
from pathlib import Path

import asyncssh
import yaml


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
TARGET_HOST = "192.168.9.221"
ALERTMANAGER_NAMESPACE = "monitoring"
ALERTMANAGER_SECRET = "alertmanager-main"
ALERTMANAGER_WEBHOOK_URL = "http://backend.aiops.svc.cluster.local:8000/api/alerts/webhook"
ALERTMANAGER_SERVICE_URL = "http://alertmanager-main.monitoring.svc.cluster.local:9093"
KUBECTL = (
    "env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy "
    "kubectl --kubeconfig=/opt/kubernetes/cfg/kube-controller-manager.kubeconfig"
)

for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except Exception:
            pass


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_auth(host_ip: str) -> dict:
    backend_key = BACKEND_DIR / ".ssh_key"
    if backend_key.exists() and not os.getenv("SSH_KEY_FILE"):
        os.environ["SSH_KEY_FILE"] = str(backend_key)
    sys.path.insert(0, str(BACKEND_DIR))
    from state import decrypt_password  # pylint: disable=import-error

    hosts_path = BACKEND_DIR / "cmdb_hosts.json"
    creds_path = BACKEND_DIR / "ssh_credentials.json"

    hosts = _load_json(hosts_path)
    creds = _load_json(creds_path)

    host = next((item for item in hosts if item.get("ip") == host_ip), None)
    if not host:
        raise RuntimeError(f"host {host_ip} not found in {hosts_path}")

    cred_id = host.get("credential_id", "")
    if cred_id:
        cred = next((item for item in creds if item.get("id") == cred_id), None)
        if not cred:
            raise RuntimeError(f"credential {cred_id} not found for host {host_ip}")
        return {
            "host": host_ip,
            "port": int(cred.get("port") or host.get("ssh_port") or 22),
            "username": cred.get("username") or host.get("ssh_user") or "root",
            "password": decrypt_password(cred["password"]),
        }

    cipher = host.get("ssh_password", "")
    if not cipher:
        raise RuntimeError(f"no ssh password configured for host {host_ip}")
    return {
        "host": host_ip,
        "port": int(host.get("ssh_port") or 22),
        "username": host.get("ssh_user") or "root",
        "password": decrypt_password(cipher),
    }


async def _run_remote(conn: asyncssh.SSHClientConnection, command: str, check: bool = True) -> str:
    result = await conn.run(command, check=check)
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)
    return result.stdout


def _strip_banner(text: str) -> str:
    marker = "{"
    if marker in text:
        return text[text.index(marker):]
    return text


def _ensure_webhook(receivers: list[dict], receiver_name: str, url: str) -> bool:
    for receiver in receivers:
        if receiver.get("name") != receiver_name:
            continue
        configs = receiver.setdefault("webhook_configs", [])
        for config in configs:
            if str(config.get("url", "")).strip() == url:
                changed = False
                if not config.get("send_resolved", False):
                    config["send_resolved"] = True
                    changed = True
                return changed
        configs.append({"url": url, "send_resolved": True})
        return True

    receivers.append(
        {
            "name": receiver_name,
            "webhook_configs": [{"url": url, "send_resolved": True}],
        }
    )
    return True


def _patch_alertmanager_config(raw_yaml: str) -> tuple[str, bool]:
    config = yaml.safe_load(raw_yaml) or {}
    receivers = config.setdefault("receivers", [])

    changed = False
    changed = _ensure_webhook(receivers, "Default", ALERTMANAGER_WEBHOOK_URL) or changed
    changed = _ensure_webhook(receivers, "Critical", ALERTMANAGER_WEBHOOK_URL) or changed

    rendered = yaml.safe_dump(
        config,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    return rendered, changed


async def main() -> int:
    auth = _resolve_auth(TARGET_HOST)
    stamp = time.strftime("%Y%m%d%H%M%S")
    backup_path = f"/root/{ALERTMANAGER_SECRET}-backup-{stamp}.yaml"

    print(f"[1/6] connecting to {auth['host']}:{auth['port']} as {auth['username']}")
    async with asyncssh.connect(
        auth["host"],
        port=auth["port"],
        username=auth["username"],
        password=auth["password"],
        known_hosts=None,
    ) as conn:
        print("[2/6] checking current alertmanager resources")
        await _run_remote(
            conn,
            "bash -lc "
            + shlex.quote(
                f"{KUBECTL} get alertmanager,svc,pod -n {ALERTMANAGER_NAMESPACE} | grep -i alertmanager"
            ),
        )

        print("[3/6] backing up current alertmanager secret")
        await _run_remote(
            conn,
            "bash -lc "
            + shlex.quote(
                f"{KUBECTL} get secret {ALERTMANAGER_SECRET} -n {ALERTMANAGER_NAMESPACE} -o yaml > {backup_path}"
            ),
        )

        print("[4/6] patching alertmanager webhook receiver")
        secret_stdout = await _run_remote(
            conn,
            "bash -lc "
            + shlex.quote(
                f"{KUBECTL} get secret {ALERTMANAGER_SECRET} -n {ALERTMANAGER_NAMESPACE} -o json"
            ),
        )
        secret = json.loads(_strip_banner(secret_stdout))
        raw_yaml = base64.b64decode(secret["data"]["alertmanager.yaml"]).decode("utf-8")
        patched_yaml, changed = _patch_alertmanager_config(raw_yaml)

        if changed:
            patch_payload = {
                "data": {
                    "alertmanager.yaml": base64.b64encode(patched_yaml.encode("utf-8")).decode("ascii")
                }
            }
            patch_json = json.dumps(patch_payload, separators=(",", ":"))
            await _run_remote(
                conn,
                "bash -lc "
                + shlex.quote(
                    f"{KUBECTL} patch secret {ALERTMANAGER_SECRET} -n {ALERTMANAGER_NAMESPACE} "
                    f"--type merge -p {shlex.quote(patch_json)}"
                ),
            )
        else:
            print("alertmanager webhook config already present")

        print("[5/6] updating aiops backend alertmanager url and restarting backend")
        configmap_patch = json.dumps({"data": {"ALERTMANAGER_URL": ALERTMANAGER_SERVICE_URL}})
        await _run_remote(
            conn,
            "bash -lc "
            + shlex.quote(
                f"{KUBECTL} patch configmap aiops-config -n aiops --type merge -p {shlex.quote(configmap_patch)}"
            ),
        )
        await _run_remote(
            conn,
            "bash -lc " + shlex.quote(f"{KUBECTL} rollout restart deployment/backend -n aiops"),
        )
        await _run_remote(
            conn,
            "bash -lc "
            + shlex.quote(f"{KUBECTL} rollout status deployment/backend -n aiops --timeout=300s"),
        )

        print("[6/6] verifying alertmanager and backend state")
        generated_stdout = await _run_remote(
            conn,
            "bash -lc "
            + shlex.quote(
                f"{KUBECTL} get secret {ALERTMANAGER_SECRET}-generated -n {ALERTMANAGER_NAMESPACE} -o json"
            ),
        )
        generated_secret = json.loads(_strip_banner(generated_stdout))
        generated_cfg = gzip.decompress(
            base64.b64decode(generated_secret["data"]["alertmanager.yaml.gz"])
        ).decode("utf-8")
        if ALERTMANAGER_WEBHOOK_URL not in generated_cfg:
            raise RuntimeError("generated alertmanager config does not contain aiops webhook")
        print("generated alertmanager config contains aiops webhook")
        await _run_remote(
            conn,
            "bash -lc "
            + shlex.quote(
                "env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy "
                "curl -fsS http://192.168.9.221:30800/api/health"
            ),
        )
        await _run_remote(
            conn,
            "bash -lc "
            + shlex.quote(
                f"{KUBECTL} get pods -n aiops -l app=backend && {KUBECTL} get pods -n {ALERTMANAGER_NAMESPACE} | grep alertmanager"
            ),
        )

    print(f"alertmanager link complete; backup saved to {backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
