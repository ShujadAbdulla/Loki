"""In-memory undo buffer for reversible file operations."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass
class UndoEntry:
    audit_id: str
    action: str
    path: str
    backup_content: str | None
    created_at: float


class UndoBuffer:
    TTL_SECONDS = 30

    def __init__(self):
        self._entries: dict[str, UndoEntry] = {}

    def register_write(self, audit_id: str, path: str, previous_content: str | None):
        self._purge()
        self._entries[audit_id] = UndoEntry(
            audit_id=audit_id, action="write_file", path=path,
            backup_content=previous_content, created_at=time.time(),
        )

    def register_delete(self, audit_id: str, path: str, content: str):
        self._purge()
        self._entries[audit_id] = UndoEntry(
            audit_id=audit_id, action="delete_file", path=path,
            backup_content=content, created_at=time.time(),
        )

    def get(self, audit_id: str) -> UndoEntry | None:
        self._purge()
        return self._entries.get(audit_id)

    def pop(self, audit_id: str) -> UndoEntry | None:
        self._purge()
        return self._entries.pop(audit_id, None)

    def _purge(self):
        now = time.time()
        expired = [k for k, v in self._entries.items() if now - v.created_at > self.TTL_SECONDS]
        for k in expired:
            del self._entries[k]
