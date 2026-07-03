"""Codegraph 代码知识图谱工具。

当根因追到『应用代码层』（某个接口慢 / 某个异常类爆了）时，
用本地 codegraph CLI（tree-sitter 全量索引）直接拿：
  相关符号源码 + 调用链 + 影响面（谁调用它 / 改动会波及什么）。
比让 AI 盲目 grep 项目快一个量级。
"""
from __future__ import annotations

import asyncio
import subprocess

from langchain_core.tools import tool

_CODEGRAPH_TIMEOUT = 45
_OUTPUT_LIMIT = 8000


def _run_codegraph(query: str, project_path: str) -> str:
    proc = subprocess.run(
        ["codegraph", "explore", "-p", project_path, "--max-files", "6", query],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_CODEGRAPH_TIMEOUT,
        shell=False,
    )
    out = (proc.stdout or "") + (("\n[stderr] " + proc.stderr) if proc.returncode != 0 and proc.stderr else "")
    return out.strip()


@tool
async def codegraph_query(query: str, project_path: str = "") -> str:
    """查代码知识图谱：输入自然语言问题或符号名，返回相关源码+调用链+影响面。

    query=问题或符号名（必填），例如：
      - "order-api 的下单接口调用了哪些外部依赖"
      - "handleOrderCreate 函数"
      - "哪里在写 Redis key session:*"
    project_path=代码仓路径（可选，默认当前 AIOps 平台自身仓库）

    典型用途：告警根因追到『应用代码层』时（某接口慢/某异常类爆发），
    用它定位到具体函数和调用链，给出『改哪个文件哪一行』级别的建议。"""
    q = (query or "").strip()
    if not q:
        return "query 不能为空"
    path = (project_path or "").strip() or "."
    try:
        out = await asyncio.to_thread(_run_codegraph, q, path)
        if not out:
            return f"codegraph 对 `{q}` 无结果（索引可能未覆盖该仓库，或换个关键词）"
        if len(out) > _OUTPUT_LIMIT:
            out = out[:_OUTPUT_LIMIT] + f"\n...<截断，原长度 {len(out)}>"
        return out
    except FileNotFoundError:
        return "codegraph CLI 未安装（需要在服务器上 npm i -g @anthropic/codegraph 并 codegraph init）"
    except subprocess.TimeoutExpired:
        return f"codegraph 查询超时（>{_CODEGRAPH_TIMEOUT}s），换更具体的关键词重试"
    except Exception as e:
        return f"codegraph 查询失败：{e}"


__all__ = ["codegraph_query"]
