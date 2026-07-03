import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export const DEFAULT_BASE_URL =
  process.env.WECHAT_ILINK_BASE_URL?.trim() || "https://ilinkai.weixin.qq.com";

export const CHANNEL_DATA_DIR = process.env.CLAUDE_WECHAT_CHANNEL_DATA_DIR?.trim()
  ? path.resolve(process.env.CLAUDE_WECHAT_CHANNEL_DATA_DIR.trim())
  : path.join(os.homedir(), ".claude", "channels", "wechat");

export const CREDENTIALS_FILE = path.join(CHANNEL_DATA_DIR, "account.json");
export const WORKSPACES_DIR = path.join(CHANNEL_DATA_DIR, "workspaces");
const configuredWorkspace = process.env.CODEX_WORKSPACE?.trim();
export const DEFAULT_WORKSPACE = configuredWorkspace
  ? path.resolve(configuredWorkspace)
  : fs.existsSync("/workspace")
    ? path.resolve("/workspace")
    : process.cwd();
export const MAX_LOG_LINES = Number.parseInt(process.env.MAX_LOG_LINES || "500", 10);

export function nowIso() {
  return new Date().toISOString();
}

export function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

export function sanitizeWorkspaceSegment(value) {
  const sanitized = value
    .replace(/[^a-zA-Z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);
  return sanitized || "workspace";
}

export function normalizeComparableWorkspacePath(cwd) {
  const normalized = path.resolve(cwd);
  return process.platform === "win32" ? normalized.toLowerCase() : normalized;
}

export function buildWorkspaceKey(cwd) {
  const normalized = path.resolve(cwd);
  const digest = crypto
    .createHash("sha256")
    .update(normalizeComparableWorkspacePath(normalized))
    .digest("hex")
    .slice(0, 12);
  const label = sanitizeWorkspaceSegment(path.basename(normalized));
  return `${label}-${digest}`;
}

export function getWorkspaceEndpointFile(cwd) {
  return path.join(WORKSPACES_DIR, buildWorkspaceKey(cwd), "codex-panel-endpoint.json");
}

export function readJson(filePath) {
  try {
    if (!fs.existsSync(filePath)) {
      return null;
    }
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch {
    return null;
  }
}

export function maskIdentifier(value) {
  if (!value || typeof value !== "string") {
    return null;
  }
  if (value.length <= 10) {
    return value;
  }
  return `${value.slice(0, 4)}***${value.slice(-4)}`;
}

export function getCredentialSummary() {
  const account = readJson(CREDENTIALS_FILE);
  if (!account) {
    return {
      exists: false,
      file: CREDENTIALS_FILE,
    };
  }

  return {
    exists: true,
    file: CREDENTIALS_FILE,
    accountId: account.accountId || null,
    accountIdMasked: maskIdentifier(account.accountId || ""),
    userIdMasked: maskIdentifier(account.userId || ""),
    savedAt: account.savedAt || null,
    baseUrl: account.baseUrl || DEFAULT_BASE_URL,
  };
}

export class LogBuffer {
  constructor(limit = MAX_LOG_LINES) {
    this.limit = Math.max(100, limit);
    this.lines = [];
    this.partials = new Map();
  }

  append(source, chunk) {
    const text = typeof chunk === "string" ? chunk : chunk.toString("utf8");
    const prefix = `[${source}]`;
    const current = `${this.partials.get(source) || ""}${text}`;
    const parts = current.split(/\r?\n/);
    const remainder = parts.pop() ?? "";

    for (const part of parts) {
      const line = part.trimEnd();
      if (!line) {
        continue;
      }
      this.push(`${nowIso()} ${prefix} ${line}`);
    }

    this.partials.set(source, remainder);
  }

  flush(source) {
    const remainder = this.partials.get(source);
    if (!remainder) {
      return;
    }
    this.partials.delete(source);
    this.push(`${nowIso()} [${source}] ${remainder.trimEnd()}`);
  }

  push(line) {
    this.lines.push(line);
    if (this.lines.length > this.limit) {
      this.lines.splice(0, this.lines.length - this.limit);
    }
  }

  tail(lines = 200) {
    const count = Math.max(1, Math.min(lines, this.limit));
    return this.lines.slice(-count);
  }
}

export function isChildRunning(child) {
  if (!child) {
    return false;
  }
  if (child.kind === "pty") {
    return Boolean(child.running);
  }
  return child.exitCode === null && child.signalCode === null;
}

export async function waitFor(ms) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

export async function waitForExit(child, timeoutMs) {
  if (!child || !isChildRunning(child)) {
    return true;
  }

  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (!isChildRunning(child)) {
      return true;
    }
    await waitFor(200);
  }

  return !isChildRunning(child);
}

export function terminateChild(child, force = false) {
  if (!child || !isChildRunning(child)) {
    return;
  }

  try {
    if (force) {
      child.kill("SIGKILL");
      return;
    }

    if (process.platform === "win32") {
      child.kill();
    } else {
      child.kill("SIGTERM");
    }
  } catch {
    // Best effort.
  }
}
