"""Minimal Firecrawl API client used by agent tools and settings smoke tests."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

DEFAULT_FIRECRAWL_BASE_URL = "https://api.firecrawl.dev/v2"


class FirecrawlConfigError(RuntimeError):
    """Raised when Firecrawl credentials are missing."""


class FirecrawlClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_FIRECRAWL_BASE_URL,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or DEFAULT_FIRECRAWL_BASE_URL).rstrip("/")
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> "FirecrawlClient":
        return cls(
            api_key=os.getenv("FIRECRAWL_API_KEY", ""),
            base_url=os.getenv("FIRECRAWL_BASE_URL", DEFAULT_FIRECRAWL_BASE_URL),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise FirecrawlConfigError(
                "FIRECRAWL_API_KEY is not configured. Add it in backend/.env or System Settings first."
            )
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            trust_env=False,
        ) as client:
            response = await client.post(
                f"{self.base_url}{path}",
                headers=self._headers(),
                json=payload,
            )

        data = self._parse_json(response)
        if response.status_code >= 400:
            detail = self._extract_error_detail(data) or response.text[:300] or response.reason_phrase
            raise RuntimeError(f"Firecrawl API error {response.status_code}: {detail}")
        if data.get("success") is False:
            detail = self._extract_error_detail(data) or "unknown Firecrawl error"
            raise RuntimeError(f"Firecrawl request failed: {detail}")
        return data

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
        include_domains: list[str] | None = None,
        scrape_content: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "query": query.strip(),
            "limit": max(1, min(int(limit), 10)),
        }
        domains = [item.strip() for item in (include_domains or []) if item and item.strip()]
        if domains:
            payload["includeDomains"] = domains
        if scrape_content:
            payload["scrapeOptions"] = {"formats": [{"type": "markdown"}]}
        return await self._post("/search", payload)

    async def scrape(self, url: str) -> dict[str, Any]:
        payload = {
            "url": url.strip(),
            "formats": ["markdown"],
            "onlyMainContent": True,
        }
        return await self._post("/scrape", payload)

    async def test_connection(self) -> dict[str, Any]:
        return await self.scrape("https://firecrawl.dev")

    @staticmethod
    def _parse_json(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except Exception as exc:
            raise RuntimeError(f"Firecrawl returned non-JSON output: {exc}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Firecrawl returned an unexpected response payload.")
        return payload

    @staticmethod
    def _extract_error_detail(data: dict[str, Any]) -> str:
        for key in ("error", "message", "warning"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        if isinstance(data.get("details"), str) and data["details"].strip():
            return data["details"].strip()
        if isinstance(data.get("details"), (dict, list)):
            return json.dumps(data["details"], ensure_ascii=False)[:300]
        return ""
