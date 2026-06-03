"""Text quality checks for indexing and RAG retrieval."""

from __future__ import annotations

import string

# Never index or read as plain text
SKIP_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".m4v",
    ".mp3", ".wav", ".flac", ".aac", ".ogg",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".ico",
    ".zip", ".rar", ".7z", ".tar", ".gz",
    ".exe", ".dll", ".bin", ".iso",
    ".db", ".sqlite",
}

READABLE_TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".py", ".json", ".yaml", ".yml",
    ".csv", ".html", ".xml", ".pdf", ".docx",
}


def is_skipped_extension(path: str) -> bool:
    from pathlib import Path
    return Path(path).suffix.lower() in SKIP_EXTENSIONS


def is_readable_text_extension(path: str) -> bool:
    from pathlib import Path
    return Path(path).suffix.lower() in READABLE_TEXT_EXTENSIONS


def text_looks_readable(text: str, min_len: int = 40) -> bool:
    """Reject binary/garbage content."""
    if not text or len(text.strip()) < min_len:
        return len(text.strip()) >= 8 and _ratio_ok(text)
    sample = text[:8000]
    return _ratio_ok(sample)


def _ratio_ok(sample: str) -> bool:
    if not sample:
        return False
    printable = set(string.printable) | {"\n", "\r", "\t"}
    good = sum(1 for c in sample if c in printable)
    ratio = good / len(sample)
    if ratio < 0.85:
        return False
    # Too many replacement chars from bad UTF-8 decode
    if sample.count("\ufffd") > max(3, len(sample) // 200):
        return False
    return True


def sanitize_for_context(text: str, max_len: int = 2000) -> str:
    """Clean text before sending to the LLM."""
    if not text:
        return ""
    if not text_looks_readable(text, min_len=8):
        return "[Content omitted — binary or unreadable file]"
    cleaned = "".join(c if c in (set(string.printable) | {"\n", "\r", "\t"}) else " " for c in text)
    return cleaned[:max_len].strip()
