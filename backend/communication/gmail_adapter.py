"""Gmail integration via OAuth2 — tokens in OS keychain."""

from __future__ import annotations

import base64
import json
from email.mime.text import MIMEText
from typing import Optional

import keyring

KEYRING_SERVICE = "LokiGmail"
KEYRING_USER = "oauth_tokens"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]


class GmailAdapter:
    def __init__(self, config, audit):
        self._config = config
        self._audit = audit

    @property
    def connected(self) -> bool:
        return self._load_tokens() is not None

    def _client_config(self) -> dict:
        return {
            "installed": {
                "client_id": self._config.google_client_id,
                "client_secret": self._config.google_client_secret or "",
                "redirect_uris": ["http://127.0.0.1:8787/gmail/callback"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }

    def get_auth_url(self) -> str:
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_config(self._client_config(), scopes=SCOPES)
        flow.redirect_uri = "http://127.0.0.1:8787/gmail/callback"
        auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
        return auth_url

    def handle_callback(self, code: str) -> bool:
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_config(self._client_config(), scopes=SCOPES)
        flow.redirect_uri = "http://127.0.0.1:8787/gmail/callback"
        flow.fetch_token(code=code)
        creds = flow.credentials
        token_data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes) if creds.scopes else SCOPES,
        }
        keyring.set_password(KEYRING_SERVICE, KEYRING_USER, json.dumps(token_data))
        self._audit.log("gmail_connected", {}, category="EMAIL")
        return True

    def _load_tokens(self) -> Optional[dict]:
        raw = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
        return json.loads(raw) if raw else None

    def _get_service(self):
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        token_data = self._load_tokens()
        if not token_data:
            raise RuntimeError("Gmail not connected")
        creds = Credentials(**token_data)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_data["token"] = creds.token
            keyring.set_password(KEYRING_SERVICE, KEYRING_USER, json.dumps(token_data))
        return build("gmail", "v1", credentials=creds)

    def read_inbox(self, n: int = 20) -> list[dict]:
        service = self._get_service()
        results = service.users().messages().list(userId="me", maxResults=n, labelIds=["INBOX"]).execute()
        emails = []
        for msg_ref in results.get("messages", []):
            msg = service.users().messages().get(userId="me", id=msg_ref["id"], format="full").execute()
            headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
            emails.append({
                "id": msg["id"],
                "subject": headers.get("Subject", ""),
                "from": headers.get("From", ""),
                "date": headers.get("Date", ""),
                "snippet": msg.get("snippet", ""),
            })
        self._audit.log("gmail_read_inbox", {"count": len(emails)}, category="EMAIL")
        return emails

    def search(self, query: str, n: int = 20) -> list[dict]:
        service = self._get_service()
        results = service.users().messages().list(userId="me", q=query, maxResults=n).execute()
        emails = []
        for msg_ref in results.get("messages", []):
            msg = service.users().messages().get(
                userId="me", id=msg_ref["id"], format="metadata",
                metadataHeaders=["Subject", "From", "Date"],
            ).execute()
            headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
            emails.append({
                "id": msg["id"],
                "subject": headers.get("Subject", ""),
                "from": headers.get("From", ""),
                "date": headers.get("Date", ""),
                "snippet": msg.get("snippet", ""),
            })
        return emails

    def get_email(self, email_id: str) -> dict:
        service = self._get_service()
        msg = service.users().messages().get(userId="me", id=email_id, format="full").execute()
        headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
        return {
            "id": email_id,
            "subject": headers.get("Subject", ""),
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "date": headers.get("Date", ""),
            "body": self._extract_body(msg["payload"]),
        }

    def _extract_body(self, payload: dict) -> str:
        if payload.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
        return ""

    def send_email(self, to: str, subject: str, body: str) -> bool:
        service = self._get_service()
        msg = MIMEText(body)
        msg["to"] = to
        msg["subject"] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        self._audit.log("gmail_sent", {"to": to, "subject": subject[:50]}, category="EMAIL")
        return True

    def index_emails(self, store, n: int = 500):
        emails = self.read_inbox(n)
        for email in emails:
            text = f"Subject: {email['subject']}\nFrom: {email['from']}\nDate: {email['date']}\n\n{email['snippet']}"
            store.upsert_chunks(f"email::{email['id']}", [text], 0)
        self._audit.log("gmail_indexed", {"count": len(emails)}, category="EMAIL")
