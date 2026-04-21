#!/usr/bin/env python3
"""
AIOps CLI — Claude Code CLI 风格的离线模型运维助手

用法：
  python aiops_cli.py "查询最近错误日志"
  echo "帮我分析一下服务状态" | python aiops_cli.py
  python aiops_cli.py --session user123 "有什么告警？"

飞书 Bot 通过 subprocess 调用此脚本，输出结果回复给用户。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Mapping


def _bootstrap():
    """初始化环境变量（从 settings.json 读取）"""
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    try:
        from runtime_env import bootstrap_runtime_env
        bootstrap_runtime_env()
    except Exception:
        pass


async def _run(prompt: str, session_id: str) -> str:
    from langchain_core.messages import HumanMessage
    from agent.ops_quick_actions import detect_mode, get_quick_reply, quick_actions_enabled
    from agent.graph import build_graph
    from routers.agent import _get_checkpointer

    mode = detect_mode(prompt)
    quick_reply = await get_quick_reply(prompt) if quick_actions_enabled("CLI") else None
    if quick_reply:
        return quick_reply

    checkpointer = await _get_checkpointer()
    graph = build_graph(mode, checkpointer)
    config = {
        "configurable": {"thread_id": f"cli:{session_id}"},
        "recursion_limit": 40,
    }

    full_text = ""
    async for event in graph.astream_events(
        {"messages": [HumanMessage(content=prompt)]},
        config=config,
        version="v2",
    ):
        if event.get("event") != "on_chat_model_stream":
            continue
        chunk = event.get("data", {}).get("chunk")
        if chunk is None or not getattr(chunk, "content", None):
            continue
        raw = chunk.content
        parts = raw if isinstance(raw, list) else [raw]
        for part in parts:
            if isinstance(part, str):
                full_text += part
            elif isinstance(part, Mapping) and part.get("type") == "text":
                full_text += str(part.get("text") or "")

    return full_text.strip()


def main():
    _bootstrap()

    parser = argparse.ArgumentParser(description="AIOps CLI")
    parser.add_argument("prompt", nargs="?", default="", help="用户问题（也可从 stdin 读取）")
    parser.add_argument("--session", "-s", default="default", help="会话 ID（多轮上下文隔离）")
    parser.add_argument("--print", "-p", action="store_true", help="兼容 claude -p 用法（默认即为 print 模式）")
    args = parser.parse_args()

    prompt = args.prompt.strip()
    if not prompt and not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
    if not prompt:
        parser.print_help()
        sys.exit(1)

    result = asyncio.run(_run(prompt, args.session))
    print(result, flush=True)


if __name__ == "__main__":
    main()
