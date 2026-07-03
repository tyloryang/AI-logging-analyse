import { spawn } from "node:child_process";
import path from "node:path";
import { spawn as spawnPty } from "node-pty";

import {
  CREDENTIALS_FILE,
  DEFAULT_WORKSPACE,
  LogBuffer,
  ensureDir,
  getWorkspaceEndpointFile,
  isChildRunning,
  nowIso,
  readJson,
  terminateChild,
  waitFor,
  waitForExit,
} from "./shared.mjs";

export class CodexSessionManager {
  constructor(projectDir) {
    this.projectDir = projectDir;
    this.bridge = null;
    this.companion = null;
    this.current = null;
    this.logs = new LogBuffer();
    this.pending = Promise.resolve();
  }

  createManagedPty(name, ptyProcess) {
    const managed = {
      kind: "pty",
      pid: ptyProcess.pid,
      running: true,
      kill: () => {
        if (!managed.running) {
          return;
        }
        try {
          ptyProcess.kill();
        } catch {
          // Best effort cleanup.
        }
      },
    };

    ptyProcess.onData((chunk) => this.logs.append(name, chunk));
    ptyProcess.onExit(({ exitCode, signal }) => {
      managed.running = false;
      this.logs.flush(name);
      this.appendSystemLog(
        `${name} exited with ${signal ? `signal ${signal}` : `code ${exitCode ?? "unknown"}`}.`,
      );
    });

    return managed;
  }

  appendSystemLog(message) {
    this.logs.push(`${nowIso()} [system] ${message}`);
  }

  buildNodeArgs(entryPath, extraArgs) {
    return ["--no-warnings", "--experimental-strip-types", entryPath, ...extraArgs];
  }

  spawnManagedProcess(name, args, cwd) {
    const child = spawn(process.execPath, args, {
      cwd,
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });

    child.stdout?.setEncoding("utf8");
    child.stderr?.setEncoding("utf8");
    child.stdout?.on("data", (chunk) => this.logs.append(name, chunk));
    child.stderr?.on("data", (chunk) => this.logs.append(name, chunk));
    child.once("exit", (code, signal) => {
      this.logs.flush(name);
      this.appendSystemLog(
        `${name} exited with ${signal ? `signal ${signal}` : `code ${code ?? "unknown"}`}.`,
      );
    });
    child.once("error", (error) => {
      this.appendSystemLog(`${name} failed to start: ${error.message}`);
    });
    return child;
  }

  spawnManagedPtyProcess(name, args, cwd) {
    const ptyProcess = spawnPty(process.execPath, args, {
      cwd,
      env: process.env,
      cols: 120,
      rows: 40,
      name: "xterm-color",
    });

    return this.createManagedPty(name, ptyProcess);
  }

  async waitForEndpoint(cwd, timeoutMs = 10_000) {
    const endpointFile = getWorkspaceEndpointFile(cwd);
    const deadline = Date.now() + timeoutMs;

    while (Date.now() < deadline) {
      const endpoint = readJson(endpointFile);
      if (endpoint?.kind === "codex" && endpoint?.cwd === cwd) {
        return endpoint;
      }
      if (this.bridge && !isChildRunning(this.bridge)) {
        throw new Error("Bridge process exited before endpoint was ready.");
      }
      await waitFor(250);
    }

    throw new Error(`Timed out waiting for bridge endpoint: ${endpointFile}`);
  }

  async start(config) {
    return this.enqueue(async () => {
      const cwd = path.resolve(config.cwd || DEFAULT_WORKSPACE);
      const profile = config.profile?.trim() || undefined;

      if (!path.isAbsolute(cwd)) {
        throw new Error("Workspace path must be absolute.");
      }
      if (!path.resolve(cwd)) {
        throw new Error("Invalid workspace path.");
      }
      if (!readJson(CREDENTIALS_FILE)) {
        throw new Error(`Missing WeChat credentials: ${CREDENTIALS_FILE}`);
      }

      try {
        ensureDir(cwd);
      } catch (error) {
        throw new Error(`Workspace is not writable or cannot be created: ${cwd}`);
      }

      if (
        this.current &&
        this.current.cwd === cwd &&
        this.current.profile === (profile || null) &&
        isChildRunning(this.bridge) &&
        isChildRunning(this.companion)
      ) {
        this.appendSystemLog(`Reusing running Codex bridge for ${cwd}.`);
        return this.getStatus();
      }

      await this.stopInternal();

      this.current = {
        cwd,
        profile: profile || null,
        startedAt: nowIso(),
      };

      const bridgeArgs = this.buildNodeArgs(
        path.join(this.projectDir, "src", "bridge", "wechat-bridge.ts"),
        [
          "--adapter",
          "codex",
          "--cwd",
          cwd,
          "--lifecycle",
          "companion_bound",
          ...(profile ? ["--profile", profile] : []),
        ],
      );

      this.appendSystemLog(`Starting bridge for ${cwd}...`);
      this.bridge = this.spawnManagedProcess("bridge", bridgeArgs, this.projectDir);
      await this.waitForEndpoint(cwd);

      const companionArgs = this.buildNodeArgs(
        path.join(this.projectDir, "src", "companion", "local-companion.ts"),
        [
          "--adapter",
          "codex",
          "--cwd",
          cwd,
        ],
      );

      this.appendSystemLog(`Starting companion for ${cwd}...`);
      this.companion = this.spawnManagedPtyProcess("companion", companionArgs, this.projectDir);

      await waitFor(1200);
      if (!isChildRunning(this.companion)) {
        throw new Error("Companion process exited immediately after startup.");
      }

      return this.getStatus();
    });
  }

  async stop() {
    return this.enqueue(async () => {
      await this.stopInternal();
      return this.getStatus();
    });
  }

  async stopInternal() {
    const bridge = this.bridge;
    const companion = this.companion;

    if (!bridge && !companion) {
      this.current = null;
      return;
    }

    this.appendSystemLog("Stopping Codex bridge session...");

    terminateChild(companion, false);
    await waitForExit(companion, 5000);
    terminateChild(companion, true);
    await waitForExit(companion, 2000);

    terminateChild(bridge, false);
    await waitForExit(bridge, 5000);
    terminateChild(bridge, true);
    await waitForExit(bridge, 2000);

    this.bridge = null;
    this.companion = null;
    this.current = null;
  }

  getStatus() {
    const cwd = this.current?.cwd || null;
    const endpoint = cwd ? readJson(getWorkspaceEndpointFile(cwd)) : null;
    return {
      running: isChildRunning(this.bridge) || isChildRunning(this.companion),
      ready: isChildRunning(this.bridge) && isChildRunning(this.companion) && Boolean(endpoint),
      bridgePid: isChildRunning(this.bridge) ? this.bridge?.pid || null : null,
      companionPid: isChildRunning(this.companion) ? this.companion?.pid || null : null,
      cwd,
      profile: this.current?.profile || null,
      startedAt: this.current?.startedAt || null,
      endpoint,
    };
  }

  getLogs(lines) {
    return this.logs.tail(lines);
  }

  enqueue(task) {
    const next = this.pending.then(task, task);
    this.pending = next.then(
      () => undefined,
      () => undefined,
    );
    return next;
  }
}
