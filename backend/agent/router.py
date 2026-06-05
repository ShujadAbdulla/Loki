"""Route queries to local RAG, web search, or both."""

from __future__ import annotations

import re
from enum import Enum

from backend.config import AppConfig


class Route(str, Enum):
    LOCAL = "local"
    WEB = "web"
    BOTH = "both"
    MEDIA = "media"
    CHAT = "chat"


_MEDIA_PATH_RE = re.compile(
    r'[A-Za-z]:\\[^\s"\'<>|*?]+\.(?:'
    r'pdf|docx?|pptx?|xlsx?|png|jpe?g|webp|gif|bmp|'
    r'mp3|wav|m4a|aac|flac|ogg|mp4|mov|avi|mkv|webm|zip'
    r')',
    re.I,
)


WEB_HINTS = re.compile(
    r"\b(latest|today|current|news|202[4-9]|search the web|look online|internet|price of|trending)\b",
    re.I,
)
LOCAL_HINTS = re.compile(
    r"\b(my file|my document|in my folder|on my desktop|local file|indexed|watched folder)\b",
    re.I,
)
TOOL_HINTS = re.compile(
    r"\b(list|show|create|write|delete|move|read|search|find|folder|file|directory|"
    r"index|approve|summarize|copy|rename|watched)\b",
    re.I,
)
LIST_DIR_HINTS = re.compile(
    r"\b(list|show|what.+(present|there|inside)|contents of|files in|folders in)\b",
    re.I,
)


def prefers_live_directory_listing(message: str) -> bool:
    return bool(LIST_DIR_HINTS.search(message))
CASUAL = re.compile(
    r"^(hi+|hello|hey|yo|sup|thanks|thank\s*you|ok|okay|bye|good\s*(morning|afternoon|evening|night)|"
    r"how\s+are\s+you|what'?s\s+up)[\s!?.,]*$",
    re.I,
)


def is_casual_message(message: str) -> bool:
    return bool(CASUAL.match(message.strip()))


def needs_agent_tools(message: str, route: Route) -> bool:
    if is_casual_message(message):
        return False
    if route in (Route.LOCAL, Route.WEB, Route.BOTH, Route.MEDIA):
        return True
    return bool(TOOL_HINTS.search(message))


def route_query(message: str, config: AppConfig) -> Route:
    msg = message.strip()
    if _MEDIA_PATH_RE.search(msg):
        return Route.MEDIA
    if LOCAL_HINTS.search(msg) and WEB_HINTS.search(msg):
        return Route.BOTH
    if LOCAL_HINTS.search(msg):
        return Route.LOCAL
    if WEB_HINTS.search(msg) and config.web_search.enabled and config.tavily_api_key:
        return Route.WEB
    return Route.CHAT


def build_routing_context(route: Route, local_context: str = "", web_context: str = "") -> str:
    parts = []
    if route in (Route.LOCAL, Route.BOTH) and local_context:
        parts.append("## Local document context\n" + local_context)
    if route in (Route.WEB, Route.BOTH) and web_context:
        parts.append("## Web search context\n" + web_context)
    if parts:
        return (
            "\n\n".join(parts)
            + "\n\nUse the above context to answer in plain language. "
            "Do not repeat file paths in the body of your answer. "
            "If you mention a source, add one short line at the end: Source: <filename or URL>."
        )
    return ""
