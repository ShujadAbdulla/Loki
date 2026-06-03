"""Human-in-the-loop approval queue for destructive operations."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"


@dataclass
class ApprovalRequest:
    id: str
    tool_name: str
    args: dict[str, Any]
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result: str | None = None


class ApprovalQueue:
    def __init__(self) -> None:
        self._pending: dict[str, ApprovalRequest] = {}
        self._resolved: dict[str, ApprovalRequest] = {}

    def create(self, tool_name: str, args: dict[str, Any]) -> ApprovalRequest:
        req = ApprovalRequest(id=str(uuid.uuid4())[:8], tool_name=tool_name, args=args)
        self._pending[req.id] = req
        return req

    def get(self, approval_id: str) -> ApprovalRequest | None:
        return self._pending.get(approval_id) or self._resolved.get(approval_id)

    def list_pending(self) -> list[ApprovalRequest]:
        return [r for r in self._pending.values() if r.status == ApprovalStatus.PENDING]

    def approve(self, approval_id: str) -> ApprovalRequest | None:
        req = self._pending.pop(approval_id, None)
        if not req:
            return None
        req.status = ApprovalStatus.APPROVED
        self._resolved[approval_id] = req
        return req

    def reject(self, approval_id: str) -> ApprovalRequest | None:
        req = self._pending.pop(approval_id, None)
        if not req:
            return None
        req.status = ApprovalStatus.REJECTED
        self._resolved[approval_id] = req
        return req
