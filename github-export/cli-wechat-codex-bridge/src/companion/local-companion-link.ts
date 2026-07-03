import crypto from "node:crypto";
import fs from "node:fs";
import type net from "node:net";

import {
  ensureWorkspaceChannelDir,
  getWorkspaceChannelPaths,
} from "../wechat/channel-config.ts";
import type {
  BridgeAdapterKind,
  BridgeAdapterState,
  BridgeEvent,
} from "../bridge/bridge-types.ts";

export type LocalCompanionCommand =
  | { command: "send_input"; text: string }
  | { command: "list_resume_sessions"; limit?: number }
  | { command: "list_resume_threads"; limit?: number }
  | { command: "resume_session"; sessionId: string }
  | { command: "resume_thread"; threadId: string }
  | { command: "interrupt" }
  | { command: "reset" }
  | { command: "dispose" }
  | { command: "resolve_approval"; action: "confirm" | "deny" };

export type LocalCompanionCloseReason =
  | "bridge_dispose"
  | "companion_shutdown"
  | "fatal_error"
  | "signal"
  | "worker_exit";

export type LocalCompanionEndpoint = {
  instanceId: string;
  kind: BridgeAdapterKind;
  port: number;
  token: string;
  renderMode?: "embedded" | "panel" | "companion";
  bridgeOwnerPid?: number;
  serverPort?: number;
  serverUrl?: string;
  cwd: string;
  command: string;
  profile?: string;
  sharedSessionId?: string;
  sharedThreadId?: string;
  resumeConversationId?: string;
  transcriptPath?: string;
  startedAt: string;
};

export type LocalCompanionMessage =
  | {
      type: "hello";
      token: string;
      companionPid?: number;
      panelPid?: number;
    }
  | {
      type: "hello_ack";
    }
  | {
      type: "closing";
      reason: LocalCompanionCloseReason;
      exitCode?: number;
    }
  | {
      type: "request";
      id: string;
      payload: LocalCompanionCommand;
    }
  | {
      type: "response";
      id: string;
      ok: boolean;
      result?: unknown;
      error?: string;
    }
  | {
      type: "event";
      event: BridgeEvent;
    }
  | {
      type: "state";
      state: BridgeAdapterState;
    };

function normalizeEndpoint(value: unknown): LocalCompanionEndpoint | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }

  const record = value as Record<string, unknown>;
  const kind =
    record.kind === "codex" || record.kind === "claude" || record.kind === "opencode" || record.kind === "shell"
      ? record.kind
      : "codex";
  const sharedSessionId =
    typeof record.sharedSessionId === "string"
      ? record.sharedSessionId
      : typeof record.sharedThreadId === "string"
        ? record.sharedThreadId
        : undefined;

  if (
    typeof record.instanceId !== "string" ||
    typeof record.port !== "number" ||
    typeof record.token !== "string" ||
    typeof record.cwd !== "string" ||
    typeof record.command !== "string" ||
    typeof record.startedAt !== "string"
  ) {
    return null;
  }

  return {
    instanceId: record.instanceId,
    kind,
    port: record.port,
    token: record.token,
    renderMode:
      record.renderMode === "embedded" ||
      record.renderMode === "panel" ||
      record.renderMode === "companion"
        ? record.renderMode
        : undefined,
    bridgeOwnerPid:
      typeof record.bridgeOwnerPid === "number" ? record.bridgeOwnerPid : undefined,
    serverPort: typeof record.serverPort === "number" ? record.serverPort : undefined,
    serverUrl: typeof record.serverUrl === "string" ? record.serverUrl : undefined,
    cwd: record.cwd,
    command: record.command,
    profile: typeof record.profile === "string" ? record.profile : undefined,
    sharedSessionId,
    sharedThreadId:
      kind === "codex" || kind === "opencode"
        ? sharedSessionId
        : typeof record.sharedThreadId === "string"
          ? record.sharedThreadId
          : undefined,
    resumeConversationId:
      typeof record.resumeConversationId === "string" ? record.resumeConversationId : undefined,
    transcriptPath:
      typeof record.transcriptPath === "string" ? record.transcriptPath : undefined,
    startedAt: record.startedAt,
  };
}

export function buildLocalCompanionToken(): string {
  return crypto.randomBytes(18).toString("hex");
}

export function writeLocalCompanionEndpoint(endpoint: LocalCompanionEndpoint): void {
  const { endpointFile } = ensureWorkspaceChannelDir(endpoint.cwd);
  const payload: LocalCompanionEndpoint = {
    ...endpoint,
    sharedThreadId:
      endpoint.kind === "codex" || endpoint.kind === "opencode"
        ? endpoint.sharedSessionId ?? endpoint.sharedThreadId
        : undefined,
  };

  fs.writeFileSync(endpointFile, JSON.stringify(payload, null, 2), "utf8");
}

export function readLocalCompanionEndpoint(cwd: string): LocalCompanionEndpoint | null {
  try {
    const { endpointFile } = getWorkspaceChannelPaths(cwd);
    if (!fs.existsSync(endpointFile)) {
      return null;
    }
    return normalizeEndpoint(JSON.parse(fs.readFileSync(endpointFile, "utf8")));
  } catch {
    return null;
  }
}

export function clearLocalCompanionEndpoint(cwd: string, instanceId?: string): void {
  try {
    const { endpointFile } = getWorkspaceChannelPaths(cwd);
    if (!fs.existsSync(endpointFile)) {
      return;
    }

    if (!instanceId) {
      fs.rmSync(endpointFile, { force: true });
      return;
    }

    const endpoint = readLocalCompanionEndpoint(cwd);
    if (!endpoint || endpoint.instanceId === instanceId) {
      fs.rmSync(endpointFile, { force: true });
    }
  } catch {
    // Best effort cleanup.
  }
}

export function sendLocalCompanionMessage(
  socket: net.Socket,
  message: LocalCompanionMessage,
): boolean {
  if (socket.destroyed || socket.writableEnded) {
    return false;
  }

  try {
    return socket.write(`${JSON.stringify(message)}\n`);
  } catch {
    return false;
  }
}

export function attachLocalCompanionMessageListener(
  socket: net.Socket,
  onMessage: (message: LocalCompanionMessage) => void,
): () => void {
  let buffer = "";
  const onData = (chunk: string | Buffer) => {
    buffer += typeof chunk === "string" ? chunk : chunk.toString("utf8");

    while (true) {
      const newlineIndex = buffer.indexOf("\n");
      if (newlineIndex < 0) {
        return;
      }

      const line = buffer.slice(0, newlineIndex).trim();
      buffer = buffer.slice(newlineIndex + 1);
      if (!line) {
        continue;
      }

      try {
        onMessage(JSON.parse(line) as LocalCompanionMessage);
      } catch {
        // Ignore malformed local IPC frames.
      }
    }
  };

  socket.setEncoding("utf8");
  socket.on("data", onData);
  return () => {
    socket.off("data", onData);
  };
}
