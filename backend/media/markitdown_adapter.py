"""Thin wrapper around MarkItDown."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def convert_to_text(path: Path, audit=None) -> Optional[str]:
    try:
        from markitdown import MarkItDown
        md = MarkItDown()
        result = md.convert(str(path))
        return result.text_content if result and result.text_content else None
    except Exception as e:
        if audit:
            audit.log("markitdown_error", {"path": str(path), "error": str(e)}, category="FILE")
        return None
