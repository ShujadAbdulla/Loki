"""Extract plain text from supported document types."""

from __future__ import annotations

from pathlib import Path

from backend.rag.text_utils import SKIP_EXTENSIONS, is_readable_text_extension, text_looks_readable

SUPPORTED = {".txt", ".md", ".markdown", ".py", ".json", ".yaml", ".yml", ".csv", ".html", ".xml"}


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in SKIP_EXTENSIONS:
        raise ValueError(f"Cannot extract text from {suffix} files")
    if suffix in SUPPORTED or suffix == "":
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        parts = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        return "\n".join(parts)
    if suffix == ".docx":
        from docx import Document

        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs)
    raise ValueError(f"Unsupported file type: {suffix}")


def is_indexable(path: Path) -> bool:
    if not path.is_file():
        return False
    suffix = path.suffix.lower()
    if suffix in SKIP_EXTENSIONS:
        return False
    if suffix not in SUPPORTED and suffix not in {".pdf", ".docx"}:
        return False
    return True
