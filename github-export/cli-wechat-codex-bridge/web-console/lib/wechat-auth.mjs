import fs from "node:fs";

import {
  CHANNEL_DATA_DIR,
  CREDENTIALS_FILE,
  DEFAULT_BASE_URL,
  ensureDir,
  getCredentialSummary,
  nowIso,
} from "./shared.mjs";

export async function fetchQrCode(baseUrl = DEFAULT_BASE_URL) {
  const base = baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`;
  const url = `${base}ilink/bot/get_bot_qrcode?bot_type=3`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`QR fetch failed: HTTP ${response.status}`);
  }
  return await response.json();
}

export async function fetchQrStatus(baseUrl, qrcode) {
  const base = baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`;
  const url = `${base}ilink/bot/get_qrcode_status?qrcode=${encodeURIComponent(qrcode)}`;
  const response = await fetch(url, {
    headers: {
      "iLink-App-ClientVersion": "1",
    },
  });
  if (!response.ok) {
    throw new Error(`QR status failed: HTTP ${response.status}`);
  }
  return await response.json();
}

export function persistConfirmedAccount(baseUrl, statusPayload) {
  ensureDir(CHANNEL_DATA_DIR);
  const account = {
    token: statusPayload.bot_token,
    baseUrl: statusPayload.baseurl || baseUrl,
    accountId: statusPayload.ilink_bot_id,
    userId: statusPayload.ilink_user_id,
    savedAt: nowIso(),
  };
  fs.writeFileSync(CREDENTIALS_FILE, JSON.stringify(account, null, 2), "utf8");
  try {
    fs.chmodSync(CREDENTIALS_FILE, 0o600);
  } catch {
    // Best effort.
  }
  return getCredentialSummary();
}
