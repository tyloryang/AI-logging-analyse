import asyncio
import json
import os
import shlex
import sys
import tarfile
import tempfile
import time
from pathlib import Path

import asyncssh


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
REGISTRY = "192.168.9.221:5000"
TARGET_HOST = "192.168.9.221"


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_auth(host_ip: str) -> dict:
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


def _add_path(tar: tarfile.TarFile, path: Path, arcname: str) -> None:
    tar.add(path, arcname=arcname)


def _create_archive() -> Path:
    include_paths = [
        ROOT / ".dockerignore",
        ROOT / "backend",
        ROOT / "frontend",
        ROOT / "config",
        ROOT / "k8s",
    ]

    fd, temp_name = tempfile.mkstemp(prefix="aiops-deploy-", suffix=".tar.gz")
    os.close(fd)
    archive_path = Path(temp_name)

    with tarfile.open(archive_path, "w:gz") as tar:
        for path in include_paths:
            if not path.exists():
                raise RuntimeError(f"required path missing: {path}")
            _add_path(tar, path, path.relative_to(ROOT).as_posix())
    return archive_path


async def _run_remote(conn: asyncssh.SSHClientConnection, command: str) -> str:
    result = await conn.run(command, check=True)
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)
    return result.stdout


async def main() -> int:
    auth = _resolve_auth(TARGET_HOST)
    archive_path = _create_archive()
    stamp = time.strftime("%Y%m%d%H%M%S")
    remote_archive = f"/tmp/aiops-deploy-{stamp}.tar.gz"
    remote_dir = f"/opt/aiops-deploy-{stamp}"

    print(f"[1/5] connecting to {auth['host']}:{auth['port']} as {auth['username']}")
    async with asyncssh.connect(
        auth["host"],
        port=auth["port"],
        username=auth["username"],
        password=auth["password"],
        known_hosts=None,
    ) as conn:
        print("[2/5] checking remote prerequisites")
        await _run_remote(
            conn,
            "bash -lc " + shlex.quote("set -euo pipefail; command -v docker; command -v kubectl; command -v tar"),
        )

        print("[3/5] uploading current workspace archive")
        async with conn.start_sftp_client() as sftp:
            await sftp.put(str(archive_path), remote_archive)

        print("[4/5] extracting workspace on remote host")
        await _run_remote(
            conn,
            "bash -lc "
            + shlex.quote(
                f"set -euo pipefail; mkdir -p {shlex.quote(remote_dir)}; "
                f"tar -xzf {shlex.quote(remote_archive)} -C {shlex.quote(remote_dir)}"
            ),
        )

        print("[5/5] building images and redeploying k8s")
        deploy_script = f"""
set -euo pipefail
cd {shlex.quote(remote_dir)}
docker build -f backend/Dockerfile -t {REGISTRY}/aiops-backend:latest .
docker push {REGISTRY}/aiops-backend:latest
docker build -f frontend/Dockerfile -t {REGISTRY}/aiops-frontend:latest .
docker push {REGISTRY}/aiops-frontend:latest
kubectl apply --validate=false -f k8s/namespace.yaml
kubectl apply --validate=false -f k8s/configmap.yaml
kubectl apply --validate=false -f k8s/secret.yaml
kubectl apply --validate=false -f k8s/pvc.yaml
kubectl apply --validate=false -f k8s/redis.yaml
kubectl apply --validate=false -f k8s/grafana.yaml
kubectl apply --validate=false -f k8s/backend.yaml
kubectl apply --validate=false -f k8s/frontend.yaml
kubectl rollout restart deployment/backend -n aiops
kubectl rollout restart deployment/frontend -n aiops
kubectl rollout status deployment/backend -n aiops --timeout=300s
kubectl rollout status deployment/frontend -n aiops --timeout=180s
kubectl get pods -n aiops
kubectl get svc -n aiops
curl -fsS http://192.168.9.221:30800/api/health
curl -fsS http://192.168.9.221:30801/healthz
"""
        await _run_remote(conn, "bash -lc " + shlex.quote(deploy_script))

    try:
        archive_path.unlink()
    except OSError:
        pass
    print(f"remote deploy finished from {remote_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
