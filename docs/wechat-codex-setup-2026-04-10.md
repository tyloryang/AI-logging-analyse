# 微信连接 Codex 实战部署指南

> 发布时间：2026-04-10  
> 部署环境：Windows  
> 实战项目目录：`D:\loki-log-analyse`  
> 适用对象：希望把本地 Codex 会话接入微信，实现远程收发消息和状态同步的开发者

---

## 一、这次做了什么

这次我把本地 `Codex CLI` 通过开源项目 **CLI-WeChat-Bridge** 接入到了微信，实现了下面这套能力：

- 本地继续使用原生 `codex`
- 微信作为远程入口，可以直接给本机 Codex 发消息
- 会话仍然以本地终端为主，不改变原有开发习惯
- 支持为当前项目目录独立启动桥接
- 补充了一键启动脚本，后续双击即可启动

本次使用的桥接项目：

```text
https://github.com/UNLINEARITY/CLI-WeChat-Bridge
```

---

## 二、适合什么场景

如果你有下面这些需求，这套方案会非常实用：

- 白天主要在本机终端里写代码
- 离开电脑后，希望继续通过微信给 Codex 发任务
- 不想切换到网页端，也不想改变原生 CLI 工作流
- 想把一个正在跑的本地项目和微信消息通道打通

简单理解就是：

> **本地终端仍然是主工作台，微信只是远程入口。**

---

## 三、环境前提

根据这次实际部署，至少需要准备以下环境：

- Windows 系统
- Node.js `>= 24`
- Bun `>= 1.0`
- 已安装 `Codex CLI`
- 本机可以正常访问微信扫码登录接口

这次本机环境已确认：

- Node.js：`v24.13.0`
- npm：`11.6.2`
- Codex CLI：`0.118.0`

---

## 四、部署步骤

### 1. 拉取桥接仓库

我把桥接项目拉到了当前仓库的 `tools` 目录下：

```bash
git clone https://github.com/UNLINEARITY/CLI-WeChat-Bridge .\tools\CLI-WeChat-Bridge
```

实际目录：

```text
D:\loki-log-analyse\tools\CLI-WeChat-Bridge
```

---

### 2. 安装依赖

在桥接仓库目录执行：

```bash
cmd /c npm.cmd install
```

这一步会把运行桥接所需依赖装完整。

---

### 3. 安装全局命令

为了后续能在任意项目目录直接启动桥接，这次采用的是：

```bash
cmd /c npm.cmd link
```

安装完成后，本机已经可用的命令包括：

```bash
wechat-bridge-codex
wechat-codex
wechat-codex-start
```

这意味着后面不需要每次都切回桥接项目目录。

---

### 4. 微信扫码登录

桥接项目需要先绑定微信账号。  
原始方式是运行：

```bash
npm run setup
```

但这次在实操里，终端二维码不够稳定，所以我直接取了二维码链接，用微信打开扫码完成授权。

扫码成功后，凭据会写入本机：

```text
C:\Users\可乐\.claude\channels\wechat\account.json
```

注意：

- 这个文件里包含登录凭据
- **不要发到公网**
- **不要提交到 Git**

---

## 五、启动方式

### 方案一：命令行直接启动

进入你要接入微信的项目目录，例如本次实际目录：

```bash
cd /d D:\loki-log-analyse
```

然后运行：

```bash
wechat-codex-start --cwd D:\loki-log-analyse
```

这个命令会自动完成以下动作：

1. 拉起或复用 `wechat-bridge-codex`
2. 等待当前项目目录对应的本地 endpoint 就绪
3. 打开可见的 Codex 会话窗口
4. 建立微信与当前本地 Codex 会话的桥接关系

---

### 方案二：双击一键启动脚本

为了方便日常使用，我额外补了一个一键启动脚本：

```text
D:\loki-log-analyse\一键启动微信-Codex.cmd
```

直接双击即可，或者在终端中运行：

```bash
.\一键启动微信-Codex.cmd
```

脚本逻辑很简单：

- 优先调用全局 `wechat-codex-start.cmd`
- 自动把当前项目目录作为 `--cwd`
- 如果本机没找到全局命令，则回退到已知安装路径

所以后续日常使用时，基本不需要再重复输入长命令。

---

## 六、这次实际验证结果

本次部署完成后，桥接已经成功启动，并生成了关键状态文件：

桥接锁文件：

```text
C:\Users\可乐\.claude\channels\wechat\bridge.lock.json
```

当前项目的 endpoint 文件：

```text
C:\Users\可乐\.claude\channels\wechat\workspaces\loki-log-analyse-dbdd2fe85052\codex-panel-endpoint.json
```

这说明两件事：

- 微信桥接主进程已经拉起
- 当前项目目录的 Codex endpoint 已可被桥接识别

也就是说，这套链路已经打通。

---

## 七、日常使用方法

启动成功后，使用方式非常直接：

### 本地侧

- 继续在 `Codex` 终端里正常工作
- 原有 CLI 使用习惯不变

### 微信侧

- 给桥接机器人发送文本消息
- 消息会转发到当前本地 Codex 会话
- 本地输出和状态会同步回微信

换句话说：

> 你本地开的不是“另一个 Codex”，而是“把当前 Codex 会话多开了一个微信入口”。

---

## 八、常见问题

### 1. 二维码扫不上怎么办？

这是这次实操里遇到的第一个问题。

解决方式：

- 不强依赖终端二维码
- 直接取二维码链接
- 在微信里打开链接后扫码确认

如果二维码过期，就重新生成一个新的二维码链接。

---

### 2. PowerShell 提示脚本被禁止执行怎么办？

这次也遇到了 PowerShell 执行策略限制，比如：

- `npm.ps1` 无法执行
- `bun.ps1` 无法执行
- `codex.ps1` 无法执行

解决方式不是改系统策略，而是直接走 `cmd`：

```bash
cmd /c npm.cmd install
cmd /c npm.cmd link
cmd /c codex --version
```

这样更稳，也更适合 Windows 环境下快速落地。

---

### 3. 已经启动过桥接，还需要重复启动吗？

不一定。

`wechat-codex-start` 会先检查当前目录是否已有可复用 bridge：

- 如果有，就复用
- 如果 bridge 正在服务别的目录，就替换
- 如果 endpoint 丢失，则重新等待就绪

所以它本身就是一个“适合日常使用”的入口。

---

## 九、推荐的最终工作流

如果你也准备这样用，我建议采用下面这套固定流程：

### 首次部署

```bash
git clone https://github.com/UNLINEARITY/CLI-WeChat-Bridge .\tools\CLI-WeChat-Bridge
cd .\tools\CLI-WeChat-Bridge
cmd /c npm.cmd install
cmd /c npm.cmd link
```

然后完成一次微信扫码登录。

### 后续日常启动

进入项目目录后，直接运行：

```bash
.\一键启动微信-Codex.cmd
```

或者：

```bash
wechat-codex-start --cwd 当前项目目录
```

这样基本就够用了。

---

## 十、总结

这次部署的核心价值，不是“把 Codex 搬到微信里”，而是：

- **保留原生 Codex CLI 工作流**
- **增加一个微信远程入口**
- **让本地开发和移动端协作自然连起来**

对于经常在本地终端里写代码、但又需要远程触达会话的人来说，这个方案非常实用。

如果你也在用 Codex，并且希望把微信接进来，这套方法是值得长期保留的。

---

## 附：本次实际使用到的关键路径

桥接仓库目录：

```text
D:\loki-log-analyse\tools\CLI-WeChat-Bridge
```

项目一键启动脚本：

```text
D:\loki-log-analyse\一键启动微信-Codex.cmd
```

微信桥接凭据：

```text
C:\Users\可乐\.claude\channels\wechat\account.json
```

桥接状态文件：

```text
C:\Users\可乐\.claude\channels\wechat\bridge.lock.json
```

当前项目 endpoint：

```text
C:\Users\可乐\.claude\channels\wechat\workspaces\loki-log-analyse-dbdd2fe85052\codex-panel-endpoint.json
```

---

如果你愿意，我下一步还可以继续帮你补一版：

- **更偏公众号排版风格的精简版**
- **适合朋友圈/知识星球的短版**
- **带标题党风格的发布版**
