"""Transparent online/offline LLM switching with user preference."""

from __future__ import annotations

import threading
from typing import Literal

Status = Literal["online", "offline", "unavailable"]
ModePreference = Literal["auto", "online", "offline"]


class ModelRouter:
    def __init__(self, config, audit=None):
        self._config = config
        self._audit = audit
        self._active: Status = "online"
        self._lock = threading.Lock()
        self._init_active_status()

    def _init_active_status(self):
        pref = self.preference
        if pref == "offline" or not self._config.groq_api_key:
            self._active = "offline"
        else:
            self._active = "online"

    @property
    def preference(self) -> ModePreference:
        mode = getattr(self._config.agent, "llm_mode", "auto") or "auto"
        if mode not in ("auto", "online", "offline"):
            return "auto"
        return mode  # type: ignore[return-value]

    def set_preference(self, mode: ModePreference) -> None:
        self._config.agent.llm_mode = mode
        with self._lock:
            if mode == "offline":
                self._active = "offline"
            elif self._config.groq_api_key:
                self._active = "online"
            else:
                self._active = "unavailable"
        if self._audit:
            self._audit.log("llm_preference_change", {"preference": mode}, category="AI_ACTION")

    def get_llm(self, *, force_offline: bool = False):
        pref = self.preference
        use_groq = (
            not force_offline
            and pref != "offline"
            and bool(self._config.groq_api_key)
        )
        if use_groq:
            from langchain_groq import ChatGroq
            with self._lock:
                self._active = "online"
            return ChatGroq(
                model=self._config.agent.model,
                api_key=self._config.groq_api_key,
                temperature=self._config.agent.temperature,
            )
        if pref == "online" and not self._config.groq_api_key:
            raise RuntimeError(
                "Online mode requires GROQ_API_KEY. Add it to .env or switch to Auto/Offline in Settings."
            )
        with self._lock:
            self._active = "offline"
        return self._get_ollama_llm()

    def _get_ollama_llm(self):
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=self._config.agent.local_model,
            base_url="http://localhost:11434",
            temperature=self._config.agent.temperature,
        )

    def mark_fallback(self) -> None:
        with self._lock:
            if self._active != "offline":
                self._active = "offline"
                if self._audit:
                    self._audit.log("llm_offline_fallback", {"reason": "groq_request_failed"}, category="AI_ACTION")

    def get_status(self) -> Status:
        pref = self.preference
        if pref == "offline":
            return "offline"
        if not self._config.groq_api_key:
            return "offline" if pref == "auto" else "unavailable"
        with self._lock:
            return self._active

    def should_use_ollama_on_startup(self) -> bool:
        return self.preference == "offline" or (
            self.preference == "auto" and not self._config.groq_api_key
        )

    def ensure_ollama_running(self):
        import subprocess
        import time as _time
        try:
            import requests
            requests.get("http://localhost:11434", timeout=2)
            return
        except Exception:
            pass
        try:
            flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            subprocess.Popen(["ollama", "serve"], creationflags=flags)
            _time.sleep(3)
            for model in [self._config.agent.local_model, self._config.agent.vision_model]:
                try:
                    subprocess.run(["ollama", "pull", model], capture_output=True, timeout=300)
                except Exception:
                    pass
        except Exception:
            pass
