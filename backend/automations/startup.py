"""Morning briefing on startup."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from backend.config import get_data_dir


class StartupBriefing:
    def __init__(self, config, audit, store, gmail=None, outlook=None):
        self._config = config
        self._audit = audit
        self._store = store
        self._gmail = gmail
        self._outlook = outlook
        self._state_file = get_data_dir() / "last_run_state.json"
        self._briefing_text = ""

    @property
    def text(self) -> str:
        return self._briefing_text

    def get_last_run(self) -> datetime | None:
        if not self._state_file.exists():
            return None
        try:
            data = json.loads(self._state_file.read_text())
            return datetime.fromisoformat(data["last_run"])
        except Exception:
            return None

    def save_current_run(self):
        self._state_file.write_text(json.dumps({
            "last_run": datetime.now(timezone.utc).isoformat()
        }))

    def generate_briefing(self) -> str:
        if not getattr(self._config, "startup", None) or not self._config.startup.catchup_enabled:
            self.save_current_run()
            return ""

        last = self.get_last_run()
        if not last:
            self.save_current_run()
            self._briefing_text = "Welcome to Loki! I'm ready to help. Add a watched folder in Settings to get started."
            return self._briefing_text

        parts = []
        delta = datetime.now(timezone.utc) - last
        hours = int(delta.total_seconds() / 3600)
        if hours < 1:
            self.save_current_run()
            return ""

        parts.append(f"Good morning! Here's what happened while you were away ({hours}h ago):")

        changed = self._check_changed_files(last)
        if changed:
            parts.append(f"{len(changed)} file(s) changed in your watched folders")
            for f in changed[:3]:
                parts.append(f"   - {f}")

        if self._gmail and self._gmail.connected:
            try:
                emails = self._gmail.search(f"after:{last.strftime('%Y/%m/%d')}", n=10)
                if emails:
                    parts.append(f"{len(emails)} new email(s) in Gmail")
            except Exception:
                pass

        if self._outlook and self._outlook.connected:
            try:
                emails = self._outlook.read_inbox(10)
                if emails:
                    parts.append(f"{len(emails)} recent email(s) in Outlook")
            except Exception:
                pass

        self.save_current_run()
        self._briefing_text = "\n".join(parts) if len(parts) > 1 else ""
        if self._briefing_text:
            self._audit.log("startup_briefing", {"hours": hours}, category="AI_ACTION")
        return self._briefing_text

    def _check_changed_files(self, since: datetime) -> list[str]:
        changed = []
        for root in self._config.watched_paths:
            p = Path(root)
            if not p.exists():
                continue
            for f in p.rglob("*"):
                if f.is_file():
                    mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                    if mtime > since:
                        changed.append(f.name)
        return changed[:10]
