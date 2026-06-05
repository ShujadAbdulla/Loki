"""LangGraph ReAct agent with routing and tools."""

from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any

from langgraph.prebuilt import create_react_agent

from backend.agent.model_router import ModelRouter
from backend.agent.router import (
    Route,
    build_routing_context,
    needs_agent_tools,
    prefers_live_directory_listing,
    route_query,
)
from backend.config import AppConfig
from backend.security.allowlist import PathAllowlist
from backend.security.approvals import ApprovalQueue
from backend.security.audit import AuditLog
from backend.rag.store import VectorStore
from backend.tools.rag_search import RagSearchTool
from backend.tools.fs_tools import FileTools
from backend.tools.registry import build_tools
from backend.tools.web_search import WebSearchTool


LOKI_PERSONA = """You are Loki — clever, playful, and a little mischievous, like the Norse god of mischief (and the Marvel trickster). You assist on the user's Windows PC. Refer to yourself as Loki when it fits. Stay helpful; mischief means wit and flair, not harming the user or their files."""

_LOCAL_CITE_RE = re.compile(r"\s*\[local:\s*([^\]]+)\]\s*", re.I)
_WEB_CITE_RE = re.compile(r"\s*\[web:\s*([^\]]+)\]\s*", re.I)


def _clean_reply_citations(reply: str) -> str:
    if not reply:
        return reply
    local_paths: list[str] = []
    web_urls: list[str] = []

    def _local_sub(m: re.Match[str]) -> str:
        p = m.group(1).strip()
        if p not in local_paths:
            local_paths.append(p)
        return " "

    def _web_sub(m: re.Match[str]) -> str:
        u = m.group(1).strip()
        if u not in web_urls:
            web_urls.append(u)
        return " "

    cleaned = _LOCAL_CITE_RE.sub(_local_sub, reply)
    cleaned = _WEB_CITE_RE.sub(_web_sub, cleaned)
    cleaned = re.sub(r" +", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    source_bits: list[str] = []
    for p in local_paths:
        source_bits.append(Path(p).name)
    source_bits.extend(web_urls)
    if not source_bits:
        return reply.strip()
    if len(source_bits) == 1:
        cleaned = f"{cleaned}\n\nSource: {source_bits[0]}"
    else:
        cleaned = f"{cleaned}\n\nSources: {', '.join(source_bits)}"
    return cleaned.strip()


SYSTEM_PROMPT = f"""{LOKI_PERSONA}

You can:
- Search and read the user's local indexed documents (search_local_documents, read_file)
- Process media files (process_media) — images, audio, video, PDFs, office docs
- Generate documents (generate_docx, generate_pptx, generate_pdf, generate_xlsx)
- Search the web for current public information (web_search) when enabled
- Read, write, move, and delete files ONLY inside user-approved watched folders
- create_folder, delete_file, delete_folder, move_file, list_directory

Rules:
- For .mp4, .mp3, .png, .jpg, images, audio, video — use process_media, NOT read_file.
- For generating Word/PowerPoint/PDF/Excel files, use the generate_* tools.
- Paths must be inside watched folders listed below.
- Destructive ops return APPROVAL_REQUIRED:<id> — tell user to approve in UI.
- Be concise and actionable.
- For greetings: reply briefly as Loki without tools.
"""


class AgentOrchestrator:
    def __init__(
        self,
        config: AppConfig,
        allowlist: PathAllowlist,
        approvals: ApprovalQueue,
        audit: AuditLog,
        store: VectorStore,
        file_tools: FileTools | None = None,
        model_router: ModelRouter | None = None,
    ) -> None:
        self._config = config
        self._allowlist = allowlist
        self._approvals = approvals
        self._audit = audit
        self._store = store
        self._file_tools = file_tools
        self._model_router = model_router or ModelRouter(config, audit)
        self._rag = RagSearchTool(store, config, audit)
        self._web = WebSearchTool(config, audit)
        self._graph = None
        self._graph_paths_key: tuple[str, ...] | tuple[str, bool] = ()

    def _watched_paths_block(self) -> str:
        roots = self._allowlist.roots
        if not roots:
            return "\n\nWATCHED FOLDERS: (none — tell user to add a folder in Settings)\n"
        lines = "\n".join(f"  - {r}" for r in roots)
        return f"\n\nWATCHED FOLDERS (use these exact paths in tools):\n{lines}\n"

    def _build_graph(self, force_offline: bool = False):
        paths_key = (tuple(str(r) for r in self._allowlist.roots), force_offline)
        if self._graph is not None and self._graph_paths_key == paths_key:
            return self._graph
        self._graph_paths_key = paths_key
        llm = self._model_router.get_llm(force_offline=force_offline)
        tools = build_tools(
            self._config,
            self._allowlist,
            self._approvals,
            self._audit,
            self._store,
            fs=self._file_tools,
            llm=llm,
        )
        prompt = SYSTEM_PROMPT + self._watched_paths_block()
        self._graph = create_react_agent(llm, tools, prompt=prompt)
        return self._graph

    def _simple_chat(self, message: str, history: list[dict[str, str]] | None) -> str:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        llm = self._model_router.get_llm()
        roots = self._allowlist.roots
        folder_hint = f" Watching folder: {roots[0]}." if roots else ""
        system = (
            "You are Loki — witty, mischievous, charming. You help on the user's Windows PC."
            f"{folder_hint} On greetings, introduce yourself briefly. No tools unless asked."
        )
        messages: list = [SystemMessage(content=system)]
        if history:
            for h in history[-6:]:
                role, content = h.get("role"), h.get("content", "")
                if not content:
                    continue
                if role == "user":
                    messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    messages.append(AIMessage(content=content))
        messages.append(HumanMessage(content=message))
        out = llm.invoke(messages)
        return out.content if isinstance(out.content, str) else str(out.content)

    def _pending(self) -> list[dict[str, Any]]:
        return [
            {"id": a.id, "tool": a.tool_name, "args": a.args}
            for a in self._approvals.list_pending()
        ]

    def chat(self, message: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
        route = route_query(message, self._config)
        mode = self._model_router.get_status()

        if not needs_agent_tools(message, route):
            reply = self._simple_chat(message, history)
            return {"reply": reply, "route": "casual", "mode": mode, "pending_approvals": self._pending()}

        local_ctx = ""
        web_ctx = ""
        if route in (Route.LOCAL, Route.BOTH, Route.MEDIA) and not prefers_live_directory_listing(message):
            local_ctx = self._rag.search(message)
        if route in (Route.WEB, Route.BOTH) and self._web.available:
            web_ctx = self._web.search(message)
        prefix = build_routing_context(route, local_ctx, web_ctx)
        paths_note = self._watched_paths_block()
        if prefix:
            full_message = f"{paths_note}{prefix}\n\nUser: {message}"
        else:
            full_message = f"{paths_note}\nUser: {message}" if paths_note.strip() else message

        graph = self._build_graph()
        messages = []
        if history:
            for h in history[-10:]:
                role = h.get("role", "user")
                content = h.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": full_message})

        self._audit.log("chat", {"message": message[:200], "route": route.value}, category="AI_ACTION")
        try:
            result = graph.invoke({"messages": messages})
        except Exception as e:
            if self._model_router.preference == "auto" and self._config.groq_api_key:
                self._model_router.mark_fallback()
                self._graph = None
                threading.Thread(target=self._model_router.ensure_ollama_running, daemon=True).start()
                graph = self._build_graph(force_offline=True)
                result = graph.invoke({"messages": messages})
            else:
                raise RuntimeError(f"AI request failed: {e}") from e
        out_messages = result.get("messages", [])
        reply = ""
        try:
            from langchain_core.messages import AIMessage
            for m in reversed(out_messages):
                if isinstance(m, AIMessage) and m.content:
                    reply = m.content if isinstance(m.content, str) else str(m.content)
                    break
        except ImportError:
            pass
        if not reply:
            for m in reversed(out_messages):
                t = getattr(m, "type", None) or type(m).__name__
                if t in ("ai", "AIMessage") and getattr(m, "content", None):
                    c = m.content
                    reply = c if isinstance(c, str) else str(c)
                    break
        if not reply and out_messages:
            last = out_messages[-1]
            reply = getattr(last, "content", str(last))
        reply = _clean_reply_citations(reply)
        return {
            "reply": reply,
            "route": route.value,
            "mode": self._model_router.get_status(),
            "pending_approvals": self._pending(),
        }
