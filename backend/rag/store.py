"""Chroma vector store for local document RAG."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings

from backend.config import get_data_dir


class VectorStore:
    COLLECTION = "documents"

    def __init__(self) -> None:
        persist = str(get_data_dir() / "chroma")
        self._client = chromadb.PersistentClient(
            path=persist,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

    @staticmethod
    def _file_hash(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()[:16]

    def delete_by_path(self, file_path: str) -> None:
        existing = self._collection.get(where={"source": file_path})
        if existing and existing.get("ids"):
            self._collection.delete(ids=existing["ids"])

    def upsert_chunks(
        self,
        file_path: str,
        chunks: list[str],
        mtime: float,
    ) -> None:
        self.delete_by_path(file_path)
        if not chunks:
            return
        path = Path(file_path)
        fhash = self._file_hash(path) if path.exists() else "missing"
        ids = [f"{file_path}::{i}" for i in range(len(chunks))]
        metadatas = [
            {"source": file_path, "chunk": i, "mtime": mtime, "hash": fhash}
            for i in range(len(chunks))
        ]
        self._collection.add(ids=ids, documents=chunks, metadatas=metadatas)

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        if self._collection.count() == 0:
            return []
        result = self._collection.query(query_texts=[query], n_results=min(top_k, max(1, self._collection.count())))
        out: list[dict[str, Any]] = []
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]
        for doc, meta, dist in zip(docs, metas, dists):
            out.append(
                {
                    "text": doc,
                    "source": meta.get("source", ""),
                    "chunk": meta.get("chunk", 0),
                    "distance": dist,
                }
            )
        return out

    def stats(self) -> dict[str, Any]:
        return {"chunk_count": self._collection.count()}

    def reset(self) -> None:
        """Drop all indexed chunks (for full re-index)."""
        name = self.COLLECTION
        try:
            self._client.delete_collection(name)
        except Exception:
            pass
        self._collection = self._client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )
