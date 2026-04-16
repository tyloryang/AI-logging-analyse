# 微信接入 Claude Code 使用指南

通过 `weixin-acp` 工具，可以在微信中直接与 Claude Code 对话。

---

## 前提条件

- 已安装 [Claude Code CLI](https://claude.ai/code)
- 已安装 Node.js（支持 `npx`）
- 微信账号

---

## 一、启动 Bot

在系统终端运行：

```bash
npx weixin-acp claude-code
```

或在 Claude Code 聊天框中输入：

```
! npx weixin-acp claude-code
```

---

## 二、扫码登录

命令运行后，终端会显示二维码：

1. 打开微信 → 扫一扫，扫描终端中的二维码
2. 若二维码显示不清晰，复制输出中的链接在微信中打开：
   ```
   https://liteapp.weixin.qq.com/q/xxxxxx?qrcode=...&bot_type=3
   ```
3. 在微信中点击确认授权

> 二维码有效期约 30 秒，过期会自动刷新（最多 3 次），若全部过期请重新运行命令。

---

## 三、配对授权（首次使用）

Bot 启动后，需配对你的微信账号：

1. 在微信中向 Bot 发送任意消息
2. Bot 会回复一个 6 位配对码，例如：`A1B2C3`
3. 在 Claude Code 中运行：
   ```
   /weixin:access pair A1B2C3
   ```
4. 配对成功即可正常使用

---

## 四、重新登录

连接断开或 Token 失效时，在终端运行：

```bash
! npx weixin-acp claude-code --relogin
```

---

## 五、访问控制管理

### 查看当前状态

```
/weixin:access
```

### 常用命令

| 命令 | 说明 |
|------|------|
| `/weixin:access pair <code>` | 批准配对请求 |
| `/weixin:access deny <code>` | 拒绝配对请求 |
| `/weixin:access allow <userId>` | 直接添加用户到白名单 |
| `/weixin:access remove <userId>` | 从白名单移除用户 |
| `/weixin:access policy <mode>` | 设置访问策略（pairing / allowlist / disabled）|

---

## 六、常见问题

**Q: 二维码看不清楚？**
在系统终端直接运行 `npx weixin-acp claude-code`，或复制输出中的链接在微信中打开。

**Q: 提示"登录超时"？**
二维码 30 秒过期，重新运行命令即可。

**Q: 配对码在哪里？**
在微信中向 Bot 发消息，Bot 会自动回复配对码。
