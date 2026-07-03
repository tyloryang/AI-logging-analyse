import type { BridgeAdapterKind } from "./bridge-types.ts";
import {
  formatFinalReplyMessage,
  parseWechatFinalReply,
  sanitizeWechatFinalReplyText,
} from "./bridge-utils.ts";

export type WechatFinalReplySender = {
  sendText: (text: string) => Promise<void>;
  sendImage: (imagePath: string) => Promise<unknown>;
  sendFile: (filePath: string) => Promise<unknown>;
  sendVoice: (voicePath: string) => Promise<unknown>;
  sendVideo: (videoPath: string) => Promise<unknown>;
};

export async function forwardWechatFinalReply(params: {
  adapter: BridgeAdapterKind;
  rawText: string;
  sender: WechatFinalReplySender;
}): Promise<void> {
  const { adapter, rawText, sender } = params;
  const parsed = parseWechatFinalReply(rawText);
  const visibleText = formatFinalReplyMessage(
    adapter,
    sanitizeWechatFinalReplyText(adapter, parsed.visibleText),
  ).trim();

  if (visibleText) {
    await sender.sendText(visibleText);
  }

  for (const attachment of parsed.attachments) {
    try {
      switch (attachment.kind) {
        case "image":
          await sender.sendImage(attachment.path);
          break;
        case "file":
          await sender.sendFile(attachment.path);
          break;
        case "voice":
          await sender.sendVoice(attachment.path);
          break;
        case "video":
          await sender.sendVideo(attachment.path);
          break;
      }
    } catch (error) {
      const errorText =
        error instanceof Error ? error.message : String(error ?? "unknown error");
      await sender.sendText(
        `Failed to send ${attachment.kind} attachment: ${attachment.path}\n${errorText}`,
      );
    }
  }
}
