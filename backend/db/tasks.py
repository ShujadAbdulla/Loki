"""SQLite task persistence."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from backend.config import get_data_dir


class TaskStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self._path = db_path or (get_data_dir() / "tasks.db")

    async def init(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    steps TEXT,
                    channel TEXT,
                    channel_reply_to TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            await db.commit()

    async def create(
        self,
        goal: str,
        channel: str | None = None,
        channel_reply_to: str | None = None,
    ) -> dict[str, Any]:
        tid = str(uuid.uuid4())[:12]
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                INSERT INTO tasks (id, goal, status, steps, channel, channel_reply_to, created_at, updated_at)
                VALUES (?, ?, 'pending', '[]', ?, ?, ?, ?)
                """,
                (tid, goal, channel, channel_reply_to, now, now),
            )
            await db.commit()
        return await self.get(tid)  # type: ignore

    async def get(self, task_id: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)) as cur:
                row = await cur.fetchone()
        if not row:
            return None
        return self._row_to_dict(row)

    async def list_tasks(self, limit: int = 50) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
            ) as cur:
                rows = await cur.fetchall()
        return [self._row_to_dict(r) for r in rows]

    async def update_status(self, task_id: str, status: str, steps: list[str] | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        steps_json = json.dumps(steps) if steps is not None else None
        async with aiosqlite.connect(self._path) as db:
            if steps_json is not None:
                await db.execute(
                    "UPDATE tasks SET status = ?, steps = ?, updated_at = ? WHERE id = ?",
                    (status, steps_json, now, task_id),
                )
            else:
                await db.execute(
                    "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                    (status, now, task_id),
                )
            await db.commit()

    @staticmethod
    def _row_to_dict(row: aiosqlite.Row) -> dict[str, Any]:
        d = dict(row)
        try:
            d["steps"] = json.loads(d.get("steps") or "[]")
        except json.JSONDecodeError:
            d["steps"] = []
        return d
