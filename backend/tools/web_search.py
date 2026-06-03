"""Tavily web search tool."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.config import AppConfig
    from backend.security.audit import AuditLog


class WebSearchTool:
    def __init__(self, config: "AppConfig", audit: "AuditLog") -> None:
        self._config = config
        self._audit = audit
        self._tavily = None

    def _get_tavily(self):
        if self._tavily is not None:
            return self._tavily
        key = self._config.tavily_api_key
        if not key:
            return None
        from langchain_tavily import TavilySearch

        self._tavily = TavilySearch(max_results=self._config.web_search.max_results, tavily_api_key=key)
        return self._tavily

    @property
    def available(self) -> bool:
        return bool(self._config.web_search.enabled and self._config.tavily_api_key)

    def search(self, query: str, max_results: int | None = None) -> str:
        if not self.available:
            return "Web search is disabled. Set TAVILY_API_KEY and enable web_search in settings."
        tavily = self._get_tavily()
        if not tavily:
            return "Web search unavailable."
        n = max_results or self._config.web_search.max_results
        self._audit.log("web_search", {"query": query, "max_results": n})
        try:
            raw = tavily.invoke({"query": query})
            if isinstance(raw, str):
                return raw
            return json.dumps(raw, indent=2, ensure_ascii=False)[:15000]
        except Exception as e:
            return f"Web search error: {e}"
