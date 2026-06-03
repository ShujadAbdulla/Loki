"""Store API keys via OS keyring when available."""

from __future__ import annotations

import keyring

SERVICE = "PersonalAgent"


def get_secret(name: str) -> str | None:
    try:
        return keyring.get_password(SERVICE, name)
    except Exception:
        return None


def set_secret(name: str, value: str) -> None:
    keyring.set_password(SERVICE, name, value)


def delete_secret(name: str) -> None:
    try:
        keyring.delete_password(SERVICE, name)
    except Exception:
        pass
