"""Loki — local FastAPI service."""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

# Allow running as python backend/main.py from project root
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv(_ROOT / ".env")

from backend.config import AppConfig, load_config, save_user_config
from backend.agent.orchestrator import AgentOrchestrator
from backend.automations.runner import AutomationRunner
from backend.db.tasks import TaskStore
from backend.rag.indexer import DocumentIndexer
from backend.rag.store import VectorStore
from backend.rag.watcher import FolderWatcher
from backend.remote.email_adapter import EmailAdapter
from backend.remote.messaging import CommandType, ParsedCommand
from backend.remote.telegram_adapter import TelegramAdapter
from backend.security.allowlist import PathAllowlist
from backend.security.approvals import ApprovalQueue
from backend.security.audit import AuditLog
from backend.tools.fs_tools import FileTools

DESKTOP_UI = _ROOT / "desktop" / "ui"

config: AppConfig = load_config()
allowlist = PathAllowlist(config.watched_paths)
approvals = ApprovalQueue()
audit = AuditLog()
file_tools = FileTools(
    allowlist,
    approvals,
    audit,
    set(config.security.require_approval_for),
)
store = VectorStore()
indexer = DocumentIndexer(store, config)
watcher = FolderWatcher(indexer)
task_store = TaskStore()
orchestrator: AgentOrchestrator | None = None
email_adapter = EmailAdapter(config.allowed_senders, config.email.command_folder)
telegram_adapter = TelegramAdapter(config.telegram_allowed_chats)
automation_runner: AutomationRunner | None = None
_bg_tasks: list[asyncio.Task] = []


class ChatRequest(BaseModel):
    message: str
    history: list[dict[str, str]] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str
    route: str
    pending_approvals: list[dict[str, Any]]


class SettingsUpdate(BaseModel):
    watched_paths: list[str] | None = None
    web_search_enabled: bool | None = None
    allowed_senders: list[str] | None = None


class WatchedPathsUpdate(BaseModel):
    paths: list[str]


def _get_orchestrator() -> AgentOrchestrator:
    global orchestrator
    if orchestrator is None:
        orchestrator = AgentOrchestrator(config, allowlist, approvals, audit, store, file_tools)
    return orchestrator


async def _handle_remote_command(cmd: ParsedCommand) -> None:
    if cmd.type == CommandType.APPROVE and cmd.approval_id:
        approvals.approve(cmd.approval_id)
        if cmd.sender and email_adapter.enabled:
            await email_adapter.send(cmd.sender, f"Approved {cmd.approval_id}")
        elif cmd.sender and telegram_adapter.enabled:
            await telegram_adapter.send(cmd.sender, f"Approved {cmd.approval_id}")
        return
    if cmd.type == CommandType.REJECT and cmd.approval_id:
        approvals.reject(cmd.approval_id)
        return
    if cmd.type == CommandType.TASK and cmd.payload:
        task = await task_store.create(
            cmd.payload,
            channel="remote",
            channel_reply_to=cmd.sender,
        )
        orch = _get_orchestrator()
        result = orch.chat(cmd.payload)
        await task_store.update_status(task["id"], "completed", [result.get("reply", "")[:500]])
        reply = f"Task {task['id']} done.\n\n{result.get('reply', '')[:3000]}"
        if cmd.sender:
            if email_adapter.enabled:
                await email_adapter.send(cmd.sender, reply)
            elif telegram_adapter.enabled:
                await telegram_adapter.send(cmd.sender, reply)


async def _run_task_goal(goal: str) -> str:
    r = _get_orchestrator().chat(goal)
    return r.get("reply", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global automation_runner
    await task_store.init()
    allowlist.set_roots(config.watched_paths)
    watcher.start(config.watched_paths)

    automation_runner = AutomationRunner(indexer, _run_task_goal)
    automation_runner.load(config.automations)

    if email_adapter.enabled:
        _bg_tasks.append(asyncio.create_task(email_adapter.start_listening(_handle_remote_command)))
    if telegram_adapter.enabled and config.telegram.enabled:
        _bg_tasks.append(asyncio.create_task(telegram_adapter.start_listening(_handle_remote_command)))

    yield

    watcher.stop()
    email_adapter.stop()
    telegram_adapter.stop()
    if automation_runner:
        automation_runner.stop()
    for t in _bg_tasks:
        t.cancel()


app = FastAPI(title="Loki", lifespan=lifespan)
_port = config.server.port
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://127.0.0.1:{_port}",
        f"http://localhost:{_port}",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "groq": bool(config.groq_api_key),
        "web_search": bool(config.tavily_api_key and config.web_search.enabled),
        "watched_paths": config.watched_paths,
        "rag_stats": store.stats(),
    }


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    try:
        result = _get_orchestrator().chat(req.message, req.history)
        return ChatResponse(**result)
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        audit.log("chat_error", {"error": str(e)})
        raise HTTPException(500, f"Agent error: {e}") from e


@app.get("/tasks")
async def list_tasks():
    return await task_store.list_tasks()


@app.get("/approvals")
def list_approvals():
    return [
        {"id": a.id, "tool": a.tool_name, "args": a.args, "created_at": a.created_at}
        for a in approvals.list_pending()
    ]


@app.post("/approve/{approval_id}")
def approve(approval_id: str):
    req = approvals.approve(approval_id)
    if not req:
        raise HTTPException(404, "Approval not found")
    audit.log("approval_granted", {"id": approval_id, "tool": req.tool_name})
    try:
        result = file_tools.execute_approved(req)
        req.result = result
    except Exception as e:
        result = f"Failed after approval: {e}"
        req.result = result
    return {"status": "approved", "id": approval_id, "result": result}


@app.post("/reject/{approval_id}")
def reject(approval_id: str):
    req = approvals.reject(approval_id)
    if not req:
        raise HTTPException(404, "Approval not found")
    return {"status": "rejected", "id": approval_id}


@app.get("/settings")
def get_settings():
    return {
        "watched_paths": config.watched_paths,
        "web_search_enabled": config.web_search.enabled,
        "allowed_senders": config.allowed_senders,
        "telegram_enabled": config.telegram.enabled,
        "email_enabled": config.email.enabled,
    }


@app.put("/settings")
def update_settings(body: SettingsUpdate):
    global config, orchestrator, file_tools
    if body.watched_paths is not None:
        config.watched_paths = body.watched_paths
        allowlist.set_roots(config.watched_paths)
        watcher.stop()
        watcher.start(config.watched_paths)
    if body.web_search_enabled is not None:
        config.web_search.enabled = body.web_search_enabled
    if body.allowed_senders is not None:
        config.allowed_senders = body.allowed_senders
    save_user_config(config)
    orchestrator = None
    return get_settings()


@app.post("/watched-paths")
def add_watched_paths(body: WatchedPathsUpdate):
    global config, orchestrator, file_tools
    merged = list(config.watched_paths)
    added: list[str] = []
    errors: list[str] = []
    for p in body.paths:
        raw = p.strip()
        if not raw:
            continue
        try:
            resolved = str(Path(raw).expanduser().resolve())
        except (OSError, ValueError) as e:
            errors.append(f"Invalid path '{raw}': {e}")
            continue
        target = Path(resolved)
        if not target.exists():
            errors.append(f"Folder does not exist: {resolved}")
            continue
        if not target.is_dir():
            errors.append(f"Not a folder (maybe a file?): {resolved}")
            continue
        if resolved in merged:
            errors.append(f"Already watching: {resolved}")
            continue
        merged.append(resolved)
        added.append(resolved)
    if not added and errors:
        raise HTTPException(400, " ".join(errors))
    config.watched_paths = merged
    allowlist.set_roots(merged)
    watcher.stop()
    watcher.start(merged)
    save_user_config(config)
    orchestrator = None
    indexed = 0
    for path in added:
        indexed += indexer.index_directory(Path(path))
    return {
        "watched_paths": merged,
        "added": added,
        "indexed_files": indexed,
        "errors": errors,
    }


@app.get("/audit")
def get_audit(n: int = 50):
    return audit.tail(n)


@app.post("/index")
def reindex(clear: bool = True):
    if clear:
        store.reset()
    count = 0
    skipped = 0
    for p in config.watched_paths:
        root = Path(p)
        for f in root.rglob("*"):
            if f.is_file():
                from backend.rag.extract import is_indexable
                if not is_indexable(f):
                    skipped += 1
                    continue
                if indexer.index_file(f):
                    count += 1
    return {
        "indexed_files": count,
        "skipped_non_text": skipped,
        "stats": store.stats(),
        "note": "Videos, audio, and images are not indexed. Use list_directory to see them.",
    }


if DESKTOP_UI.exists():
    app.mount("/ui", StaticFiles(directory=str(DESKTOP_UI), html=True), name="ui")


@app.get("/")
def root():
    if DESKTOP_UI.exists():
        return RedirectResponse(url="/ui/")
    return {"message": "Loki API", "docs": "/docs", "ui": "/ui/"}


def main():
    import uvicorn

    host = config.server.host
    port = config.server.port
    uvicorn.run(
        "backend.main:app",
        host=host,
        port=port,
        reload=os.getenv("AGENT_RELOAD", "").lower() in ("1", "true"),
    )


if __name__ == "__main__":
    main()
