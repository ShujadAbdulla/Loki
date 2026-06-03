"""Email command inbox (IMAP poll + SMTP send)."""

from __future__ import annotations

import asyncio
import email
import email.utils
import imaplib
import smtplib
import os
from email.mime.text import MIMEText
from typing import Callable, Awaitable

from backend.remote.messaging import MessagingAdapter, parse_command_body


class EmailAdapter(MessagingAdapter):
    name = "email"

    def __init__(
        self,
        allowed_senders: list[str],
        command_folder: str = "AgentCommands",
    ) -> None:
        self._allowed = {s.lower() for s in allowed_senders}
        self._folder = command_folder
        self._addr = os.getenv("EMAIL_ADDRESS", "")
        self._password = os.getenv("EMAIL_PASSWORD", "")
        self._imap_host = os.getenv("IMAP_HOST", "imap.gmail.com")
        self._smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self._on_command: Callable | None = None
        self._running = False

    @property
    def enabled(self) -> bool:
        return bool(self._addr and self._password and self._allowed)

    async def send(self, to: str, message: str) -> None:
        if not self._addr:
            return
        msg = MIMEText(message)
        msg["Subject"] = "Loki"
        msg["From"] = self._addr
        msg["To"] = to

        def _send():
            with smtplib.SMTP(self._smtp_host, 587) as s:
                s.starttls()
                s.login(self._addr, self._password)
                s.send_message(msg)

        await asyncio.to_thread(_send)

    def _poll_once(self) -> list[tuple[str, str, str]]:
        found: list[tuple[str, str, str]] = []
        mail = imaplib.IMAP4_SSL(self._imap_host)
        mail.login(self._addr, self._password)
        mail.select(self._folder)
        _, data = mail.search(None, "UNSEEN")
        for num in (data[0] or b"").split():
            _, msg_data = mail.fetch(num, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            sender = email.utils.parseaddr(msg.get("From", ""))[1].lower()
            if self._allowed and sender not in self._allowed:
                continue
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode(errors="replace")
                        break
            else:
                body = msg.get_payload(decode=True).decode(errors="replace")
            found.append((sender, body, msg.get("Subject", "")))
            mail.store(num, "+FLAGS", "\\Seen")
        mail.logout()
        return found

    async def start_listening(self, on_command: Callable[[object], Awaitable[None]]) -> None:
        self._on_command = on_command
        self._running = True
        while self._running:
            if not self.enabled:
                await asyncio.sleep(30)
                continue
            try:
                items = await asyncio.to_thread(self._poll_once)
                for sender, body, _subj in items:
                    cmd = parse_command_body(body, sender=sender)
                    if cmd.type.value != "unknown":
                        await on_command(cmd)
            except Exception:
                pass
            await asyncio.sleep(60)

    def stop(self) -> None:
        self._running = False
