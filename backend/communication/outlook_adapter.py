"""Outlook integration via MSAL device code flow."""

from __future__ import annotations

import json
from typing import Optional

import keyring
import requests

KEYRING_SERVICE = "LokiOutlook"
KEYRING_USER = "oauth_tokens"
SCOPES = ["Mail.Read", "Mail.Send", "Mail.ReadWrite", "Calendars.Read"]
GRAPH = "https://graph.microsoft.com/v1.0"


class OutlookAdapter:
    def __init__(self, config, audit):
        self._config = config
        self._audit = audit
        self._device_flow: dict | None = None

    @property
    def connected(self) -> bool:
        return self._load_tokens() is not None

    def _app(self):
        import msal
        return msal.PublicClientApplication(
            self._config.microsoft_client_id,
            authority="https://login.microsoftonline.com/common",
        )

    def start_device_flow(self) -> dict:
        app = self._app()
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise RuntimeError("Device flow failed")
        self._device_flow = flow
        return {
            "message": flow.get("message", ""),
            "user_code": flow.get("user_code", ""),
            "verification_uri": flow.get("verification_uri", "https://microsoft.com/devicelogin"),
        }

    def complete_device_flow(self) -> bool:
        if not self._device_flow:
            raise RuntimeError("No device flow started")
        app = self._app()
        result = app.acquire_token_by_device_flow(self._device_flow)
        if "access_token" not in result:
            raise RuntimeError(result.get("error_description", "Auth failed"))
        keyring.set_password(KEYRING_SERVICE, KEYRING_USER, json.dumps(result))
        self._device_flow = None
        self._audit.log("outlook_connected", {}, category="EMAIL")
        return True

    def _load_tokens(self) -> Optional[dict]:
        raw = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
        return json.loads(raw) if raw else None

    def _headers(self) -> dict:
        tokens = self._load_tokens()
        if not tokens:
            raise RuntimeError("Outlook not connected")
        return {"Authorization": f"Bearer {tokens['access_token']}"}

    def read_inbox(self, n: int = 20) -> list[dict]:
        r = requests.get(
            f"{GRAPH}/me/messages?$top={n}&$orderby=receivedDateTime desc",
            headers=self._headers(), timeout=15,
        )
        r.raise_for_status()
        emails = []
        for msg in r.json().get("value", []):
            emails.append({
                "id": msg["id"],
                "subject": msg.get("subject", ""),
                "from": msg.get("from", {}).get("emailAddress", {}).get("address", ""),
                "date": msg.get("receivedDateTime", ""),
                "snippet": msg.get("bodyPreview", ""),
            })
        self._audit.log("outlook_read_inbox", {"count": len(emails)}, category="EMAIL")
        return emails

    def search(self, query: str, n: int = 20) -> list[dict]:
        r = requests.get(
            f"{GRAPH}/me/messages?$search=\"{query}\"&$top={n}",
            headers=self._headers(), timeout=15,
        )
        r.raise_for_status()
        return [
            {
                "id": m["id"],
                "subject": m.get("subject", ""),
                "from": m.get("from", {}).get("emailAddress", {}).get("address", ""),
                "date": m.get("receivedDateTime", ""),
                "snippet": m.get("bodyPreview", ""),
            }
            for m in r.json().get("value", [])
        ]

    def get_email(self, email_id: str) -> dict:
        r = requests.get(f"{GRAPH}/me/messages/{email_id}", headers=self._headers(), timeout=15)
        r.raise_for_status()
        msg = r.json()
        return {
            "id": email_id,
            "subject": msg.get("subject", ""),
            "from": msg.get("from", {}).get("emailAddress", {}).get("address", ""),
            "date": msg.get("receivedDateTime", ""),
            "body": msg.get("body", {}).get("content", ""),
        }

    def send_email(self, to: str, subject: str, body: str) -> bool:
        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": to}}],
            }
        }
        r = requests.post(f"{GRAPH}/me/sendMail", headers=self._headers(), json=payload, timeout=15)
        r.raise_for_status()
        self._audit.log("outlook_sent", {"to": to, "subject": subject[:50]}, category="EMAIL")
        return True

    def get_calendar_events(self, n: int = 10) -> list[dict]:
        r = requests.get(
            f"{GRAPH}/me/events?$top={n}&$orderby=start/dateTime",
            headers=self._headers(), timeout=15,
        )
        r.raise_for_status()
        return [
            {
                "subject": e.get("subject", ""),
                "start": e.get("start", {}).get("dateTime", ""),
                "end": e.get("end", {}).get("dateTime", ""),
            }
            for e in r.json().get("value", [])
        ]
