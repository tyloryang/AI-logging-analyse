#!/usr/bin/env node

import fs from "node:fs";
import net from "node:net";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

import {
  BRIDGE_LOG_FILE,
  CREDENTIALS_FILE,
  migrateLegacyChannelFiles,
} from "../wechat/channel-config.ts";
import {
  readBridgeLockFile,
  shouldAutoReclaimBridgeLock,
  type BridgeLockPayload,
} from "../bridge/bridge-state.ts";
import {
  clearLocalCompanionEndpoint,
  readLocalCompanionEndpoint,
  type LocalCompanionEndpoint,
} from "./local-companion-link.ts";
import type { BridgeAdapterKind } from "../bridge/bridge-types.ts";

type LocalCompanionLaunchAdapter = Exclude<BridgeAdapterKind, "shell">;

type LocalCompanionStartCliOptions = {
  adapter: LocalCompanionLaunchAdapter;
  cwd: string;
  profile?: string;
  timeoutMs: number;
};

type EndpointReadResult = {
  endpoint: LocalCompanionEndpoint | null;
};

const MODULE_DIR = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_WAIT_TIMEOUT_MS = 15_000;
const DEFAULT_ADAPTER: LocalCompanionLaunchAdapter = "codex";

function log(adapter: LocalCompanionLaunchAdapter, message: string): void {
  process.stderr.write(`[wechat-${adapter}-start] ${message}\n`);
}

export function normalizeComparablePath(cwd: string): string {
  const normalized = path.resolve(cwd);
  return process.platform === "win32" ? normalized.toLowerCase() : normalized;
}

export function isSameWorkspaceCwd(left: string, right: string): boolean {
  return normalizeComparablePath(left) === normalizeComparablePath(right);
}

export function parseCliArgs(argv: string[]): LocalCompanionStartCliOptions {
  let adapter: LocalCompanionLaunchAdapter = DEFAULT_ADAPTER;
  let cwd = process.cwd();
  let profile: string | undefined;
  let timeoutMs = DEFAULT_WAIT_TIMEOUT_MS;

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = argv[i + 1];

    if (arg === "--help" || arg === "-h") {
      process.stdout.write(
        [
          "Usage: wechat-codex-start [--cwd <path>] [--profile <name-or-path>] [--timeout-ms <ms>]",
          "       wechat-claude-start [--cwd <path>] [--profile <name-or-path>] [--timeout-ms <ms>]",
          "       wechat-opencode-start [--cwd <path>] [--profile <name-or-path>] [--timeout-ms <ms>]",
          "       local-companion-start [--adapter <codex|claude|opencode>] [--cwd <path>] [--profile <name-or-path>] [--timeout-ms <ms>]",
          "",
          "Starts or reuses a Codex, Claude, or OpenCode bridge for the current directory, waits for the local endpoint, then opens the visible companion or panel.",
          "All adapters are companion-bound: closing the companion/panel also stops the bridge.",
          "",
        ].join("\n"),
      );
      process.exit(0);
    }

    if (arg === "--adapter") {
      if (!next || !["codex", "claude", "opencode"].includes(next)) {
        throw new Error(`Invalid adapter: ${next ?? "(missing)"}`);
      }
      adapter = next as LocalCompanionLaunchAdapter;
      i += 1;
      continue;
    }

    if (arg === "--cwd") {
      if (!next) {
        throw new Error("--cwd requires a value");
      }
      cwd = path.resolve(next);
      i += 1;
      continue;
    }

    if (arg === "--profile") {
      if (!next) {
        throw new Error("--profile requires a value");
      }
      profile = next;
      i += 1;
      continue;
    }

    if (arg === "--timeout-ms") {
      if (!next) {
        throw new Error("--timeout-ms requires a value");
      }
      const parsed = Number(next);
      if (!Number.isFinite(parsed) || parsed < 1000) {
        throw new Error("--timeout-ms must be a number >= 1000");
      }
      timeoutMs = Math.trunc(parsed);
      i += 1;
      continue;
    }

    throw new Error(`Unknown argument: ${arg}`);
  }

  return { adapter, cwd, profile, timeoutMs };
}

function isPidAlive(pid: number): boolean {
  if (!Number.isInteger(pid) || pid <= 0) {
    return false;
  }

  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

async function waitForProcessExit(pid: number, timeoutMs: number): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (!isPidAlive(pid)) {
      return true;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  return !isPidAlive(pid);
}

async function stopExistingBridge(
  lock: BridgeLockPayload,
  requestedAdapter: LocalCompanionLaunchAdapter,
): Promise<void> {
  const { pid, cwd } = lock;
  log(requestedAdapter, `Stopping existing bridge for ${cwd} (pid=${pid})...`);

  try {
    process.kill(pid);
  } catch (error) {
    if (isPidAlive(pid)) {
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(`Failed to stop existing bridge pid=${pid}: ${message}`);
    }
  }

  if (!(await waitForProcessExit(pid, 10_000))) {
    throw new Error(`Timed out waiting for existing bridge pid=${pid} to exit.`);
  }

  clearLocalCompanionEndpoint(cwd);
  log(
    requestedAdapter,
    `Cleared stale local companion endpoint for previous workspace ${cwd}.`,
  );
}

async function isEndpointReachable(endpoint: LocalCompanionEndpoint): Promise<boolean> {
  await new Promise<void>((resolve) => setTimeout(resolve, 0));

  return await new Promise<boolean>((resolve) => {
    const port = endpoint.serverPort ?? endpoint.port;
    const socket = net.connect({
      host: "127.0.0.1",
      port,
    });

    let done = false;
    const finish = (result: boolean) => {
      if (done) {
        return;
      }
      done = true;
      socket.destroy();
      resolve(result);
    };

    socket.setTimeout(400);
    socket.once("connect", () => finish(true));
    socket.once("timeout", () => finish(false));
    socket.once("error", () => finish(false));
  });
}

async function readUsableEndpoint(
  cwd: string,
  adapter: LocalCompanionLaunchAdapter,
): Promise<EndpointReadResult> {
  const endpoint = readLocalCompanionEndpoint(cwd);
  if (!endpoint || endpoint.kind !== adapter) {
    return { endpoint: null };
  }

  if (await isEndpointReachable(endpoint)) {
    return { endpoint };
  }

  clearLocalCompanionEndpoint(cwd, endpoint.instanceId);
  log(adapter, `Removed stale local companion endpoint for ${cwd}.`);
  return { endpoint: null };
}

export function buildBackgroundBridgeArgs(
  entryPath: string,
  options: LocalCompanionStartCliOptions,
): string[] {
  const lifecycle = "companion_bound";
  const args = [
    "--no-warnings",
    "--experimental-strip-types",
    entryPath,
    "--adapter",
    options.adapter,
    "--cwd",
    options.cwd,
    "--lifecycle",
    lifecycle,
  ];

  if (options.profile) {
    args.push("--profile", options.profile);
  }

  return args;
}

export function resolveForegroundClientEntryPath(
  _adapter: LocalCompanionLaunchAdapter,
): string {
  return path.resolve(MODULE_DIR, "local-companion.ts");
}

export function buildForegroundClientArgs(
  entryPath: string,
  options: LocalCompanionStartCliOptions,
): string[] {
  return [
    "--no-warnings",
    "--experimental-strip-types",
    entryPath,
    "--adapter",
    options.adapter,
    "--cwd",
    options.cwd,
  ];
}

function startBridgeInBackground(options: LocalCompanionStartCliOptions): void {
  const entryPath = path.resolve(MODULE_DIR, "..", "bridge", "wechat-bridge.ts");
  const args = buildBackgroundBridgeArgs(entryPath, options);

  const child = spawn(process.execPath, args, {
    cwd: options.cwd,
    env: process.env,
    detached: true,
    stdio: "ignore",
    windowsHide: true,
  });

  child.unref();
}

async function waitForEndpoint(
  cwd: string,
  adapter: LocalCompanionLaunchAdapter,
  timeoutMs: number,
): Promise<LocalCompanionEndpoint> {
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    const result = await readUsableEndpoint(cwd, adapter);
    if (result.endpoint) {
      return result.endpoint;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }

  throw new Error(
    `Timed out waiting for the ${adapter} bridge endpoint for ${cwd}. Check ${BRIDGE_LOG_FILE}.`,
  );
}

async function ensureBridgeReady(options: LocalCompanionStartCliOptions): Promise<void> {
  // If the lock is absent or the lock-holding process is dead, do NOT trust a
  // leftover endpoint.  The bridge (WeChat transport) may have crashed while
  // the opencode server kept running.  Starting only the panel would leave no
  // bridge to poll WeChat messages.
  const lock = readBridgeLockFile();
  const lockProcessAlive = lock ? isPidAlive(lock.pid) : false;
  if (!lock || !lockProcessAlive) {
    if (lock && !lockProcessAlive) {
      log(options.adapter, `Found stale lock for ${options.cwd} (pid=${lock.pid} dead). Clearing.`);
      clearLocalCompanionEndpoint(options.cwd);
    }

    log(options.adapter, `Starting bridge in background for ${options.cwd}...`);
    startBridgeInBackground(options);
    await waitForEndpoint(options.cwd, options.adapter, options.timeoutMs);
    return;
  }

  // Lock is held by a live process — check whether we can reuse or need to replace it.
  if (shouldAutoReclaimBridgeLock(lock)) {
    await stopExistingBridge(lock, options.adapter);
    log(options.adapter, `Starting replacement bridge in background for ${options.cwd}...`);
    startBridgeInBackground(options);
    await waitForEndpoint(options.cwd, options.adapter, options.timeoutMs);
    return;
  }

  if (lock.adapter !== options.adapter || !isSameWorkspaceCwd(lock.cwd, options.cwd)) {
    await stopExistingBridge(lock, options.adapter);
    log(options.adapter, `Starting replacement bridge in background for ${options.cwd}...`);
    startBridgeInBackground(options);
    await waitForEndpoint(options.cwd, options.adapter, options.timeoutMs);
    return;
  }

  const endpointResult = await readUsableEndpoint(options.cwd, options.adapter);
  if (endpointResult.endpoint) {
    log(options.adapter, `Reusing running bridge for ${options.cwd}.`);
    return;
  }

  log(options.adapter, `Found running bridge for ${options.cwd}. Waiting for endpoint...`);
  await waitForEndpoint(options.cwd, options.adapter, options.timeoutMs);
}

async function runVisibleClient(options: LocalCompanionStartCliOptions): Promise<number> {
  const entryPath = resolveForegroundClientEntryPath(options.adapter);
  const args = buildForegroundClientArgs(entryPath, options);

  return await new Promise<number>((resolve, reject) => {
    const child = spawn(process.execPath, args, {
      cwd: options.cwd,
      env: process.env,
      stdio: "inherit",
    });

    child.once("error", (error) => reject(error));
    child.once("exit", (code, signal) => {
      if (signal) {
        process.kill(process.pid, signal);
        return;
      }
      resolve(code ?? 0);
    });
  });
}

async function main(): Promise<void> {
  const options = parseCliArgs(process.argv.slice(2));
  migrateLegacyChannelFiles((message) => log(options.adapter, message));

  if (!fs.existsSync(CREDENTIALS_FILE)) {
    throw new Error(`Missing WeChat credentials. Run "bun run setup" first. (${CREDENTIALS_FILE})`);
  }

  await ensureBridgeReady(options);
  const exitCode = await runVisibleClient(options);
  process.exit(exitCode);
}

const isDirectRun = Boolean((import.meta as ImportMeta & { main?: boolean }).main);
if (isDirectRun) {
  main().catch((error) => {
    const adapter = (() => {
      try {
        return parseCliArgs(process.argv.slice(2)).adapter;
      } catch {
        return DEFAULT_ADAPTER;
      }
    })();
    log(adapter, error instanceof Error ? error.message : String(error));
    process.exit(1);
  });
}
