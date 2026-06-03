"""Messaging adapter interface for remote task control."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class CommandType(str, Enum):
    TASK = "task"
    APPROVE = "approve"
    REJECT = "reject"
    UNKNOWN = "unknown"


@dataclass
class ParsedCommand:
    type: CommandType
    payload: str
    approval_id: str | None = None
    sender: str | None = None


TASK_RE = re.compile(r"^\s*TASK:\s*(.+)$", re.I | re.M)
APPROVE_RE = re.compile(r"^\s*APPROVE:\s*(\S+)\s*$", re.I | re.M)
REJECT_RE = re.compile(r"^\s*REJECT:\s*(\S+)\s*$", re.I | re.M)


def parse_command_body(text: str, sender: str | None = None) -> ParsedCommand:
    text = text.strip()
    m = APPROVE_RE.search(text)
    if m:
        return ParsedCommand(CommandType.APPROVE, "", approval_id=m.group(1).strip(), sender=sender)
    m = REJECT_RE.search(text)
    if m:
        return ParsedCommand(CommandType.REJECT, "", approval_id=m.group(1).strip(), sender=sender)
    m = TASK_RE.search(text)
    if m:
        return ParsedCommand(CommandType.TASK, m.group(1).strip(), sender=sender)
    if text.upper().startswith("TASK "):
        return ParsedCommand(CommandType.TASK, text[5:].strip(), sender=sender)
    return ParsedCommand(CommandType.UNKNOWN, text, sender=sender)


class MessagingAdapter(ABC):
    name: str = "base"

    @abstractmethod
    async def send(self, to: str, message: str) -> None:
        ...

    @abstractmethod
    async def start_listening(self, on_command) -> None:
        ...
