"""YAML-driven automation workflows."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable, Awaitable

from apscheduler.schedulers.background import BackgroundScheduler
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from backend.rag.indexer import DocumentIndexer


class AutomationRunner:
    def __init__(
        self,
        indexer: DocumentIndexer,
        run_task: Callable[[str], Awaitable[str]],
    ) -> None:
        self._indexer = indexer
        self._run_task = run_task
        self._scheduler = BackgroundScheduler()
        self._observer: Observer | None = None
        self._automations: list[dict[str, Any]] = []

    def load(self, automations: list[dict[str, Any]]) -> None:
        self._automations = automations
        try:
            if self._scheduler.running:
                self._scheduler.shutdown(wait=False)
        except Exception:
            pass
        self._scheduler = BackgroundScheduler()
        if self._observer:
            self._observer.stop()
            self._observer = None

        for i, auto in enumerate(automations):
            trigger = auto.get("on")
            if trigger == "schedule":
                cron = auto.get("cron")
                if cron:
                    self._scheduler.add_job(
                        lambda a=auto: asyncio.run(self._execute(a)),
                        "cron",
                        **self._parse_cron(cron),
                        id=f"auto_{i}",
                    )
            elif trigger == "file_created":
                self._setup_file_watch(auto)

        if self._scheduler.get_jobs():
            self._scheduler.start()

    @staticmethod
    def _parse_cron(cron: str) -> dict[str, Any]:
        parts = cron.split()
        if len(parts) == 5:
            return {
                "minute": parts[0],
                "hour": parts[1],
                "day": parts[2],
                "month": parts[3],
                "day_of_week": parts[4],
            }
        return {"hour": "9", "minute": "0"}

    def _setup_file_watch(self, auto: dict[str, Any]) -> None:
        path = auto.get("path", "")
        pattern = auto.get("filter", "*")
        root = Path(path).expanduser()
        if not root.is_dir():
            return

        runner = self

        class Handler(FileSystemEventHandler):
            def on_created(self, event):
                if event.is_directory:
                    return
                p = Path(event.src_path)
                if pattern != "*" and not p.match(pattern):
                    return
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(runner._execute(auto))
                    else:
                        asyncio.run(runner._execute(auto))
                except RuntimeError:
                    asyncio.run(runner._execute(auto))

        handler = Handler()
        if not self._observer:
            self._observer = Observer()
        self._observer.schedule(handler, str(root.resolve()), recursive=False)
        if not self._observer.is_alive():
            self._observer.start()

    async def _execute(self, auto: dict[str, Any]) -> None:
        steps = auto.get("then", [])
        for step in steps:
            if isinstance(step, str):
                if step == "index_document":
                    path = auto.get("path")
                    if path:
                        self._indexer.index_directory(Path(path).expanduser())
                elif step.startswith("run_task:"):
                    goal = step.split(":", 1)[1].strip()
                    await self._run_task(goal)
            elif isinstance(step, dict):
                if "index_document" in step:
                    pass
                if "run_task" in step:
                    await self._run_task(step["run_task"])

    def stop(self) -> None:
        try:
            if self._scheduler.running:
                self._scheduler.shutdown(wait=False)
        except Exception:
            pass
        if self._observer:
            self._observer.stop()
