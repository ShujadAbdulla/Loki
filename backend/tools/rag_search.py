"""Local document search via vector store."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from backend.rag.text_utils import is_skipped_extension, sanitize_for_context

if TYPE_CHECKING:
    from backend.config import AppConfig
    from backend.rag.store import VectorStore
    from backend.security.audit import AuditLog


class RagSearchTool:
    def __init__(self, store: "VectorStore", config: "AppConfig", audit: "AuditLog") -> None:
        self._store = store
        self._config = config
        self._audit = audit

    def search(self, query: str, top_k: int | None = None) -> str:
        k = top_k or self._config.rag.top_k
        self._audit.log("rag_search", {"query": query, "top_k": k})
        hits = self._store.search(query, top_k=k)
        if not hits:
            return "No local documents indexed. Add watched folders in Settings and wait for indexing."
        parts: list[str] = []
        source_names: list[str] = []
        for i, h in enumerate(hits, 1):
            src = h.get("source", "")
            if is_skipped_extension(src):
                continue
            body = sanitize_for_context(h.get("text", ""), max_len=2000)
            if body.startswith("[Content omitted"):
                continue
            name = Path(src).name if src else "unknown"
            if name not in source_names:
                source_names.append(name)
            parts.append(f"--- Excerpt {i} ({name}) ---\n{body}")
        if not parts:
            return "No readable text found in the index for that query. Try list_directory for file names."
        footer = ""
        if source_names:
            footer = "\n\nDocuments: " + ", ".join(source_names)
        return "\n\n".join(parts) + footer
