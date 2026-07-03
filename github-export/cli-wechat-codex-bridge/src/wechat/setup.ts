#!/usr/bin/env bun
/**
 * CLI WeChat Bridge setup.
 *
 * Run this before starting CLI WeChat Bridge:
 *   bun run setup
 */

import fs from "node:fs";
import readline from "node:readline";

import {
  BOT_TYPE,
  CREDENTIALS_FILE,
  DEFAULT_BASE_URL,
  ensureChannelDataDir,
  migrateLegacyChannelFiles,
} from "./channel-config.ts";

interface QRCodeResponse {
  qrcode: string;
  qrcode_img_content: string;
}

interface QRStatusResponse {
  status: "wait" | "scaned" | "confirmed" | "expired";
  bot_token?: string;
  ilink_bot_id?: string;
  baseurl?: string;
  ilink_user_id?: string;
}

type StoredAccount = {
  token: string;
  baseUrl: string;
  accountId: string;
  userId?: string;
  savedAt: string;
};

function loadExistingCredentials(): StoredAccount | null {
  try {
    if (!fs.existsSync(CREDENTIALS_FILE)) {
      return null;
    }
    return JSON.parse(fs.readFileSync(CREDENTIALS_FILE, "utf-8")) as StoredAccount;
  } catch {
    return null;
  }
}

async function fetchQRCode(baseUrl: string): Promise<QRCodeResponse> {
  const base = baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`;
  const url = `${base}ilink/bot/get_bot_qrcode?bot_type=${BOT_TYPE}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`QR fetch failed: ${res.status}`);
  }
  return (await res.json()) as QRCodeResponse;
}

async function pollQRStatus(
  baseUrl: string,
  qrcode: string,
): Promise<QRStatusResponse> {
  const base = baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`;
  const url = `${base}ilink/bot/get_qrcode_status?qrcode=${encodeURIComponent(qrcode)}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 35_000);

  try {
    const res = await fetch(url, {
      headers: { "iLink-App-ClientVersion": "1" },
      signal: controller.signal,
    });
    clearTimeout(timer);
    if (!res.ok) {
      throw new Error(`QR status failed: ${res.status}`);
    }
    return (await res.json()) as QRStatusResponse;
  } catch (err) {
    clearTimeout(timer);
    if (err instanceof Error && err.name === "AbortError") {
      return { status: "wait" };
    }
    throw err;
  }
}

async function askYesNo(prompt: string): Promise<boolean> {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  try {
    const answer = await new Promise<string>((resolve) => {
      rl.question(prompt, resolve);
    });
    return answer.trim().toLowerCase() === "y";
  } finally {
    rl.close();
  }
}

async function printQRCode(qrContent: string): Promise<void> {
  try {
    const qrterm = await import("qrcode-terminal");
    await new Promise<void>((resolve) => {
      qrterm.default.generate(qrContent, { small: true }, (qr: string) => {
        console.log(qr);
        resolve();
      });
    });
  } catch {
    console.log(`Open this QR code URL in a browser: ${qrContent}\n`);
  }
}

async function main() {
  migrateLegacyChannelFiles((message) => console.log(message));

  const existing = loadExistingCredentials();
  if (existing) {
    console.log(`Found saved account: ${existing.accountId}`);
    console.log(`Saved at: ${existing.savedAt}`);
    console.log(`Credentials file: ${CREDENTIALS_FILE}`);
    console.log();

    const shouldRelogin = await askYesNo("Log in again? (y/N) ");
    if (!shouldRelogin) {
      console.log("Keeping existing credentials.");
      return;
    }
  }

  console.log("Fetching WeChat login QR code...\n");
  const qrResp = await fetchQRCode(DEFAULT_BASE_URL);
  await printQRCode(qrResp.qrcode_img_content);

  console.log("Scan the QR code in WeChat, then confirm on your phone.\n");

  const deadline = Date.now() + 480_000;
  let scannedPrinted = false;

  while (Date.now() < deadline) {
    const status = await pollQRStatus(DEFAULT_BASE_URL, qrResp.qrcode);

    switch (status.status) {
      case "wait":
        process.stdout.write(".");
        break;
      case "scaned":
        if (!scannedPrinted) {
          console.log("\nQR code scanned. Confirm the login in WeChat...");
          scannedPrinted = true;
        }
        break;
      case "expired":
        console.log("\nThe QR code expired. Run setup again.");
        process.exit(1);
        break;
      case "confirmed": {
        if (!status.ilink_bot_id || !status.bot_token) {
          console.error("\nLogin failed: missing bot credentials from server.");
          process.exit(1);
        }

        const account: StoredAccount = {
          token: status.bot_token,
          baseUrl: status.baseurl || DEFAULT_BASE_URL,
          accountId: status.ilink_bot_id,
          userId: status.ilink_user_id,
          savedAt: new Date().toISOString(),
        };

        ensureChannelDataDir();
        fs.writeFileSync(CREDENTIALS_FILE, JSON.stringify(account, null, 2), "utf-8");
        try {
          fs.chmodSync(CREDENTIALS_FILE, 0o600);
        } catch {
          // Best effort on Windows.
        }

        console.log("\nWeChat login completed.");
        console.log(`Account ID: ${account.accountId}`);
        console.log(`User ID: ${account.userId ?? "(unknown)"}`);
        console.log(`Credentials saved to: ${CREDENTIALS_FILE}`);
        console.log();
        console.log("No /pair step is required.");
        console.log("The logged-in WeChat account above becomes the only authorized bridge owner.");
        console.log();
        console.log("After installing the package globally (for example: npm install -g . or npm link),");
        console.log("start the WeChat bridge from any directory with:");
        console.log("  wechat-bridge-codex");
        console.log("  wechat-codex         # start this in a second terminal in the same directory");
        console.log("  wechat-bridge-opencode");
        console.log("  wechat-opencode      # start this in a second terminal in the same directory");
        console.log("  wechat-bridge-claude");
        console.log("  wechat-claude        # start this in a second terminal in the same directory");
        console.log("  wechat-bridge-shell");
        console.log("  On Linux/macOS, wechat-bridge-shell defaults to pwsh, then bash, zsh, or sh.");
        console.log("  Shell mode is a headless remote executor for non-interactive commands and scripts.");
        console.log();
        console.log("Repo-local development entrypoints are still available:");
        console.log("  bun run bridge:codex");
        console.log("  bun run codex:panel");
        console.log("  bun run bridge:opencode");
        console.log("  bun run opencode:panel");
        console.log("  bun run opencode:start");
        console.log("  bun run bridge:claude");
        console.log("  bun run claude:companion");
        console.log("  bun run bridge:shell");
        console.log();
        console.log("Legacy MCP server entrypoint:");
        console.log("  bun run start");
        return;
      }
    }

    await new Promise((resolve) => setTimeout(resolve, 1000));
  }

  console.log("\nLogin timed out. Run setup again.");
  process.exit(1);
}

main().catch((err) => {
  const message = err instanceof Error ? err.message : String(err);
  console.error(`Error: ${message}`);
  process.exit(1);
});
