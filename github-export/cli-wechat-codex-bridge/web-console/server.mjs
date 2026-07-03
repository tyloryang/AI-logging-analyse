#!/usr/bin/env node

import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { CodexSessionManager } from "./lib/session-manager.mjs";
import {
  DEFAULT_BASE_URL,
  DEFAULT_WORKSPACE,
  MAX_LOG_LINES,
  ensureDir,
  getCredentialSummary,
  nowIso,
} from "./lib/shared.mjs";
import {
  fetchQrCode,
  fetchQrStatus,
  persistConfirmedAccount,
} from "./lib/wechat-auth.mjs";
import { buildQrSvgDataUrl } from "./lib/qr-svg.mjs";

const MODULE_DIR = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_DIR = path.resolve(MODULE_DIR, "..");
const PUBLIC_DIR = path.join(MODULE_DIR, "public");
const PORT = Number.parseInt(process.env.PORT || "8080", 10);
const MAX_BODY_BYTES = 32 * 1024;
const activeQrCodes = new Map();
const sessionManager = new CodexSessionManager(PROJECT_DIR);

function sendJson(res, statusCode, payload) {
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
  });
  res.end(JSON.stringify(payload, null, 2));
}

function sendText(res, statusCode, contentType, payload) {
  res.writeHead(statusCode, {
    "Content-Type": contentType,
    "Cache-Control": "no-store",
  });
  res.end(payload);
}

async function readBody(req) {
  let size = 0;
  const chunks = [];

  for await (const chunk of req) {
    size += chunk.length;
    if (size > MAX_BODY_BYTES) {
      throw new Error(`Request body too large (>${MAX_BODY_BYTES} bytes).`);
    }
    chunks.push(chunk);
  }

  if (chunks.length === 0) {
    return {};
  }

  const raw = Buffer.concat(chunks).toString("utf8").trim();
  if (!raw) {
    return {};
  }

  return JSON.parse(raw);
}

function getConsoleState() {
  return {
    defaultWorkspace: DEFAULT_WORKSPACE,
    credential: getCredentialSummary(),
    session: sessionManager.getStatus(),
    maxLogLines: MAX_LOG_LINES,
  };
}

function getMimeType(filePath) {
  if (filePath.endsWith(".html")) {
    return "text/html; charset=utf-8";
  }
  if (filePath.endsWith(".css")) {
    return "text/css; charset=utf-8";
  }
  if (filePath.endsWith(".js")) {
    return "application/javascript; charset=utf-8";
  }
  if (filePath.endsWith(".json")) {
    return "application/json; charset=utf-8";
  }
  if (filePath.endsWith(".svg")) {
    return "image/svg+xml";
  }
  return "application/octet-stream";
}

async function handleApi(req, res, pathname) {
  if (req.method === "GET" && pathname === "/api/health") {
    sendJson(res, 200, { ok: true, now: nowIso() });
    return true;
  }

  if (req.method === "GET" && pathname === "/api/config") {
    sendJson(res, 200, getConsoleState());
    return true;
  }

  if (req.method === "POST" && pathname === "/api/qrcode") {
    const body = await readBody(req);
    const baseUrl = body.baseUrl?.trim() || DEFAULT_BASE_URL;
    const qr = await fetchQrCode(baseUrl);
    const qrcodeImageUrl = buildQrSvgDataUrl(qr.qrcode_img_content);
    activeQrCodes.set(qr.qrcode, {
      baseUrl,
      qrcode: qr.qrcode,
      qrcodeImageUrl,
      qrcodeSourceUrl: qr.qrcode_img_content,
      createdAt: Date.now(),
    });
    sendJson(res, 200, {
      qrcode: qr.qrcode,
      qrcodeImageUrl,
      scanUrl: qr.qrcode_img_content,
      qrcodeSourceUrl: qr.qrcode_img_content,
      baseUrl,
      expiresHint: "请尽快扫码；如过期可重新生成。",
    });
    return true;
  }

  if (req.method === "GET" && pathname.startsWith("/api/qrcode/") && pathname.endsWith("/status")) {
    const qrcode = decodeURIComponent(pathname.slice("/api/qrcode/".length, -"/status".length));
    const qrRecord = activeQrCodes.get(qrcode);
    if (!qrRecord) {
      sendJson(res, 404, { error: "Unknown qrcode. Please generate a new one." });
      return true;
    }

    const status = await fetchQrStatus(qrRecord.baseUrl, qrcode);
    let credential = getCredentialSummary();
    if (status.status === "confirmed" && status.ilink_bot_id && status.bot_token) {
      credential = persistConfirmedAccount(qrRecord.baseUrl, status);
    }

    sendJson(res, 200, {
      status: status.status,
      confirmed: status.status === "confirmed",
      credential,
    });
    return true;
  }

  if (req.method === "POST" && pathname === "/api/session/start") {
    const body = await readBody(req);
    const status = await sessionManager.start({
      cwd: body.cwd || DEFAULT_WORKSPACE,
      profile: body.profile,
    });
    sendJson(res, 200, status);
    return true;
  }

  if (req.method === "POST" && pathname === "/api/session/stop") {
    const status = await sessionManager.stop();
    sendJson(res, 200, status);
    return true;
  }

  if (req.method === "GET" && pathname === "/api/session/status") {
    sendJson(res, 200, sessionManager.getStatus());
    return true;
  }

  if (req.method === "GET" && pathname === "/api/logs") {
    const url = new URL(req.url, `http://${req.headers.host || "localhost"}`);
    const lines = Number.parseInt(url.searchParams.get("lines") || "200", 10);
    sendJson(res, 200, {
      lines: sessionManager.getLogs(lines),
    });
    return true;
  }

  return false;
}

async function handleRequest(req, res) {
  try {
    const url = new URL(req.url || "/", `http://${req.headers.host || "localhost"}`);
    const pathname = decodeURIComponent(url.pathname);

    if (pathname.startsWith("/api/")) {
      const handled = await handleApi(req, res, pathname);
      if (!handled) {
        sendJson(res, 404, { error: `Unknown API route: ${pathname}` });
      }
      return;
    }

    const targetPath = pathname === "/" ? "/index.html" : pathname;
    const safePath = path.normalize(targetPath).replace(/^(\.\.[/\\])+/, "");
    const filePath = path.join(PUBLIC_DIR, safePath);

    if (!filePath.startsWith(PUBLIC_DIR) || !fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
      sendText(res, 404, "text/plain; charset=utf-8", "Not found");
      return;
    }

    sendText(res, 200, getMimeType(filePath), fs.readFileSync(filePath));
  } catch (error) {
    sendJson(res, 500, {
      error: error instanceof Error ? error.message : String(error),
    });
  }
}

const server = http.createServer((req, res) => {
  void handleRequest(req, res);
});

server.listen(PORT, () => {
  try {
    ensureDir(DEFAULT_WORKSPACE);
  } catch {
    // Best effort. The workspace may be a mounted read-only or pre-existing path.
  }
  sessionManager.appendSystemLog(
    `Web console started on :${PORT}. Workspace=${DEFAULT_WORKSPACE}.`,
  );
  console.log(`CLI WeChat Bridge web console listening on http://0.0.0.0:${PORT}`);
});

async function shutdown(signal) {
  sessionManager.appendSystemLog(`Received ${signal}, shutting down web console...`);
  await sessionManager.stop();
  server.close(() => process.exit(0));
}

process.on("SIGINT", () => {
  void shutdown("SIGINT");
});
process.on("SIGTERM", () => {
  void shutdown("SIGTERM");
});
