"""Telegram bot for remote TASK / APPROVE commands."""

from __future__ import annotations

import asyncio
import os
from typing import Callable, Awaitable

from backend.remote.messaging import MessagingAdapter, parse_command_body


class TelegramAdapter(MessagingAdapter):
    name = "telegram"

    def __init__(self, allowed_chat_ids: list[int]) -> None:
        self._token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._allowed = set(allowed_chat_ids)
        self._app = None
        self._running = False

    @property
    def enabled(self) -> bool:
        return bool(self._token)

    async def send(self, to: str, message: str) -> None:
        if not self.enabled:
            return
        from telegram import Bot

        bot = Bot(self._token)
        await bot.send_message(chat_id=int(to), text=message[:4000])

    async def start_listening(self, on_command: Callable[[object], Awaitable[None]]) -> None:
        if not self.enabled:
            return
        from telegram.ext import Application, MessageHandler, filters, ContextTypes

        async def handle(update, context: ContextTypes.DEFAULT_TYPE):
            if not update.message or not update.message.text:
                return
            chat_id = update.effective_chat.id if update.effective_chat else None
            if self._allowed and chat_id not in self._allowed:
                await update.message.reply_text("Unauthorized chat.")
                return
            cmd = parse_command_body(update.message.text, sender=str(chat_id))
            if cmd.type.value == "unknown":
                await update.message.reply_text(
                    "Send:\nTASK: your goal\nAPPROVE: <id>\nREJECT: <id>"
                )
                return
            await on_command(cmd)
            if cmd.type.value == "task":
                await update.message.reply_text("Task queued.")

        self._app = Application.builder().token(self._token).build()
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
        self._running = True
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()
        while self._running:
            await asyncio.sleep(1)

    def stop(self) -> None:
        self._running = False
