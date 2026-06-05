"""Append-only audit log for agent actions."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import get_data_dir


class AuditLog:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (get_data_dir() / "audit.jsonl")

    @property
    def path(self) -> Path:
        return self._path

    def log(
        self,
        action: str,
        detail: dict[str, Any] | None = None,
        category: str = "AI_ACTION",
        duration_ms: int | None = None,
    ) -> str:
        entry_id = str(uuid.uuid4())[:12]
        entry = {
            "id": entry_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "category": category,
            "detail": detail or {},
            "duration_ms": duration_ms,
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry_id

    def tail(self, n: int = 50) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        lines = self._path.read_text(encoding="utf-8").strip().splitlines()
        out: list[dict[str, Any]] = []
        for line in lines[-n:]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out
