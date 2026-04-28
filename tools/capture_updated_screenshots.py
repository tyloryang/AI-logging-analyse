from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

import requests


ROOT = Path(__file__).resolve().parents[1]
SCREENSHOTS_DIR = ROOT / "screenshots"
PROFILE_DIR = ROOT / ".tmp-screenshot-chrome"
BASE_URL = os.getenv("SCREENSHOT_BASE_URL", "http://127.0.0.1:5173")
DEBUG_PORT = int(os.getenv("SCREENSHOT_DEBUG_PORT", "9223"))
VIEWPORT_WIDTH = int(os.getenv("SCREENSHOT_VIEWPORT_WIDTH", "1440"))
VIEWPORT_HEIGHT = int(os.getenv("SCREENSHOT_VIEWPORT_HEIGHT", "900"))
DEVICE_SCALE_FACTOR = float(os.getenv("SCREENSHOT_DEVICE_SCALE_FACTOR", "2"))
CHROME = os.getenv("CHROME_PATH", r"C:\Program Files\Google\Chrome\Application\chrome.exe")

SHOTS = [
    ("01_login.png", "/#/login", 1.2),
    ("02_dashboard.png", "/#/", 2.0),
    ("03_log_analysis.png", "/#/logs", 2.2),
    ("04_slowlog.png", "/#/slowlog", 2.2),
    ("05_cmdb.png", "/#/hosts", 2.2),
    ("06_ssh.png", "/#/ssh", 2.0),
    ("07_report.png", "/#/report", 2.2),
    ("08_admin.png", "/#/admin/users", 2.2),
]


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


class DevToolsWebSocket:
    def __init__(self, ws_url: str) -> None:
        self.ws_url = ws_url
        self.sock: socket.socket | None = None
        self.next_id = 0

    def connect(self) -> None:
        parsed = urlparse(self.ws_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 80
        path = parsed.path
        if parsed.query:
            path += f"?{parsed.query}"

        sock = socket.create_connection((host, port), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        sock.sendall(request.encode("ascii"))
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = sock.recv(4096)
            if not chunk:
                raise RuntimeError("Chrome DevTools WebSocket handshake failed")
            response += chunk
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise RuntimeError(response.decode("utf-8", errors="ignore"))
        self.sock = sock

    def close(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            finally:
                self.sock = None

    def _recv_exact(self, size: int) -> bytes:
        if not self.sock:
            raise RuntimeError("WebSocket is not connected")
        chunks = []
        remaining = size
        while remaining:
            chunk = self.sock.recv(remaining)
            if not chunk:
                raise RuntimeError("WebSocket closed")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _send_frame(self, payload: bytes, opcode: int = 0x1) -> None:
        if not self.sock:
            raise RuntimeError("WebSocket is not connected")
        header = bytearray([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def _recv_frame(self) -> str:
        while True:
            first, second = self._recv_exact(2)
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._recv_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._recv_exact(8))[0]
            mask = self._recv_exact(4) if masked else b""
            payload = self._recv_exact(length) if length else b""
            if masked:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
            if opcode == 0x8:
                raise RuntimeError("WebSocket closed by Chrome")
            if opcode == 0x9:
                self._send_frame(payload, opcode=0xA)
                continue
            if opcode == 0x1:
                return payload.decode("utf-8")

    def command(self, method: str, params: dict | None = None, timeout: float = 15) -> dict:
        self.next_id += 1
        command_id = self.next_id
        payload = {"id": command_id, "method": method}
        if params is not None:
            payload["params"] = params
        self._send_frame(json.dumps(payload, separators=(",", ":")).encode("utf-8"))

        deadline = time.time() + timeout
        while time.time() < deadline:
            message = json.loads(self._recv_frame())
            if message.get("id") == command_id:
                if "error" in message:
                    raise RuntimeError(f"{method} failed: {message['error']}")
                return message.get("result", {})
        raise TimeoutError(f"Timed out waiting for {method}")

    def evaluate(self, expression: str, await_promise: bool = False, timeout: float = 15) -> dict:
        return self.command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": await_promise,
                "returnByValue": True,
                "userGesture": True,
            },
            timeout=timeout,
        )


def wait_for_devtools() -> str:
    endpoint = f"http://127.0.0.1:{DEBUG_PORT}/json"
    deadline = time.time() + 20
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            pages = requests.get(endpoint, timeout=1).json()
            for page in pages:
                if page.get("type") == "page" and page.get("webSocketDebuggerUrl"):
                    return page["webSocketDebuggerUrl"]
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"Unable to connect to Chrome DevTools: {last_error}")


def wait_for_ready(ws: DevToolsWebSocket, extra_wait: float = 0.0) -> None:
    deadline = time.time() + 25
    while time.time() < deadline:
        try:
            result = ws.evaluate("document.readyState", timeout=5)
            value = result.get("result", {}).get("value")
            if value in ("interactive", "complete"):
                break
        except Exception:
            pass
        time.sleep(0.25)

    ws.evaluate(
        "document.fonts && document.fonts.ready ? document.fonts.ready.then(() => true) : true",
        await_promise=True,
        timeout=10,
    )
    if extra_wait:
        time.sleep(extra_wait)


def navigate(ws: DevToolsWebSocket, path: str, extra_wait: float) -> None:
    ws.command("Page.navigate", {"url": f"{BASE_URL}{path}"}, timeout=10)
    wait_for_ready(ws, extra_wait=extra_wait)


def login(ws: DevToolsWebSocket, username: str, password: str) -> None:
    script = f"""
    (async () => {{
      const username = {json.dumps(username)};
      const password = {json.dumps(password)};
      const inputs = Array.from(document.querySelectorAll('input'));
      const usernameInput = inputs.find(input => input.type !== 'password');
      const passwordInput = inputs.find(input => input.type === 'password');
      const setValue = (input, value) => {{
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
        setter.call(input, value);
        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
      }};
      setValue(usernameInput, username);
      setValue(passwordInput, password);
      const button = document.querySelector('button[type="submit"], .btn-auth, button');
      button.click();
      return true;
    }})()
    """
    ws.evaluate(script, await_promise=True, timeout=10)
    deadline = time.time() + 20
    while time.time() < deadline:
        result = ws.evaluate("location.hash", timeout=5)
        value = result.get("result", {}).get("value", "")
        if value not in ("#/login", "#/register", "#/forgot-password"):
            return
        time.sleep(0.4)
    raise RuntimeError("Login did not leave the login page")


def capture(ws: DevToolsWebSocket, output: Path) -> None:
    result = ws.command(
        "Page.captureScreenshot",
        {"format": "png", "fromSurface": True, "captureBeyondViewport": False},
        timeout=20,
    )
    output.write_bytes(base64.b64decode(result["data"]))


def launch_chrome() -> subprocess.Popen:
    if PROFILE_DIR.exists():
        shutil.rmtree(PROFILE_DIR, ignore_errors=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    args = [
        CHROME,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-crash-reporter",
        "--disable-extensions",
        "--hide-scrollbars",
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={PROFILE_DIR}",
        f"--window-size={VIEWPORT_WIDTH * int(DEVICE_SCALE_FACTOR)},{VIEWPORT_HEIGHT * int(DEVICE_SCALE_FACTOR)}",
        "about:blank",
    ]
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> None:
    env = read_env(ROOT / "backend" / ".env")
    username = os.getenv("SCREENSHOT_USERNAME") or env.get("ADMIN_USERNAME")
    password = os.getenv("SCREENSHOT_PASSWORD") or env.get("ADMIN_PASSWORD")
    if not username or not password:
        raise RuntimeError(
            "Missing screenshot login credentials. Set SCREENSHOT_USERNAME/SCREENSHOT_PASSWORD "
            "or configure ADMIN_USERNAME/ADMIN_PASSWORD in backend/.env."
        )
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    chrome = launch_chrome()
    ws: DevToolsWebSocket | None = None
    try:
        ws = DevToolsWebSocket(wait_for_devtools())
        ws.connect()
        ws.command("Page.enable")
        ws.command("Runtime.enable")
        ws.command(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": VIEWPORT_WIDTH,
                "height": VIEWPORT_HEIGHT,
                "deviceScaleFactor": DEVICE_SCALE_FACTOR,
                "mobile": False,
            },
        )

        navigate(ws, "/#/login", extra_wait=1.0)
        capture(ws, SCREENSHOTS_DIR / "01_login.png")
        print("captured screenshots/01_login.png")

        login(ws, username, password)
        wait_for_ready(ws, extra_wait=1.5)

        for name, path, wait_seconds in SHOTS[1:]:
            navigate(ws, path, extra_wait=wait_seconds)
            capture(ws, SCREENSHOTS_DIR / name)
            print(f"captured screenshots/{name}")
    finally:
        if ws:
            ws.close()
        chrome.terminate()
        try:
            chrome.wait(timeout=8)
        except subprocess.TimeoutExpired:
            chrome.kill()
        shutil.rmtree(PROFILE_DIR, ignore_errors=True)


if __name__ == "__main__":
    main()
