"""LangChain tool for hybrid media processing."""

from __future__ import annotations

from pathlib import Path

from backend.media.processor import MediaProcessor


class MediaTool:
    def __init__(self, config, audit, store, allowlist, processor: MediaProcessor | None = None):
        self._config = config
        self._audit = audit
        self._store = store
        self._allowlist = allowlist
        self._processor = processor or MediaProcessor(config, audit)

    def process_media(self, path: str) -> str:
        try:
            p = self._allowlist.resolve_allowed(path)
        except PermissionError:
            return f"Path not in watched folders: {path}"
        if not p.exists():
            return f"File not found: {resolved}"
        text = self._processor.process(p)
        mtime = p.stat().st_mtime if p.exists() else 0
        chunk_size = self._config.rag.chunk_size
        chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)] or [text]
        self._store.upsert_chunks(str(p), chunks, mtime)
        self._audit.log("media_processed", {"path": str(p), "chars": len(text)}, category="FILE")
        preview = text[:2000] + ("..." if len(text) > 2000 else "")
        return f"Processed {p.name} ({len(text)} chars). Indexed for search.\n\n{preview}"
