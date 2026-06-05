"""Loki v2 — local FastAPI service."""

from __future__ import annotations

import asyncio
import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv(_ROOT / ".env")

from backend.config import AppConfig, load_config, save_user_config
from backend.agent.model_router import ModelRouter
from backend.agent.orchestrator import AgentOrchestrator
from backend.automations.runner import AutomationRunner
from backend.automations.startup import StartupBriefing
from backend.communication.gmail_adapter import GmailAdapter
from backend.communication.outlook_adapter import OutlookAdapter
from backend.communication.whatsapp_adapter import WhatsAppAdapter
from backend.db.tasks import TaskStore
from backend.generators.docx_generator import DocxGenerator
from backend.generators.pdf_generator import PdfGenerator
from backend.generators.pptx_generator import PptxGenerator
from backend.generators.xlsx_generator import XlsxGenerator
from backend.rag.indexer import DocumentIndexer
from backend.rag.store import VectorStore
from backend.rag.watcher import FolderWatcher
from backend.remote.email_adapter import EmailAdapter
from backend.remote.messaging import CommandType, ParsedCommand
from backend.remote.telegram_adapter import TelegramAdapter
from backend.security.allowlist import PathAllowlist
from backend.security.approvals import ApprovalQueue
from backend.security.audit import AuditLog
from backend.security.undo import UndoBuffer
from backend.tools.fs_tools import FileTools

DESKTOP_UI = _ROOT / "desktop" / "ui"

config: AppConfig = load_config()
allowlist = PathAllowlist(config.watched_paths)
approvals = ApprovalQueue()
audit = AuditLog()
undo_buffer = UndoBuffer()
file_tools = FileTools(allowlist, approvals, audit, set(config.security.require_approval_for))
store = VectorStore()
indexer = DocumentIndexer(store, config)
watcher = FolderWatcher(indexer)
task_store = TaskStore()
model_router = ModelRouter(config, audit)
orchestrator: AgentOrchestrator | None = None
email_adapter = EmailAdapter(config.allowed_senders, config.email.command_folder)
telegram_adapter = TelegramAdapter(config.telegram_allowed_chats)
gmail_adapter = GmailAdapter(config, audit)
outlook_adapter = OutlookAdapter(config, audit)
whatsapp_adapter = WhatsAppAdapter(config, audit)
startup_briefing = StartupBriefing(config, audit, store, gmail_adapter, outlook_adapter)
automation_runner: AutomationRunner | None = None
_bg_tasks: list[asyncio.Task] = []


class ChatRequest(BaseModel):
    message: str
    history: list[dict[str, str]] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str
    route: str
    mode: str = "online"
    pending_approvals: list[dict[str, Any]]


class SettingsUpdate(BaseModel):
    watched_paths: list[str] | None = None
    web_search_enabled: bool | None = None
    allowed_senders: list[str] | None = None
    llm_mode: Literal["auto", "online", "offline"] | None = None


class WatchedPathsUpdate(BaseModel):
    paths: list[str]


class GenerateRequest(BaseModel):
    type: Literal["docx", "pptx", "pdf", "xlsx"]
    prompt: str
    template: bool = False


class WhatsAppReadRequest(BaseModel):
    contact: str
    n: int = 20


def _get_orchestrator() -> AgentOrchestrator:
    global orchestrator
    if orchestrator is None:
        orchestrator = AgentOrchestrator(
            config, allowlist, approvals, audit, store, file_tools, model_router
        )
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
        task = await task_store.create(cmd.payload, channel="remote", channel_reply_to=cmd.sender)
        result = _get_orchestrator().chat(cmd.payload)
        await task_store.update_status(task["id"], "completed", [result.get("reply", "")[:500]])
        reply = f"Task {task['id']} done.\n\n{result.get('reply', '')[:3000]}"
        if cmd.sender:
            if email_adapter.enabled:
                await email_adapter.send(cmd.sender, reply)
            elif telegram_adapter.enabled:
                await telegram_adapter.send(cmd.sender, reply)


async def _run_task_goal(goal: str) -> str:
    return _get_orchestrator().chat(goal).get("reply", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global automation_runner
    await task_store.init()
    allowlist.set_roots(config.watched_paths)
    watcher.start(config.watched_paths)
    startup_briefing.generate_briefing()
    if model_router.should_use_ollama_on_startup():
        threading.Thread(target=model_router.ensure_ollama_running, daemon=True).start()
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
    whatsapp_adapter.close()
    if automation_runner:
        automation_runner.stop()
    for t in _bg_tasks:
        t.cancel()


app = FastAPI(title="Loki", lifespan=lifespan)
_port = config.server.port
app.add_middleware(
    CORSMiddleware,
    allow_origins=[f"http://127.0.0.1:{_port}", f"http://localhost:{_port}"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "mode": model_router.get_status(),
        "llm_preference": model_router.preference,
        "groq": bool(config.groq_api_key),
        "groq_configured": bool(config.groq_api_key),
        "web_search": bool(config.tavily_api_key and config.web_search.enabled),
        "watched_paths": config.watched_paths,
        "rag_stats": store.stats(),
        "gmail": gmail_adapter.connected,
        "outlook": outlook_adapter.connected,
        "whatsapp": whatsapp_adapter.connected,
    }


@app.get("/briefing")
def get_briefing():
    return {"text": startup_briefing.text}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    try:
        result = _get_orchestrator().chat(req.message, req.history)
        return ChatResponse(**result)
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        audit.log("chat_error", {"error": str(e)}, category="ERROR")
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
    audit.log("approval_granted", {"id": approval_id, "tool": req.tool_name}, category="FILE")
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
        "llm_mode": model_router.preference,
        "mode": model_router.get_status(),
        "groq_configured": bool(config.groq_api_key),
    }


@app.put("/settings")
def update_settings(body: SettingsUpdate):
    global config, orchestrator
    if body.watched_paths is not None:
        config.watched_paths = body.watched_paths
        allowlist.set_roots(config.watched_paths)
        watcher.stop()
        watcher.start(config.watched_paths)
    if body.web_search_enabled is not None:
        config.web_search.enabled = body.web_search_enabled
    if body.allowed_senders is not None:
        config.allowed_senders = body.allowed_senders
    if body.llm_mode is not None:
        model_router.set_preference(body.llm_mode)
        config.agent.llm_mode = body.llm_mode
        if body.llm_mode == "offline":
            threading.Thread(target=model_router.ensure_ollama_running, daemon=True).start()
    save_user_config(config)
    orchestrator = None
    return get_settings()


@app.post("/watched-paths")
def add_watched_paths(body: WatchedPathsUpdate):
    global config, orchestrator
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
            errors.append(f"Not a folder: {resolved}")
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
    indexed = sum(indexer.index_directory(Path(path)) for path in added)
    return {"watched_paths": merged, "added": added, "indexed_files": indexed, "errors": errors}


@app.get("/audit")
def get_audit(n: int = 50):
    return audit.tail(n)


@app.get("/audit/stream")
async def audit_stream():
    async def event_generator():
        last_pos = 0
        while True:
            if audit.path.exists():
                with audit.path.open(encoding="utf-8") as f:
                    f.seek(last_pos)
                    new_lines = f.readlines()
                    last_pos = f.tell()
                for line in new_lines:
                    yield f"data: {line}\n\n"
            await asyncio.sleep(1)
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/undo/{audit_id}")
def undo_action(audit_id: str):
    entry = undo_buffer.pop(audit_id)
    if not entry:
        raise HTTPException(404, "Undo expired or not found")
    path = Path(entry.path)
    try:
        if entry.action == "write_file":
            if entry.backup_content is None:
                if path.exists():
                    path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(entry.backup_content, encoding="utf-8")
        elif entry.action == "delete_file" and entry.backup_content:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(entry.backup_content, encoding="utf-8")
        audit.log("undo_executed", {"audit_id": audit_id, "path": entry.path}, category="FILE")
        return {"status": "undone", "path": entry.path}
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.post("/index")
def reindex(clear: bool = True):
    if clear:
        store.reset()
    count = skipped = 0
    for p in config.watched_paths:
        for f in Path(p).rglob("*"):
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
        "note": "Use process_media for images, audio, and video files.",
    }


@app.post("/generate")
def generate_file(req: GenerateRequest):
    llm = model_router.get_llm()
    gen_map = {
        "docx": DocxGenerator, "pptx": PptxGenerator,
        "pdf": PdfGenerator, "xlsx": XlsxGenerator,
    }
    gen = gen_map[req.type](config, audit, llm)
    path = gen.generate(req.prompt)
    return {"path": str(path), "filename": path.name}


@app.get("/downloads")
def list_downloads():
    output_dir = Path(config.generators.output_folder)
    if not output_dir.exists():
        return []
    files = sorted(output_dir.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)
    return [
        {"name": f.name, "path": str(f), "size": f.stat().st_size,
         "modified": f.stat().st_mtime, "type": f.suffix[1:]}
        for f in files if f.is_file()
    ]


@app.get("/gmail/auth")
def gmail_auth():
    if not config.google_client_id:
        raise HTTPException(400, "GOOGLE_CLIENT_ID not set")
    return {"auth_url": gmail_adapter.get_auth_url()}


@app.get("/gmail/callback")
def gmail_callback(code: str):
    gmail_adapter.handle_callback(code)
    return RedirectResponse(url="/ui/?gmail=connected")


@app.get("/gmail/status")
def gmail_status():
    return {"connected": gmail_adapter.connected}


@app.get("/emails/gmail")
def get_gmail_emails(n: int = 20):
    if not gmail_adapter.connected:
        raise HTTPException(400, "Gmail not connected")
    return gmail_adapter.read_inbox(n)


@app.get("/outlook/auth")
def outlook_auth():
    if not config.microsoft_client_id:
        raise HTTPException(400, "MICROSOFT_CLIENT_ID not set")
    return outlook_adapter.start_device_flow()


@app.post("/outlook/complete")
def outlook_complete():
    outlook_adapter.complete_device_flow()
    return {"connected": True}


@app.get("/outlook/status")
def outlook_status():
    return {"connected": outlook_adapter.connected}


@app.get("/emails/outlook")
def get_outlook_emails(n: int = 20):
    if not outlook_adapter.connected:
        raise HTTPException(400, "Outlook not connected")
    return outlook_adapter.read_inbox(n)


@app.get("/whatsapp/status")
def whatsapp_status():
    return {"connected": whatsapp_adapter.connected}


@app.post("/whatsapp/connect")
def whatsapp_connect():
    threading.Thread(target=whatsapp_adapter.open_and_wait_for_qr, daemon=True).start()
    return {"message": "WhatsApp Web opening — scan the QR code"}


@app.post("/whatsapp/read")
def whatsapp_read(req: WhatsAppReadRequest):
    return whatsapp_adapter.read_messages(req.contact, req.n)


if DESKTOP_UI.exists():
    app.mount("/ui", StaticFiles(directory=str(DESKTOP_UI), html=True), name="ui")


@app.get("/")
def root():
    if DESKTOP_UI.exists():
        return RedirectResponse(url="/ui/")
    return {"message": "Loki API", "docs": "/docs", "ui": "/ui/"}


def main():
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=config.server.host,
        port=config.server.port,
        reload=os.getenv("AGENT_RELOAD", "").lower() in ("1", "true"),
    )


if __name__ == "__main__":
    main()
