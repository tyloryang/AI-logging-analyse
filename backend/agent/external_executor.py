"""External agent executor support for Claude Code / Codex / custom CLIs."""

from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import sys
from pathlib import Path
from typing import Awaitable, Callable

TokenCallback = Callable[[str], Awaitable[None] | None]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_DIR = Path(__file__).resolve().parents[1]


def _refresh_env() -> None:
    try:
        from runtime_env import refresh_runtime_settings_env

        refresh_runtime_settings_env()
    except Exception:
        pass


def _normalize_executor(value: str) -> str:
    lowered = (value or "").strip().lower()
    if lowered in {"", "langgraph", "default", "builtin"}:
        return "langgraph"
    if lowered in {"aiops_cli", "cli", "subprocess"}:
        return "aiops_cli"
    if lowered in {"external_cli", "external", "claude", "claude_code", "codex"}:
        return "external_cli"
    return "langgraph"


def get_agent_executor(channel: str = "") -> str:
    """Resolve executor mode from env/settings with backward compatibility."""
    _refresh_env()

    if channel.upper() == "FEISHU" and os.getenv("FEISHU_USE_CLI", "").strip() == "1":
        return "aiops_cli"

    configured = os.getenv("AIOPS_AGENT_EXECUTOR", "").strip()
    return _normalize_executor(configured)


def _get_external_command() -> tuple[str, str]:
    command = os.getenv("AIOPS_EXTERNAL_AGENT_COMMAND", "").strip()
    args = os.getenv("AIOPS_EXTERNAL_AGENT_ARGS", "").strip()
    if command:
        if not args and Path(command).stem.lower() == "claude":
            args = "-p"
        return command, args

    auto_claude = shutil.which("claude")
    if auto_claude:
        return auto_claude, "-p"

    return "", args


def _get_external_workdir() -> str:
    workdir = os.getenv("AIOPS_EXTERNAL_AGENT_WORKDIR", "").strip()
    return workdir or str(_REPO_ROOT)


def _get_external_timeout() -> int:
    raw = os.getenv("AIOPS_EXTERNAL_AGENT_TIMEOUT", "").strip()
    try:
        timeout = int(raw) if raw else 240
    except ValueError:
        timeout = 240
    return max(timeout, 30)


def _get_external_use_stdin() -> bool:
    raw = os.getenv("AIOPS_EXTERNAL_AGENT_USE_STDIN", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def build_external_agent_prompt(user_prompt: str, session_id: str, channel: str = "") -> str:
    return (
        "你正在作为本项目内嵌的外部 ReAct 智能体工作。\n"
        f"- 当前项目目录：{_REPO_ROOT}\n"
        f"- 当前会话：{session_id or 'default'}\n"
        f"- 当前来源：{channel or 'api'}\n"
        "- 默认先分析再执行，可自主多步调用本地能力完成任务。\n"
        "- 默认只读分析，不要修改项目文件，除非用户明确要求改代码或配置。\n"
        "- 回答使用中文，避免暴露冗长隐藏思维链；输出结论、关键依据、执行结果即可。\n\n"
        f"用户问题：{user_prompt.strip()}"
    )


async def _emit_token(callback: TokenCallback | None, text: str) -> None:
    if not callback or not text:
        return
    maybe = callback(text)
    if asyncio.iscoroutine(maybe):
        await maybe


async def _read_stream(stream: asyncio.StreamReader | None, callback: TokenCallback | None = None) -> str:
    if stream is None:
        return ""

    parts: list[str] = []
    while True:
        chunk = await stream.read(512)
        if not chunk:
            break
        text = chunk.decode("utf-8", errors="replace")
        parts.append(text)
        await _emit_token(callback, text)
    return "".join(parts)


async def run_aiops_cli_subprocess(
    prompt: str,
    session_id: str,
    on_token: TokenCallback | None = None,
) -> str:
    cli_path = _BACKEND_DIR / "aiops_cli.py"
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(cli_path),
        "--session",
        session_id or "default",
        prompt,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(_REPO_ROOT),
    )
    stdout_task = asyncio.create_task(_read_stream(proc.stdout, on_token))
    stderr_task = asyncio.create_task(_read_stream(proc.stderr))

    try:
        await asyncio.wait_for(proc.wait(), timeout=180)
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise RuntimeError("aiops_cli 执行超时（180 秒）") from exc

    stdout = (await stdout_task).strip()
    stderr = (await stderr_task).strip()
    if proc.returncode != 0:
        raise RuntimeError(f"aiops_cli 返回错误 (rc={proc.returncode}): {stderr[:500]}")
    return stdout or stderr


async def run_external_cli(
    prompt: str,
    session_id: str,
    channel: str = "",
    on_token: TokenCallback | None = None,
) -> str:
    command, args_text = _get_external_command()
    if not command:
        raise RuntimeError(
            "未找到外部 Agent CLI。请在系统配置中设置 AIOPS_EXTERNAL_AGENT_COMMAND，"
            "或确保本机已安装并可直接执行 `claude`。"
        )

    args_text = (args_text or "").format(
        session_id=session_id or "default",
        channel=(channel or "api").lower(),
        workspace=str(_REPO_ROOT),
    )
    args = shlex.split(args_text, posix=True) if args_text else []
    prepared_prompt = build_external_agent_prompt(prompt, session_id, channel)
    use_stdin = _get_external_use_stdin()
    timeout = _get_external_timeout()
    workdir = _get_external_workdir()

    argv = [command, *args]
    if not use_stdin:
        argv.append(prepared_prompt)

    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE if use_stdin else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=workdir,
    )

    if use_stdin and proc.stdin is not None:
        proc.stdin.write(prepared_prompt.encode("utf-8"))
        await proc.stdin.drain()
        proc.stdin.close()

    stdout_task = asyncio.create_task(_read_stream(proc.stdout, on_token))
    stderr_task = asyncio.create_task(_read_stream(proc.stderr))

    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise RuntimeError(f"外部 Agent CLI 执行超时（{timeout} 秒）") from exc

    stdout = (await stdout_task).strip()
    stderr = (await stderr_task).strip()
    if proc.returncode != 0:
        raise RuntimeError(
            f"外部 Agent CLI 执行失败 (rc={proc.returncode})：{stderr[:500] or stdout[:500]}"
        )
    return stdout or stderr


async def run_configured_executor(
    prompt: str,
    session_id: str,
    channel: str = "",
    on_token: TokenCallback | None = None,
) -> str:
    mode = get_agent_executor(channel)
    if mode == "aiops_cli":
        return await run_aiops_cli_subprocess(prompt, session_id, on_token=on_token)
    if mode == "external_cli":
        return await run_external_cli(prompt, session_id, channel=channel, on_token=on_token)
    raise RuntimeError(f"当前执行器模式不支持 subprocess 调用：{mode}")
