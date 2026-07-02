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

# 常见错误关键字 → 分类 + 建议动作
_ERROR_PATTERNS = [
    # 编译/构建
    (r"(?i)compilation failed|BUILD FAILED|error: (cannot find symbol|package .* does not exist)",
     "compile", "代码编译失败", "检查代码语法 / 依赖版本；查看提交历史找到引入错误的 commit 后修复或回滚"),
    (r"(?i)npm ERR!|yarn error|ELIFECYCLE",
     "npm_build", "Node.js 构建失败", "对齐 package-lock.json 与 node 版本；检查依赖是否已发布；必要时 npm cache clean"),
    (r"(?i)ImportError|ModuleNotFoundError|python\.egg-info.*failed",
     "python_dep", "Python 依赖缺失", "校对 requirements.txt / pyproject.toml；确认虚拟环境激活；网络能通 PyPI 镜像"),
    (r"(?i)Could not resolve dependencies|Failed to collect dependencies|no valid.*artifact",
     "maven_dep", "Maven/Gradle 依赖解析失败", "检查私服连接 / settings.xml；跑一次 mvn -U 强制刷新；核对 pom.xml 版本号"),
    # 测试
    (r"(?i)test.*FAILED|assertion.*failed|Tests run: \d+, Failures: [1-9]|junit.*failure",
     "test", "单元测试挂了", "跑 jenkins_get_test_results 查具体失败用例；本地复现后修 assertion / mock"),
    # 部署 / K8s / Docker
    (r"(?i)ImagePullBackOff|ErrImagePull|manifest unknown|denied.*docker",
     "image_pull", "镜像拉取失败", "检查镜像 tag 是否已推送 / imagePullSecret / 仓库地址；重跑推送再触发"),
    (r"(?i)kubectl.*(error|refused|forbidden)|The connection to the server .* was refused",
     "k8s_conn", "K8s API 不可达", "kubectl cluster-info 检查连通；kubeconfig token 是否过期"),
    (r"(?i)deploy.*timed?[- ]?out|rollout.*progressing|readiness probe failed",
     "deploy_timeout", "部署超时（探针未就绪）", "看 Pod events / readinessProbe 配置；应用启动慢考虑扩 timeout"),
    # 基础设施
    (r"(?i)connection refused|no route to host|network is unreachable",
     "network", "网络不通", "从 Jenkins 节点 telnet / curl 目标 → 排查防火墙 / DNS / VPN"),
    (r"(?i)OutOfMemoryError|Killed process|OOMKilled|Cannot allocate memory",
     "oom", "内存不足 / OOM", "调大 JVM -Xmx / Pod resources.limits.memory；或找内存泄漏"),
    (r"(?i)No space left on device|disk.*full|inode.*used up",
     "disk", "磁盘/inode 打满", "df -h + du -sh 找大目录清理；构建缓存可 clean workspace"),
    (r"(?i)Permission denied|EACCES|Access is denied|forbidden \(403\)",
     "perm", "权限不足", "检查执行用户 / SSH key / API Token / K8s RBAC"),
    # SCM
    (r"(?i)Could not read from remote repository|GitException|Repository not found",
     "git", "Git 拉代码失败", "检查 credentials / branch 是否存在 / 代理设置"),
    # Jenkins 自身
    (r"(?i)Jenkins is (going )?to shut down|slave.*disconnected|node.*offline|executor.*busy",
     "jenkins_infra", "Jenkins 节点/执行器异常", "看节点状态；必要时重启 agent 或分配到其它 label"),
    # 超时
    (r"(?i)aborted.*took .* > .*|timed? out after|Build step .* marked build as failure",
     "abort_timeout", "构建被中止/超时", "看是否有人手动中止；调整 build timeout；分析卡在哪一步"),
]


def _analyze_log(log: str, limit: int = 8) -> list[dict]:
    """扫日志识别错误类别 + 关键行摘录。返回按出现顺序去重的错误分类列表。"""
    import re
    findings: list[dict] = []
    seen: set[str] = set()
    for pattern, kind, title, advice in _ERROR_PATTERNS:
        m = re.search(pattern, log)
        if not m:
            continue
        if kind in seen:
            continue
        seen.add(kind)
        # 定位该匹配所在行 + 上下 1 行
        start = log.rfind("\n", 0, m.start()) + 1
        end = log.find("\n", m.end())
        if end < 0:
            end = len(log)
        snippet = log[start:end].strip()[:220]
        findings.append({"kind": kind, "title": title, "advice": advice, "line": snippet})
        if len(findings) >= limit:
            break
    return findings


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
            for f in findings:
                out.append(f"- **{f['title']}**（`{f['kind']}`）")
                out.append(f"  日志片段：`{f['line']}`")
        else:
            out.append("- 未匹配到常见错误模式，日志末尾片段：")
            tail = "\n".join(log.splitlines()[-15:]) if log else "(日志为空)"
            out.append(f"```\n{tail[:800]}\n```")
        out.append("")

        out.append("### 【建议下一步】")
        if findings:
            for f in findings:
                out.append(f"- {f['title']} → {f['advice']}")
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


__all__ = [
    "jenkins_get_all_jobs", "jenkins_search_jobs", "jenkins_build_job",
    "jenkins_get_build_info", "jenkins_get_build_logs", "jenkins_get_running_builds",
    "jenkins_get_queue", "jenkins_cancel_queue_item", "jenkins_get_test_results",
    # 高层复合工具
    "jenkins_get_failed_jobs", "jenkins_diagnose_build", "jenkins_retry_last_build",
]
