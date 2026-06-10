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


__all__ = [
    "jenkins_get_all_jobs", "jenkins_search_jobs", "jenkins_build_job",
    "jenkins_get_build_info", "jenkins_get_build_logs", "jenkins_get_running_builds",
    "jenkins_get_queue", "jenkins_cancel_queue_item", "jenkins_get_test_results",
]
