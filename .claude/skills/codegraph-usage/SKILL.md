---
name: codegraph-usage
description: >
  本仓库的代码理解能力由两个工具组成：(1) `codegraph` CLI（已装好，1.2.0，本地知识图谱
  索引 .codegraph/，201 files / 6,139 nodes / 17,410 edges，覆盖 javascript/python/vue/yaml），
  用于"某符号在哪定义/谁调用它/它调用了谁/改动会影响什么/该跑哪些测试"这类结构性查询；
  (2) Understand Anything 插件（尚未安装，装好后提供 /understand /understand-dashboard
  /understand-chat /understand-diff /understand-explain /understand-domain /understand-onboard
  等命令），用于可视化看板、语义提问（"哪些部分处理身份验证"）、改动影响分析、业务领域提取、
  新人 onboarding 指南。当用户提出上述任一类问题，或要求"生成架构图/知识图谱/给新人写指南/
  解释这个功能是怎么运作的"时，使用此技能里的命令和决策规则。完整背景见
  docs/codegraph-usage-guide.md。
---

# 代码理解工具使用规则（项目级）

本仓库有两套互补的代码理解能力：**CodeGraph**（已装好，CLI，纯结构查询）和
**Understand Anything**（插件，尚未安装，可视化 + 语义化 + 业务领域）。
不要把两者当成同一个东西随便选一个用——它们解决的问题不完全重叠，见下面的决策表。

## 先看决策表：这个问题该用哪个

| 你要回答的问题 | 用哪个 | 具体命令 |
|---|---|---|
| X 在哪定义、是什么 kind | CodeGraph | `codegraph query <X> --json` → `codegraph node <X>` |
| 谁调用了 X / X 调用了谁 | CodeGraph | `codegraph callers <X> --json` / `codegraph callees <X> --json` |
| 改 X 会影响哪些代码/测试（精确、基于调用图） | CodeGraph | `codegraph impact <X> --depth 3` / `codegraph affected <file>` |
| 这次改动影响什么（模糊、结合语义判断） | Understand Anything | `/understand-diff` |
| "XX 功能/流程是怎么运作的"（自然语言提问） | Understand Anything | `/understand-chat <问题>` |
| 深入理解某一个具体文件 | Understand Anything | `/understand-explain <file>` |
| 要一张可交互的架构可视化图 | Understand Anything | `/understand-dashboard` |
| 把代码映射到业务领域/流程/步骤 | Understand Anything | `/understand-domain` |
| 给新同事写 onboarding 指南 | Understand Anything | `/understand-onboard` |
| 分析 Karpathy 模式的 wiki 知识库 | Understand Anything | `/understand-knowledge <path>` |
| 只是找一段字面文本（日志文案、注释、字符串常量） | 都不用 | `rg` |

**两者都能回答"改动影响什么"时的处理原则**：`codegraph impact`/`codegraph affected`
是基于确定性调用图算出来的，`understand-diff` 掺了语义判断，覆盖面可能更广但也可能有误判。
两个结论不一致时，**取交集做保守判断**，不要只信一边；如果 `understand-diff` 说了 CodeGraph
没提到的影响面，去 `codegraph callers`/`codegraph impact` 手动验证一下再采信。

---

## 一、CodeGraph（已装好）

本仓库根目录已执行过 `codegraph init .`，`.codegraph/` 是本机的知识图谱索引
（数据库/日志等临时文件已被 `.codegraph/.gitignore` 排除，不提交 Git）。

### 常用命令（本机 1.2.0 实测可用）

```powershell
# 索引维护
codegraph init .                 # 首次初始化（换机器/新 clone 后必做）
codegraph sync .                 # 增量同步（改完代码后执行）
codegraph index .                # 完整重建（索引损坏或版本升级后）
codegraph status --json          # 查看索引状态和 pendingChanges

# 结构查询
codegraph files                                    # 项目文件树
codegraph query <name> --kind function --json      # 搜索符号
codegraph node <symbol>                            # 符号源码 + 上下游 trail
codegraph callers <symbol> --json                  # 谁调用了它
codegraph callees <symbol> --json                  # 它调用了谁
codegraph impact <symbol> --depth 3                # 改动影响面
codegraph affected <changed-file>                  # 该文件改动后应关注哪些测试
codegraph explore "<自然语言问题或关键符号>"          # 按功能区域探索相关源码
```

### 推荐工作流

1. **改动前先问结构**：`codegraph explore "要改的功能 关键函数 关键文件"`
2. **定位符号**：`codegraph query <symbol> --json` → `codegraph node <symbol>`
3. **看调用关系**：`codegraph callers <symbol> --json` / `codegraph callees <symbol> --json`
4. **评估影响面**：`codegraph impact <symbol> --depth 3` / `codegraph affected <changed-file>`
5. **改完后同步索引**：`codegraph sync .` → `codegraph status --json`
6. **最后仍用单元测试/构建命令验证**——CodeGraph 只判断结构关系，不判断功能正确性。

### 边界与踩坑

- **没有 `codegraph context <symbol>` 命令**（本机 1.2.0 会报 `unknown command 'context'`）。
  想要"聚焦上下文"时用 `codegraph node <symbol>` 或 `codegraph explore "<query>"` 代替。
- **索引是本地缓存，不随 Git 走**。新 clone 或换机器后先跑 `codegraph init .`，
  否则所有查询命令都会失败或提示未初始化。
- **查询结果依赖索引新鲜度**。刚做过大量改动时先 `codegraph sync .` 再查，避免读到旧结构。
- CodeGraph 回答不了"为什么这么设计"——这类问题去看 git log/commit message 或直接问人。

---

## 二、Understand Anything（插件，尚未安装）

来源：[Egonex-AI/Understand-Anything](https://github.com/Egonex-AI/Understand-Anything/blob/main/READMEs/README.zh-CN.md)。
和 CodeGraph 同样是 tree-sitter（确定性语法解析）+ LLM（语义理解）混合方案，
但产出更偏"可视化 + 语义化 + 业务知识"，而不是纯结构查询。

### 安装（需要在真实终端里手动执行——这是 CLI 层命令，本技能调用不了）

```
/plugin marketplace add Egonex-AI/Understand-Anything
/plugin install understand-anything
```

其他平台（非 Claude Code）：一行脚本安装

```bash
# macOS/Linux
curl -fsSL https://raw.githubusercontent.com/Egonex-AI/Understand-Anything/main/install.sh | bash
# 指定平台，如 codex
curl -fsSL https://raw.githubusercontent.com/Egonex-AI/Understand-Anything/main/install.sh | bash -s codex
```

```powershell
# Windows
iwr -useb https://raw.githubusercontent.com/Egonex-AI/Understand-Anything/main/install.ps1 | iex
```

更新/卸载：`./install.sh --update`、`./install.sh --uninstall <platform>`。

### 命令参考

| 命令 | 用途 | 关键参数 | 输出 |
|---|---|---|---|
| `/understand [子目录]` | 分析代码库，构建知识图谱 | `--language en\|zh\|zh-TW\|ja\|ko\|ru`；`--auto-update`（装 post-commit 钩子自动增量更新） | `.understand-anything/knowledge-graph.json` |
| `/understand-dashboard` | 打开交互式网页看板 | 无 | 可搜索/平移/缩放/按架构层级分组着色的图谱界面 |
| `/understand-chat <问题>` | 用自然语言问代码库 | 问题文本，如 `How does the payment flow work?` | 对话式回答 |
| `/understand-explain <file>` | 深入解释某一个具体文件 | 文件路径 | 该文件的详细解读 |
| `/understand-diff` | 分析当前修改的影响面 | 无 | `.understand-anything/diff-overlay.json`（本地临时文件，不提交） |
| `/understand-domain` | 提取业务领域知识 | 无 | domain / 流程 / 步骤 的映射 |
| `/understand-onboard` | 给新团队成员生成入门指南 | 无 | 入门文档 |
| `/understand-knowledge <wiki路径>` | 分析 Karpathy 模式的 LLM Wiki 知识库 | Wiki 目录路径 | 力导向图 |

### 推荐工作流

1. **首次分析**：`/understand`（首次运行 token 消耗较大，之后默认增量式——只重新分析
   上次运行以来变更过的文件；想自动化就加 `--auto-update` 装 post-commit 钩子）
2. **可视化探索**：`/understand-dashboard` 看整体架构分组和依赖关系
3. **深度理解**：按需选一种——
   - 提问式："这个流程怎么运作的" → `/understand-chat <问题>`
   - 定点式：只想搞懂一个文件 → `/understand-explain <file>`
   - 业务式：想知道代码对应哪些业务流程 → `/understand-domain`
4. **改动前**：`/understand-diff` 看语义层面的影响面（和 CodeGraph 的
   `impact`/`affected` 交叉验证，见上面决策表）
5. **新人 onboarding**：`/understand-onboard` 一次性生成入门指南，不用每次口头讲一遍
6. **维护**：装了 `--auto-update` 就不用管；没装就在大改动后手动重跑 `/understand`

### 图谱文件与版本控制

- 知识图谱存在 `.understand-anything/knowledge-graph.json`，**官方建议提交进 Git**——
  这样团队成员 clone 仓库后可以直接用现成图谱，不用每人各自重新分析一遍
  （这点和 `.codegraph/` 每台机器本地建、明确不提交正好相反，两者的 `.gitignore` 策略不要搞混）
- **例外，不要提交**：`.understand-anything/intermediate/`（中间产物）和
  `diff-overlay.json`（`/understand-diff` 的本地临时结果）
- 图谱文件超过 10MB 时官方建议用 `git-lfs` 跟踪，避免仓库体积暴涨

### 边界与踩坑

- **首次 `/understand` token 消耗大**，是一次性成本；不要在同一次会话里反复跑全量分析，
  优先依赖增量更新（`--auto-update` 或改动后手动重跑一次）。
- **`/understand-diff` 的输出是本地临时文件**（`diff-overlay.json`），不要指望它能跨会话/
  跨机器复用，每次要看改动影响都要重新跑。
- **多语言输出靠 `--language` 参数控制**，不是自动跟随系统语言；本项目要中文输出时显式传
  `--language zh`。
- **支持本地模型**（如 Ollama）保护隐私——如果这个仓库有敏感业务逻辑不想经过外部 LLM，
  按官方集成指南把平台指向本地模型再跑 `/understand`。
- README 没有详细列出知识图谱 JSON 的具体字段结构，也没有单独的常见问题/已知限制章节——
  遇到边界情况以实际运行结果为准，不要假设它有 CodeGraph 那样的 `--json` 精确字段契约。
- **插件当前未安装**——在它实际装好之前，本节里的所有命令都不可用；如果用户提到
  "看板"/"语义搜索"/"业务领域"这类需求但插件还没装，先提醒用户去装，而不是假装命令已存在去执行。

## 详细背景

完整的原理说明、实测案例、优化建议见 [docs/codegraph-usage-guide.md](../../../docs/codegraph-usage-guide.md)。
