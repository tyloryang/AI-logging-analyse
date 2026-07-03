#!/usr/bin/env bun

import net from "node:net";
import path from "node:path";

import { createBridgeAdapter } from "../bridge/bridge-adapters.ts";
import {
  attachCodexPanelMessageListener,
  readCodexPanelEndpoint,
  sendCodexPanelMessage,
  type CodexPanelMessage,
} from "./codex-panel-link.ts";
import { migrateLegacyChannelFiles } from "../wechat/channel-config.ts";

function log(message: string): void {
  process.stderr.write(`[codex-panel] ${message}\n`);
}

type CodexPanelCliOptions = {
  cwd: string;
};

function parseCliArgs(argv: string[]): CodexPanelCliOptions {
  let cwd = process.cwd();

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = argv[i + 1];

    if (arg === "--help" || arg === "-h") {
      process.stdout.write(
        [
          "Usage: wechat-codex [--cwd <path>]",
          "",
          'Starts the visible Codex panel and connects it to the running "wechat-bridge-codex" instance for the current directory.',
          "",
        ].join("\n"),
      );
      process.exit(0);
    }

    if (arg === "--cwd") {
      if (!next) {
        throw new Error("--cwd requires a value");
      }
      cwd = path.resolve(next);
      i += 1;
      continue;
    }

    throw new Error(`Unknown argument: ${arg}`);
  }

  return { cwd };
}

async function main(): Promise<void> {
  migrateLegacyChannelFiles(log);
  const options = parseCliArgs(process.argv.slice(2));

  const endpoint = readCodexPanelEndpoint(options.cwd);
  if (!endpoint) {
    throw new Error(
      `No active Codex bridge endpoint was found for ${options.cwd}. Start "wechat-bridge-codex" in that directory first.`,
    );
  }

  const socket = await new Promise<net.Socket>((resolve, reject) => {
    const nextSocket = net.connect({
      host: "127.0.0.1",
      port: endpoint.port,
    });

    nextSocket.once("connect", () => resolve(nextSocket));
    nextSocket.once("error", (error) => reject(error));
  });

  socket.setNoDelay(true);

  const adapter = createBridgeAdapter({
    kind: "codex",
    command: endpoint.command,
    cwd: endpoint.cwd,
    profile: endpoint.profile,
    initialSharedThreadId: endpoint.sharedThreadId,
    renderMode: "panel",
  });

  let shuttingDown = false;
  let helloAcknowledged = false;
  let detachListener: (() => void) | null = null;

  const publishState = () => {
    sendCodexPanelMessage(socket, {
      type: "state",
      state: adapter.getState(),
    });
  };

  const sendResponse = (id: string, ok: boolean, result?: unknown, error?: string) => {
    sendCodexPanelMessage(socket, {
      type: "response",
      id,
      ok,
      result,
      error,
    });
  };

  const closePanel = async (exitCode = 0) => {
    if (shuttingDown) {
      return;
    }
    shuttingDown = true;

    detachListener?.();
    detachListener = null;
    try {
      await adapter.dispose();
    } catch {
      // Best effort cleanup.
    }
    try {
      socket.end();
      socket.destroy();
    } catch {
      // Best effort cleanup.
    }
    process.exit(exitCode);
  };

  adapter.setEventSink((event) => {
    sendCodexPanelMessage(socket, {
      type: "event",
      event,
    });
    publishState();
  });

  detachListener = attachCodexPanelMessageListener(socket, (message: CodexPanelMessage) => {
    if (!helloAcknowledged) {
      if (message.type === "hello_ack") {
        helloAcknowledged = true;
      }
      return;
    }

    if (message.type !== "request") {
      return;
    }

    void (async () => {
      try {
        switch (message.payload.command) {
          case "send_input":
            await adapter.sendInput(message.payload.text);
            sendResponse(message.id, true);
            break;
          case "list_resume_sessions":
          case "list_resume_threads":
            sendResponse(
              message.id,
              true,
              await adapter.listResumeSessions(message.payload.limit),
            );
            break;
          case "resume_session":
            await adapter.resumeSession(message.payload.sessionId);
            publishState();
            sendResponse(message.id, true);
            break;
          case "resume_thread":
            await adapter.resumeSession(message.payload.threadId);
            publishState();
            sendResponse(message.id, true);
            break;
          case "interrupt":
            sendResponse(message.id, true, await adapter.interrupt());
            break;
          case "reset":
            await adapter.reset();
            publishState();
            sendResponse(message.id, true);
            break;
          case "resolve_approval":
            sendResponse(
              message.id,
              true,
              await adapter.resolveApproval(message.payload.action),
            );
            break;
          case "dispose":
            sendResponse(message.id, true);
            await closePanel(0);
            break;
        }
      } catch (error) {
        const text = error instanceof Error ? error.message : String(error);
        sendResponse(message.id, false, undefined, text);
      }
    })();
  });

  socket.once("close", () => {
    void closePanel(0);
  });
  socket.once("error", () => {
    void closePanel(1);
  });

  sendCodexPanelMessage(socket, {
    type: "hello",
    token: endpoint.token,
    panelPid: process.pid,
  });

  await adapter.start();
  publishState();
  log(`Connected to bridge ${endpoint.instanceId}.`);
}

main().catch((error) => {
  log(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
