"""Watch folders and re-index on file changes."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from backend.rag.indexer import DocumentIndexer


class _Handler(FileSystemEventHandler):
    def __init__(self, indexer: DocumentIndexer, debounce_sec: float = 1.5) -> None:
        self._indexer = indexer
        self._debounce = debounce_sec
        self._pending: dict[str, float] = {}
        self._lock = threading.Lock()

    def _schedule(self, path: str, is_delete: bool) -> None:
        with self._lock:
            self._pending[path] = time.time()
            if is_delete:
                self._pending[path] = -time.time()

    def on_created(self, event) -> None:
        if not event.is_directory:
            self._schedule(event.src_path, False)

    def on_modified(self, event) -> None:
        if not event.is_directory:
            self._schedule(event.src_path, False)

    def on_deleted(self, event) -> None:
        if not event.is_directory:
            self._schedule(event.src_path, True)

    def flush(self) -> None:
        now = time.time()
        with self._lock:
            due = {p: t for p, t in self._pending.items() if abs(now - abs(t)) >= self._debounce}
            for p in due:
                del self._pending[p]
        for path, marker in due.items():
            p = Path(path)
            if marker < 0:
                self._indexer.remove_file(p)
            else:
                if p.exists():
                    self._indexer.index_file(p)


class FolderWatcher:
    def __init__(self, indexer: DocumentIndexer) -> None:
        self._indexer = indexer
        self._observer: Observer | None = None
        self._handler = _Handler(indexer)
        self._flush_thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self, roots: list[str]) -> None:
        self.stop()
        if not roots:
            return
        self._observer = Observer()
        for r in roots:
            p = Path(r).expanduser()
            if p.is_dir():
                self._indexer.index_directory(p.resolve())
                self._observer.schedule(self._handler, str(p.resolve()), recursive=True)
        self._observer.start()
        self._stop.clear()
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()

    def _flush_loop(self) -> None:
        while not self._stop.is_set():
            self._handler.flush()
            time.sleep(0.5)

    def stop(self) -> None:
        self._stop.set()
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
