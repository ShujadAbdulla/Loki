"""Chunk and index documents into the vector store."""

from __future__ import annotations

from pathlib import Path

from backend.config import AppConfig
from backend.rag.extract import extract_text, is_indexable
from backend.rag.text_utils import text_looks_readable
from backend.rag.store import VectorStore


class DocumentIndexer:
    def __init__(self, store: VectorStore, config: AppConfig) -> None:
        self._store = store
        self._config = config

    def _chunk(self, text: str) -> list[str]:
        size = self._config.rag.chunk_size
        overlap = self._config.rag.chunk_overlap
        if len(text) <= size:
            return [text] if text.strip() else []
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = start + size
            chunks.append(text[start:end])
            start = end - overlap
        return chunks

    def index_file(self, path: Path) -> bool:
        if not is_indexable(path):
            return False
        try:
            text = extract_text(path)
            if not text_looks_readable(text, min_len=20):
                return False
            chunks = self._chunk(text)
            if not chunks:
                return False
            mtime = path.stat().st_mtime
            self._store.upsert_chunks(str(path.resolve()), chunks, mtime)
            return True
        except Exception:
            return False

    def remove_file(self, path: Path) -> None:
        self._store.delete_by_path(str(path.resolve()))

    def index_directory(self, root: Path) -> int:
        count = 0
        for p in root.rglob("*"):
            if p.is_file() and is_indexable(p):
                if self.index_file(p):
                    count += 1
        return count
