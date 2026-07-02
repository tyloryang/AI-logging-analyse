"""Jenkins CI/CD 工具（9 个）。"""
from __future__ import annotations

from datetime import datetime

from langchain_core.tools import tool

from ._shared import _jenkins_client


@tool
async def jenkins_get_all_jobs() -> str:
    """获取 Jenkins 所有 Job 列表，包含最近构建状态。"""
    client, err = _jenkins_client()
    if err:
        return err
    try:
        jobs = await client.get_all_jobs()
        if not jobs:
            return "Jenkins 中没有找到任何 Job"
        lines = [f"**Jenkins Job 列表（共 {len(jobs)} 个）**\n"]
        for j in jobs[:50]:
            color = j.get("color", "")
            status = {"blue": "✅成功", "red": "❌失败", "yellow": "⚠️不稳定", "notbuilt": "⭕未构建", "aborted": "⏹已中止"}.get(color, color)
            lb = j.get("lastBuild") or {}
            build_info = f"#{lb.get('number', '-')} {lb.get('result', '-')}" if lb else "无构建"
            lines.append(f"- **{j['name']}** {status} | 最近构建: {build_info}")
        if len(jobs) > 50:
            lines.append(f"\n... 共 {len(jobs)} 个 Job，仅展示前 50 个")
        return "\n".join(lines)
    except Exception as e:
        return f"获取 Job 列表失败：{e}"


@tool
async def jenkins_search_jobs(query: str) -> str:
    """按关键字搜索 Jenkins Job。query=搜索关键字（必填）。"""
    client, err = _jenkins_client()
    if err:
        return err
    try:
        jobs = await client.search_jobs(query)
        if not jobs:
            return f"未找到包含「{query}」的 Job"
        lines = [f"**搜索「{query}」结果（{len(jobs)} 个）**\n"]
        for j in jobs:
            lb = j.get("lastBuild") or {}
            lines.append(f"- **{j['name']}** | 最近构建: #{lb.get('number', '-')} {lb.get('result', '-')}")
        return "\n".join(lines)
    except Exception as e:
        return f"搜索失败：{e}"


@tool
async def jenkins_build_job(job: str, params: str = "") -> str:
    """触发 Jenkins Job 构建。
    job=Job名称（必填）。
    params=构建参数，格式为 JSON 字符串如 '{"BRANCH":"main","ENV":"prod"}'（可选）。"""
    client, err = _jenkins_client()
    if err:
        return err
    try:
        parsed_params = None
        if params.strip():
            import json
            parsed_params = json.loads(params)
        queue_id = await client.build_job(job, parsed_params)
        return f"✅ 已触发 Job **{job}** 构建，队列 ID: {queue_id}。可稍后用 jenkins_get_build_info 查询构建结果。"
    except Exception as e:
        return f"触发构建失败：{e}"


@tool
async def jenkins_get_build_info(job: str, build: str = "lastBuild") -> str:
    """获取 Jenkins Job 构建信息。
    job=Job名称（必填）。build=构建号，如 42 或 lastBuild（默认最新）。"""
    client, err = _jenkins_client()
    if err:
        return err
    try:
        info = await client.get_build_info(job, build)
        result = info.get("result") or "进行中"
        duration_s = info.get("duration", 0) // 1000
        ts = info.get("timestamp", 0) // 1000
        dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else "-"
        url = info.get("url", "")
        lines = [
            f"**{job} #{info.get('number', build)} 构建信息**",
            f"- 结果：{'✅ 成功' if result=='SUCCESS' else ('❌ 失败' if result=='FAILURE' else result)}",
            f"- 耗时：{duration_s}s",
            f"- 触发时间：{dt}",
            f"- 链接：{url}",
        ]
        causes = [c.get("shortDescription", "") for a in info.get("actions", []) for c in a.get("causes", []) if a.get("causes")]
        if causes:
            lines.append(f"- 触发原因：{'; '.join(causes)}")
        return "\n".join(lines)
    except Exception as e:
        return f"获取构建信息失败：{e}"


@tool
async def jenkins_get_build_logs(job: str, build: str = "lastBuild", lines: int = 100) -> str:
    """获取 Jenkins 构建日志。
    job=Job名称（必填）。build=构建号或 lastBuild（默认最新）。lines=返回行数（默认100）。"""
    client, err = _jenkins_client()
    if err:
        return err
    try:
        log = await client.get_build_logs(job, build, lines)
        return f"**{job} #{build} 日志（末尾 {lines} 行）**\n\n```\n{log}\n```"
    except Exception as e:
        return f"获取日志失败：{e}"


@tool
async def jenkins_get_running_builds() -> str:
    """获取 Jenkins 当前正在运行的所有构建。"""
    client, err = _jenkins_client()
    if err:
        return err
    try:
        builds = await client.get_running_builds()
        if not builds:
            return "当前没有正在运行的构建"
        lines = [f"**正在运行的构建（{len(builds)} 个）**\n"]
        for b in builds:
            eta = b.get("estimatedDuration", 0) // 1000
            lines.append(f"- **{b.get('job', '-')}** #{b.get('number', '-')} | 预估剩余 {eta}s")
        return "\n".join(lines)
    except Exception as e:
        return f"获取运行中构建失败：{e}"


@tool
async def jenkins_get_queue() -> str:
    """获取 Jenkins 构建队列（等待构建的任务）。"""
    client, err = _jenkins_client()
    if err:
        return err
    try:
        items = await client.get_queue_items()
        if not items:
            return "构建队列为空"
        lines = [f"**构建队列（{len(items)} 个）**\n"]
        for item in items:
            task = item.get("task", {})
            lines.append(f"- 队列 ID: {item.get('id')} | Job: {task.get('name', '-')} | 原因: {item.get('why', '-')}")
        return "\n".join(lines)
    except Exception as e:
        return f"获取队列失败：{e}"


@tool
async def jenkins_cancel_queue_item(queue_id: int) -> str:
    """取消 Jenkins 队列中等待的构建。queue_id=队列 ID（必填，从 jenkins_get_queue 中获取）。"""
    client, err = _jenkins_client()
    if err:
        return err
    try:
        ok = await client.cancel_queue_item(queue_id)
        return f"{'✅ 已取消' if ok else '❌ 取消失败'} 队列 ID {queue_id} 的构建"
    except Exception as e:
        return f"取消失败：{e}"


@tool
async def jenkins_get_test_results(job: str, build: str = "lastBuild") -> str:
    """获取 Jenkins 构建的测试报告（需要 JUnit/TestNG 插件）。
    job=Job名称（必填）。build=构建号或 lastBuild（默认最新）。"""
    client, err = _jenkins_client()
    if err:
        return err
    try:
        result = await client.get_test_results(job, build)
        total = result.get("totalCount", 0)
        failed = result.get("failCount", 0)
        skipped = result.get("skipCount", 0)
        passed = total - failed - skipped
        lines = [
            f"**{job} #{build} 测试报告**",
            f"- 总计：{total} | ✅通过：{passed} | ❌失败：{failed} | ⏭跳过：{skipped}",
        ]
        if failed > 0:
            fail_cases = [s for s in result.get("suites", []) for c in s.get("cases", []) if c.get("status") in ("FAILED", "REGRESSION")]
            for c in fail_cases[:5]:
                lines.append(f"  ❌ {c.get('className', '')}.{c.get('name', '')}")
            if len(fail_cases) > 5:
                lines.append(f"  ... 共 {len(fail_cases)} 个失败用例")
        return "\n".join(lines)
    except Exception as e:
        return f"获取测试报告失败（可能该构建无测试报告）：{e}"


# ── 高层复合工具：一次调用完成『排查失败 → 诊断日志 → 精准恢复』 ─────────────
# AI 遇到「Jenkins 有哪些失败任务 / 为什么挂了 / 怎么修」类问题时，优先走这 3 个。

# ── 根因识别规则（v2：25 类别 + 优先级 + 建议下一步调用哪些工具） ─────────────
# 字段：(pattern, kind, priority, title, advice, follow_up_tools)
# priority：分数越高越"根本"（编译错 > 网络抖 > 中止）；命中多个时高分先
# follow_up_tools：AI 该继续调的原子工具名称提示（跨模块联动）
_ERROR_PATTERNS = [
    # ── 编译/构建（priority=9，最根本） ─────────────────────────────
    (r"(?i)compilation failed|BUILD FAILED|error: (cannot find symbol|package .* does not exist)",
     "compile", 9, "代码编译失败",
     "检查代码语法 / 依赖版本；查看提交历史找到引入错误的 commit 后修复或回滚", []),
    (r"(?i)npm ERR!|yarn error|ELIFECYCLE|error Command failed with exit code",
     "npm_build", 9, "Node.js 构建失败",
     "对齐 package-lock.json 与 node 版本；检查依赖是否已发布；必要时 npm cache clean --force", []),
    (r"(?i)ImportError|ModuleNotFoundError|(python\.egg-info.*failed)|error: subprocess-exited-with-error",
     "python_dep", 9, "Python 依赖缺失/构建失败",
     "校对 requirements.txt / pyproject.toml；确认虚拟环境激活；网络能通 PyPI 镜像", []),
    (r"(?i)Could not resolve dependencies|Failed to collect dependencies|no valid.*artifact|Could not find artifact",
     "maven_dep", 9, "Maven/Gradle 依赖解析失败",
     "检查私服连接 / settings.xml；跑一次 mvn -U 强制刷新；核对 pom.xml 版本号", []),
    (r"(?i)go: cannot find module|go: module .* not found|go build.*failed|package .* is not in GOROOT",
     "go_build", 9, "Go 构建失败",
     "go mod tidy 后重跑；检查 GOPROXY；确认 go.mod 里的 replace 指令未失效", []),
    (r"(?i)error\[E\d+\]:|cargo build.*failed|could not compile.*because|error: could not find",
     "rust_build", 9, "Rust 构建失败",
     "cargo clean && cargo build 重跑；核对 Cargo.toml 里的 features 与 edition", []),
    # ── 容器镜像/仓库（priority=8） ─────────────────────────────
    (r"(?i)ImagePullBackOff|ErrImagePull|manifest unknown|denied.*docker|pull access denied",
     "image_pull", 8, "镜像拉取失败",
     "检查镜像 tag 是否已推送 / imagePullSecret / 仓库地址；重跑推送再触发",
     ["get_k8s_events", "get_k8s_pods"]),
    (r"(?i)failed to push|denied: requested access to the resource is denied|error: unauthorized: access denied",
     "image_push", 8, "镜像推送失败",
     "检查 registry 登录凭证 / repo push 权限；确认 tag 命名规范符合仓库策略", []),
    (r"(?i)(kaniko|buildah).*(error|failed|unable)|error building image|docker build.*(error|failed)|Step \d+/\d+ : .*\n.*error",
     "docker_build", 8, "Docker/Kaniko 镜像构建失败",
     "Dockerfile 每行前置查错；确认 base image 存在；build context 大小是否超限", []),
    # ── K8s 部署（priority=8） ─────────────────────────────
    (r"(?i)kubectl.*(error|refused|forbidden)|The connection to the server .* was refused",
     "k8s_conn", 8, "K8s API 不可达",
     "kubectl cluster-info 检查连通；kubeconfig token 是否过期",
     ["get_k8s_events"]),
    (r"(?i)deploy.*timed?[- ]?out|rollout.*progressing|readiness probe failed|liveness probe failed",
     "deploy_timeout", 8, "部署超时（探针未就绪）",
     "看 Pod events / readinessProbe 配置；应用启动慢考虑扩 timeout",
     ["get_k8s_events", "get_k8s_pods"]),
    (r"(?i)helm.*(error|failed)|Error: UPGRADE FAILED|release.*not found",
     "helm", 8, "Helm 部署失败",
     "helm status / helm history 看上一次成功版本；必要时 rollback",
     ["get_k8s_events"]),
    # ── 测试 & 质量门禁（priority=7） ─────────────────────────────
    (r"(?i)Tests? run: \d+, (Failures|Errors): [1-9]|assertion.*failed|junit.*failure|jest.*failed",
     "test", 7, "单元测试挂了",
     "调 jenkins_get_test_results 查具体失败用例；本地复现后修 assertion / mock",
     ["jenkins_get_test_results"]),
    (r"(?i)e2e.*failed|cypress.*failed|playwright.*failed|selenium.*(exception|timeout)",
     "e2e", 7, "端到端测试失败",
     "查测试报告截图和 trace；用例可能对环境敏感，检查测试环境稳定性",
     ["jenkins_get_test_results"]),
    (r"(?i)sonar.*quality gate.*failed|coverage.*below|violations found",
     "quality_gate", 7, "SonarQube 质量门禁未过",
     "看 Sonar 报告；补充测试覆盖率 / 修复代码 smell；或临时改分支的门禁阈值", []),
    # ── SCM（priority=7） ─────────────────────────────
    (r"(?i)Could not read from remote repository|GitException|Repository not found|fatal:.*ssh|Host key verification failed",
     "git", 7, "Git 拉代码失败",
     "检查 credentials / branch 是否存在 / 代理设置；known_hosts 是否有目标 host key", []),
    # ── 基础设施（priority=6） ─────────────────────────────
    (r"(?i)connection refused|no route to host|network is unreachable|dns.*(fail|timeout)",
     "network", 6, "网络不通",
     "从 Jenkins 节点 telnet / curl 目标 → 排查防火墙 / DNS / VPN", []),
    (r"(?i)OutOfMemoryError|Killed process|OOMKilled|Cannot allocate memory|out of memory",
     "oom", 6, "内存不足 / OOM",
     "调大 JVM -Xmx / Pod resources.limits.memory；或找内存泄漏",
     ["get_k8s_events"]),
    (r"(?i)No space left on device|disk.*full|inode.*used up|Not enough disk space",
     "disk", 6, "磁盘/inode 打满",
     "df -h + du -sh 找大目录清理；构建缓存可 clean workspace", []),
    (r"(?i)Permission denied|EACCES|Access is denied|forbidden \(403\)|401 Unauthorized",
     "perm", 6, "权限不足",
     "检查执行用户 / SSH key / API Token / K8s RBAC", []),
    # ── 通知类（priority=4，非阻断） ─────────────────────────────
    (r"(?i)slack.*(fail|error)|feishu.*(fail|error)|webhook.*(fail|400|500)",
     "notify", 4, "通知发送失败",
     "非核心错误，检查通知机器人 URL/Token；构建本身可能已成功", []),
    # ── 基础设施上传（priority=5） ─────────────────────────────
    (r"(?i)Nexus.*(fail|401|403)|Artifactory.*(fail|401|403)|Failed to deploy artifacts",
     "nexus_up", 5, "私服上传失败",
     "检查 deploy 凭证；确认 GAV 未重复；私服磁盘/quota 是否够", []),
    # ── Jenkins 自身 / Pipeline 脚本（priority=5） ─────────────────
    (r"(?i)Jenkins is (going )?to shut down|slave.*disconnected|node.*offline|Node .* is offline",
     "jenkins_infra", 5, "Jenkins 节点/执行器异常",
     "看节点状态；必要时重启 agent 或分配到其它 label", []),
    (r"(?i)WorkflowScript.*error|groovy\.lang\..*Exception|Jenkinsfile.*(syntax|error)",
     "pipeline_syntax", 5, "Pipeline 脚本语法错",
     "Jenkinsfile 里的 Groovy 语法有问题；用 Replay 定位失败行", []),
    # ── IaC（priority=5） ─────────────────────────────
    (r"(?i)ansible.*fail|fatal:.*FAILED!|TASK .* failed|Play recap.*(unreachable|failed)",
     "ansible", 5, "Ansible 任务失败",
     "看 msg / stderr；检查 inventory 主机可达；vault password 是否正确", []),
    (r"(?i)terraform.*error|Error: .*terraform|Refreshing state.*failed",
     "terraform", 5, "Terraform 执行失败",
     "看 tfstate 与实际资源是否 drift；plan 重跑；必要时手动 taint 资源", []),
    # ── 超时（priority=3，最"表象"） ─────────────────────────────
    (r"(?i)aborted.*took .* > .*|timed? out after|Build step .* marked build as failure|took longer than",
     "abort_timeout", 3, "构建被中止/超时",
     "看是否有人手动中止；调整 build timeout；分析卡在哪一步", []),
]


def _analyze_log(log: str, limit: int = 8, context_lines: int = 2) -> list[dict]:
    """扫日志识别错误类别，返回：
        [{kind, priority, title, advice, line, context, follow_up_tools, hits}]
    按 priority 降序 → 命中次数降序排序。
    - line：命中所在行
    - context：前后 context_lines 行拼接
    - hits：这类错误在日志里出现的总次数（越多越确定）
    """
    import re
    findings: dict[str, dict] = {}
    for pattern, kind, priority, title, advice, follow_ups in _ERROR_PATTERNS:
        matches = list(re.finditer(pattern, log))
        if not matches:
            continue
        m = matches[0]
        # 定位该匹配所在行 + 上下 context_lines 行
        line_start = log.rfind("\n", 0, m.start()) + 1
        line_end = log.find("\n", m.end())
        if line_end < 0:
            line_end = len(log)
        # 前面 N 行
        before = log[:line_start].rstrip("\n").split("\n")[-context_lines:] if line_start else []
        # 后面 N 行
        tail = log[line_end:].lstrip("\n").split("\n")[:context_lines] if line_end < len(log) else []
        line = log[line_start:line_end].strip()[:220]
        ctx_lines = [x.rstrip() for x in before + [line] + tail if x.strip()]
        findings[kind] = {
            "kind": kind,
            "priority": priority,
            "title": title,
            "advice": advice,
            "line": line,
            "context": "\n".join(ctx_lines)[:600],
            "follow_up_tools": follow_ups,
            "hits": len(matches),
        }
    # 排序：priority 高 → hits 多 → 先命中
    ranked = sorted(findings.values(), key=lambda x: (-x["priority"], -x["hits"]))
    return ranked[:limit]


@tool
async def jenkins_get_failed_jobs(limit: int = 30) -> str:
    """一键列出『最近一次构建失败』的 Jenkins Job（含失败构建号、时间、简短原因）。

    limit=最多返回多少条（默认 30，扫描全部 job 但只输出这么多）。
    典型用途：用户问『Jenkins 有哪些任务失败了』时首选调这个。"""
    client, err = _jenkins_client()
    if err:
        return err
    try:
        jobs = await client.get_all_jobs()
        failed = []
        # color=red → 最近一次失败；aborted → 中止；yellow → unstable
        for j in jobs:
            color = (j.get("color") or "").split("_")[0]  # 去掉 _anime 后缀
            if color not in ("red", "aborted", "yellow"):
                continue
            lb = j.get("lastBuild") or {}
            failed.append({
                "name":       j["name"],
                "result":     lb.get("result", color.upper()),
                "number":     lb.get("number"),
                "url":        lb.get("url", ""),
                "color":      color,
            })
        if not failed:
            return f"✅ 当前所有 {len(jobs)} 个 Job 最近一次构建都成功，没有失败任务。"

        # 时间戳需要额外抓，为控制耗时只对前 limit 个抓
        failed = failed[:limit]
        lines = [f"**⚠️ 发现 {len(failed)} 个失败/异常 Job（共 {len(jobs)} 个 Job 中筛出）**\n"]
        for f in failed:
            emoji = {"red": "❌", "aborted": "⏹", "yellow": "⚠️"}.get(f["color"], "❌")
            build_ref = f"#{f['number']}" if f["number"] else "-"
            lines.append(f"- {emoji} **{f['name']}** {build_ref} → {f['result']}")
        lines.append("")
        lines.append("下一步建议：对可疑 Job 调 `jenkins_diagnose_build(job=\"名称\")` 一次拿到日志+根因+建议。")
        return "\n".join(lines)
    except Exception as e:
        return f"筛选失败任务出错：{e}"


@tool
async def jenkins_diagnose_build(job: str, build: str = "lastBuild", log_lines: int = 300) -> str:
    """一键诊断构建：拉元数据 + 日志尾部 + 智能识别根因 + 精准恢复建议。

    job=Job 名称（必填）。build=构建号或 lastBuild（默认最新）。log_lines=拉多少行日志（默认 300）。
    典型用途：用户问『xxx job 为什么挂了 / 具体日志是什么 / 怎么修』时首选调这个。"""
    client, err = _jenkins_client()
    if err:
        return err
    try:
        # 1) 元数据
        info = await client.get_build_info(job, build)
        result = info.get("result") or "进行中"
        duration_s = info.get("duration", 0) // 1000
        ts = info.get("timestamp", 0) // 1000
        dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else "-"
        causes = [c.get("shortDescription", "") for a in info.get("actions", []) for c in a.get("causes", []) if a.get("causes")]

        # 2) 日志
        log = await client.get_build_logs(job, build, log_lines) or ""

        # 3) 根因识别
        findings = _analyze_log(log)

        # 4) 组装输出（三段式：现象 / 根因 / 建议）
        out = []
        emoji = {"SUCCESS": "✅", "FAILURE": "❌", "UNSTABLE": "⚠️", "ABORTED": "⏹"}.get(result, "•")
        out.append(f"## {emoji} {job} #{info.get('number', build)}  →  **{result}**")
        out.append(f"耗时 {duration_s}s · 触发时间 {dt}" + (f" · 触发原因 {causes[0]}" if causes else ""))
        out.append(f"链接：{info.get('url', '')}")
        out.append("")

        if result == "SUCCESS":
            out.append("构建成功，无需诊断。")
            return "\n".join(out)

        out.append("### 【关键结果】")
        if findings:
            for idx, f in enumerate(findings, 1):
                hits_tag = f" ×{f['hits']}" if f['hits'] > 1 else ""
                out.append(f"**{idx}. {f['title']}**（`{f['kind']}` · 优先级 {f['priority']}/9{hits_tag}）")
                out.append(f"日志上下文：")
                out.append(f"```")
                out.append(f["context"] or f["line"])
                out.append(f"```")
        else:
            out.append("未匹配到常见错误模式，日志末尾片段：")
            tail = "\n".join(log.splitlines()[-15:]) if log else "(日志为空)"
            out.append(f"```\n{tail[:800]}\n```")
        out.append("")

        out.append("### 【建议下一步】")
        if findings:
            follow_up_set: list[str] = []
            for f in findings:
                out.append(f"- **{f['title']}** → {f['advice']}")
                for tool_name in f.get("follow_up_tools", []):
                    if tool_name not in follow_up_set:
                        follow_up_set.append(tool_name)
            # 跨模块联动：建议 AI 调用哪些工具补更多信息
            if follow_up_set:
                out.append("")
                out.append("**跨模块深挖建议**（识别到的失败类型需要看 Jenkins 之外的数据）：")
                for tool_name in follow_up_set:
                    if tool_name == "get_k8s_events":
                        out.append(f"- 调 `get_k8s_events(namespace='<部署命名空间>')` 拿 Pod events 定位镜像/部署问题")
                    elif tool_name == "get_k8s_pods":
                        out.append(f"- 调 `get_k8s_pods(namespace='<部署命名空间>')` 看目标 Pod 状态")
                    elif tool_name == "jenkins_get_test_results":
                        out.append(f"- 调 `jenkins_get_test_results(job=\"{job}\", build=\"{info.get('number', build)}\")` 查具体失败测试用例")
            out.append("")
            out.append(f"- 修复后可调 `jenkins_retry_last_build(job=\"{job}\")` 用同参数重跑；或到 Jenkins UI 手动触发。")
        else:
            out.append("- 无法自动识别；建议人工看完整日志：`jenkins_get_build_logs(job, build, lines=1000)`")
            out.append(f"- 若确认是偶发抖动，可 `jenkins_retry_last_build(job=\"{job}\")` 重跑一次验证。")

        return "\n".join(out)
    except Exception as e:
        return f"诊断失败：{e}"


@tool
async def jenkins_retry_last_build(job: str) -> str:
    """用『最近一次构建的参数』重新触发该 Job（精准恢复：无需 AI 猜参数）。

    job=Job 名称（必填）。适用场景：偶发抖动 / 修复后重跑 / 上一次因外部问题失败。
    ⚠ 写操作，会实际触发构建。"""
    client, err = _jenkins_client()
    if err:
        return err
    try:
        info = await client.get_build_info(job, "lastBuild")
        # 从 actions.parameters 提取原参数
        params = {}
        for act in info.get("actions", []):
            for p in (act.get("parameters") or []):
                name = p.get("name")
                if name:
                    params[name] = p.get("value", "")
        queue_id = await client.build_job(job, params or None)
        param_desc = f"（沿用参数 {list(params.keys())}）" if params else "（无参数）"
        return (
            f"✅ 已同参数重跑 Job **{job}**，队列 ID {queue_id} {param_desc}。\n"
            f"稍候用 `jenkins_get_build_info(job=\"{job}\")` 看结果，或 `jenkins_diagnose_build` 直接诊断。"
        )
    except Exception as e:
        return f"重跑失败：{e}"


@tool
async def jenkins_analyze_failures(top_n: int = 5, log_lines: int = 300) -> str:
    """『一句话搞定』：一次调用完成『筛失败 → 逐个诊断 → 汇总报告』。

    top_n=最多诊断前几个失败 Job（默认 5，按优先级排序，避免耗时过长）。
    log_lines=每个 Job 拉多少行日志（默认 300）。
    典型用途：用户问『Jenkins 有哪些任务失败？具体日志是什么？什么原因？怎么恢复？』
    → 直接调这一个，AI 不用多轮 tool call。"""
    client, err = _jenkins_client()
    if err:
        return err
    try:
        jobs = await client.get_all_jobs()
        failed = []
        for j in jobs:
            color = (j.get("color") or "").split("_")[0]
            if color not in ("red", "aborted", "yellow"):
                continue
            lb = j.get("lastBuild") or {}
            failed.append({
                "name": j["name"],
                "color": color,
                "number": lb.get("number"),
                "result": lb.get("result", color.upper()),
            })
        if not failed:
            return f"✅ 当前所有 {len(jobs)} 个 Job 最近一次构建都成功，无失败任务需处理。"

        # 只对前 top_n 个做深度诊断（保护耗时）
        to_diagnose = failed[:top_n]
        report = [f"# Jenkins 失败任务分析报告", ""]
        report.append(f"## 📊 概览")
        report.append(f"- 总 Job 数：{len(jobs)}")
        report.append(f"- 失败/异常 Job：{len(failed)}")
        report.append(f"- 本次深度诊断：前 {len(to_diagnose)} 个（按 Jenkins 顺序）")
        report.append("")

        # 简短清单（全部失败 Job）
        report.append(f"## 📋 失败清单")
        for f in failed:
            emoji = {"red": "❌", "aborted": "⏹", "yellow": "⚠️"}.get(f["color"], "❌")
            build_ref = f"#{f['number']}" if f["number"] else "-"
            marker = " ← 诊断中" if f in to_diagnose else ""
            report.append(f"- {emoji} **{f['name']}** {build_ref} → {f['result']}{marker}")
        report.append("")

        # 逐个诊断
        report.append(f"## 🔬 深度诊断")
        agg_root_causes: dict[str, int] = {}  # 全局根因分布
        cross_module_hints: set[str] = set()
        for f in to_diagnose:
            job_name = f["name"]
            report.append("")
            report.append(f"---")
            try:
                info = await client.get_build_info(job_name, "lastBuild")
                log = await client.get_build_logs(job_name, "lastBuild", log_lines) or ""
                findings = _analyze_log(log)
                result = info.get("result") or "进行中"
                duration_s = info.get("duration", 0) // 1000
                emoji = {"SUCCESS": "✅", "FAILURE": "❌", "UNSTABLE": "⚠️", "ABORTED": "⏹"}.get(result, "•")

                report.append(f"### {emoji} {job_name} #{info.get('number', '?')}  →  **{result}** · 耗时 {duration_s}s")

                if findings:
                    for idx, fd in enumerate(findings[:3], 1):  # 每 Job 只显示 Top3 根因，避免报告过长
                        agg_root_causes[fd["title"]] = agg_root_causes.get(fd["title"], 0) + 1
                        for tool_name in fd.get("follow_up_tools", []):
                            cross_module_hints.add(tool_name)
                        hits_tag = f" ×{fd['hits']}" if fd["hits"] > 1 else ""
                        report.append(f"- **根因 {idx}**：{fd['title']}（`{fd['kind']}`·优先级 {fd['priority']}/9{hits_tag}）")
                        report.append(f"  日志片段：`{fd['line']}`")
                        report.append(f"  💡 修复建议：{fd['advice']}")
                else:
                    tail = "\n".join(log.splitlines()[-6:]) if log else "(日志为空)"
                    report.append(f"- 未识别到已知错误模式，日志尾部：")
                    report.append(f"  ```")
                    report.append(f"  {tail[:400]}")
                    report.append(f"  ```")
            except Exception as e:
                report.append(f"### ❌ {job_name} 诊断失败：{e}")

        # 全局根因分布
        if agg_root_causes:
            report.append("")
            report.append(f"## 📈 根因分布")
            for title, count in sorted(agg_root_causes.items(), key=lambda x: -x[1]):
                report.append(f"- **{title}**：{count} 个 Job 命中")

        # 跨模块建议
        if cross_module_hints:
            report.append("")
            report.append(f"## 🔗 跨模块深挖")
            for tool_name in cross_module_hints:
                if tool_name == "get_k8s_events":
                    report.append(f"- 部分失败涉及 K8s → 建议调 `get_k8s_events(namespace='<命名空间>')` 拿 Pod events")
                elif tool_name == "get_k8s_pods":
                    report.append(f"- 建议调 `get_k8s_pods(namespace='<命名空间>')` 看目标 Pod 状态")
                elif tool_name == "jenkins_get_test_results":
                    report.append(f"- 存在测试失败 → 对具体 Job 调 `jenkins_get_test_results(job, build)` 查失败用例")

        # 精准恢复
        report.append("")
        report.append(f"## 🎯 精准恢复")
        report.append(f"- 修复根本原因后，用 `jenkins_retry_last_build(job=\"<Job名>\")` 用原参数重跑（写操作需二次确认）")
        report.append(f"- 若某 Job 需要深度诊断，调 `jenkins_diagnose_build(job=\"<Job名>\", log_lines=1000)` 拉更多日志")
        if len(failed) > top_n:
            report.append(f"- 未纳入本次诊断的 {len(failed) - top_n} 个失败 Job，可指定 top_n 参数扩大范围")

        return "\n".join(report)
    except Exception as e:
        return f"分析失败：{e}"


__all__ = [
    "jenkins_get_all_jobs", "jenkins_search_jobs", "jenkins_build_job",
    "jenkins_get_build_info", "jenkins_get_build_logs", "jenkins_get_running_builds",
    "jenkins_get_queue", "jenkins_cancel_queue_item", "jenkins_get_test_results",
    # 高层复合工具
    "jenkins_get_failed_jobs", "jenkins_diagnose_build", "jenkins_retry_last_build",
    "jenkins_analyze_failures",
]
