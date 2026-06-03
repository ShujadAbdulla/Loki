"""Restrict file operations to user-approved directories."""

from __future__ import annotations

from pathlib import Path


class PathAllowlist:
    def __init__(self, roots: list[str] | None = None) -> None:
        self._roots: list[Path] = []
        if roots:
            self.set_roots(roots)

    def set_roots(self, roots: list[str]) -> None:
        resolved: list[Path] = []
        for r in roots:
            p = Path(r).expanduser().resolve()
            if p.exists() and p.is_dir():
                resolved.append(p)
        self._roots = resolved

    @property
    def roots(self) -> list[Path]:
        return list(self._roots)

    def _normalize(self, path: str | Path) -> Path | None:
        try:
            return Path(path).expanduser().resolve(strict=False)
        except (OSError, ValueError):
            return None

    def is_allowed(self, path: str | Path) -> bool:
        if not self._roots:
            return False
        target = self._normalize(path)
        if target is None:
            return False
        for root in self._roots:
            try:
                target.relative_to(root)
                return True
            except ValueError:
                continue
        return False

    def resolve_allowed(self, path: str | Path) -> Path:
        target = self._normalize(path)
        if target is None or not self.is_allowed(target):
            raise PermissionError(f"Path not in allowlist: {path}")
        return target
