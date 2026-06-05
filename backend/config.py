"""Load configuration from YAML and environment."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

CONFIG_PATH = PROJECT_ROOT / "config" / "default.yaml"
USER_CONFIG_PATH = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PersonalAgent" / "config.yaml"


def get_data_dir() -> Path:
    d = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PersonalAgent"
    d.mkdir(parents=True, exist_ok=True)
    return d


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8787


class AgentConfig(BaseModel):
    model: str = "llama-3.3-70b-versatile"
    local_model: str = "phi3:mini"
    vision_model: str = "moondream"
    temperature: float = 0.3
    llm_mode: str = "auto"  # auto | online | offline


class WebSearchConfig(BaseModel):
    enabled: bool = True
    max_results: int = 5


class RagConfig(BaseModel):
    chunk_size: int = 800
    chunk_overlap: int = 120
    top_k: int = 5
    email_index_limit: int = 500


class MediaConfig(BaseModel):
    whisper_model: str = "base"
    video_frame_interval: int = 30
    judge_confidence_threshold: float = 0.7
    max_vision_frames: int = 5


class GeneratorsConfig(BaseModel):
    output_folder: str = ""
    template_folder: str = ""


class StartupConfig(BaseModel):
    catchup_enabled: bool = True
    start_with_windows: bool = False
    minimize_to_tray: bool = True


class SecurityConfig(BaseModel):
    require_approval_for: list[str] = Field(default_factory=list)


class EmailConfig(BaseModel):
    enabled: bool = False
    imap_host: str = ""
    imap_port: int = 993
    smtp_host: str = ""
    smtp_port: int = 587
    command_folder: str = "AgentCommands"


class TelegramConfig(BaseModel):
    enabled: bool = False


class AppConfig(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    web_search: WebSearchConfig = Field(default_factory=WebSearchConfig)
    rag: RagConfig = Field(default_factory=RagConfig)
    media: MediaConfig = Field(default_factory=MediaConfig)
    generators: GeneratorsConfig = Field(default_factory=GeneratorsConfig)
    startup: StartupConfig = Field(default_factory=StartupConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    watched_paths: list[str] = Field(default_factory=list)
    allowed_senders: list[str] = Field(default_factory=list)
    network_allowlist: list[str] = Field(default_factory=list)
    email: EmailConfig = Field(default_factory=EmailConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    automations: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def groq_api_key(self) -> str | None:
        return os.getenv("GROQ_API_KEY") or os.getenv("groq")

    @property
    def tavily_api_key(self) -> str | None:
        return os.getenv("TAVILY_API_KEY") or os.getenv("tavily_API")

    @property
    def telegram_token(self) -> str | None:
        return os.getenv("TELEGRAM_BOT_TOKEN")

    @property
    def telegram_allowed_chats(self) -> list[int]:
        raw = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "")
        if not raw.strip():
            return []
        return [int(x.strip()) for x in raw.split(",") if x.strip().lstrip("-").isdigit()]

    @property
    def google_client_id(self) -> str | None:
        return os.getenv("GOOGLE_CLIENT_ID")

    @property
    def google_client_secret(self) -> str | None:
        return os.getenv("GOOGLE_CLIENT_SECRET")

    @property
    def microsoft_client_id(self) -> str | None:
        return os.getenv("MICROSOFT_CLIENT_ID")


def _merge_dict(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _merge_dict(out[k], v)
        else:
            out[k] = v
    return out


def load_config() -> AppConfig:
    default_data: dict[str, Any] = {}
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open(encoding="utf-8") as f:
            default_data = yaml.safe_load(f) or {}
    data = dict(default_data)
    if USER_CONFIG_PATH.exists():
        with USER_CONFIG_PATH.open(encoding="utf-8") as f:
            user = yaml.safe_load(f) or {}
            data = _merge_dict(data, user)
    # Union approval tools so older user configs still pick up new defaults
    merged = set((default_data.get("security") or {}).get("require_approval_for", []))
    merged.update((data.get("security") or {}).get("require_approval_for", []))
    if merged:
        data.setdefault("security", {})["require_approval_for"] = sorted(merged)
    server = data.setdefault("server", {})
    if os.getenv("SERVER_PORT"):
        server["port"] = int(os.getenv("SERVER_PORT"))
    # Local only — never bind to all interfaces from env
    server["host"] = "127.0.0.1"
    cfg = AppConfig.model_validate(data)
    data_dir = get_data_dir()
    if not cfg.generators.output_folder:
        cfg.generators.output_folder = str(data_dir / "generated")
    if not cfg.generators.template_folder:
        cfg.generators.template_folder = str(data_dir / "templates")
    return cfg


def save_user_config(cfg: AppConfig) -> None:
    USER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = cfg.model_dump()
    with USER_CONFIG_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, default_flow_style=False)
