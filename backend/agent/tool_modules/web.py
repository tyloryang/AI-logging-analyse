"""Firecrawl Web 检索 / 抓取工具。"""
from __future__ import annotations

import re

from langchain_core.tools import tool

from firecrawl_client import FirecrawlClient, FirecrawlConfigError


@tool
async def firecrawl_search_web(
    query: str,
    limit: int = 5,
    include_domains: str = "",
    scrape_content: bool = False,
) -> str:
    """Search current external web pages or official docs. Use this for vendor docs, release notes, external troubleshooting guides, or other web content that may have changed recently.
    query=search query, limit=max 10 results, include_domains=optional comma-separated hostnames like 'docs.firecrawl.dev,kubernetes.io', scrape_content=true to include markdown for each result.
    """
    client = FirecrawlClient.from_env()
    try:
        payload = await client.search(
            query=query,
            limit=limit,
            include_domains=[item.strip() for item in include_domains.split(",") if item.strip()],
            scrape_content=scrape_content,
        )
    except FirecrawlConfigError as exc:
        return str(exc)
    except Exception as exc:
        return f"Firecrawl search failed: {exc}"

    data = payload.get("data") or {}
    if isinstance(data, list):
        results = list(data)
    else:
        results = list(data.get("web") or [])
        if not results:
            results = list(data.get("news") or [])
    if not results:
        return f"No Firecrawl search results found for: {query}"

    lines = [f"Firecrawl search results for: {query}"]
    for index, item in enumerate(results[: max(1, min(limit, 10))], 1):
        metadata = item.get("metadata") or {}
        title = item.get("title") or metadata.get("title") or item.get("url") or "(untitled)"
        url = item.get("url") or metadata.get("url") or metadata.get("sourceURL") or ""
        description = item.get("description") or item.get("snippet") or metadata.get("description") or ""
        markdown = (item.get("markdown") or "").strip()

        lines.append(f"{index}. {title}")
        if url:
            lines.append(f"   URL: {url}")
        if description:
            lines.append(f"   Summary: {description[:300]}")
        if markdown:
            excerpt = re.sub(r"\s+", " ", markdown)[:700]
            lines.append(f"   Markdown: {excerpt}")
    return "\n".join(lines)


@tool
async def firecrawl_scrape_url(url: str) -> str:
    """Scrape a known external URL into clean markdown. Use this after web search or when the user already provided a URL."""
    client = FirecrawlClient.from_env()
    try:
        payload = await client.scrape(url)
    except FirecrawlConfigError as exc:
        return str(exc)
    except Exception as exc:
        return f"Firecrawl scrape failed: {exc}"

    data = payload.get("data") or {}
    metadata = data.get("metadata") or {}
    title = metadata.get("title") or metadata.get("sourceURL") or url
    final_url = metadata.get("url") or metadata.get("sourceURL") or url
    status_code = metadata.get("statusCode", "-")
    markdown = (data.get("markdown") or "").strip()
    excerpt = markdown[:4000] if markdown else ""

    lines = [
        f"Firecrawl scrape: {title}",
        f"URL: {final_url}",
        f"HTTP status: {status_code}",
    ]
    if excerpt:
        lines.append("")
        lines.append(excerpt)
    else:
        lines.append("No markdown content was returned.")
    return "\n".join(lines)


__all__ = ["firecrawl_search_web", "firecrawl_scrape_url"]
