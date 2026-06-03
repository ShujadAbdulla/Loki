"""File CRUD tools with allowlist and approval gates."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from backend.security.allowlist import PathAllowlist
    from backend.security.approvals import ApprovalQueue, ApprovalRequest, ApprovalStatus
    from backend.security.audit import AuditLog
else:
    from backend.security.approvals import ApprovalRequest, ApprovalStatus


_PLACEHOLDER_MARKERS = (
    "/path/to",
    "/watched/",
    "your/folder",
    "your folder",
    "<path>",
    "{path}",
    "path/to",
)


class FileTools:
    def __init__(
        self,
        allowlist: "PathAllowlist",
        approvals: "ApprovalQueue",
        audit: "AuditLog",
        require_approval: set[str],
        on_approval_needed: Callable[[str, dict], str] | None = None,
    ) -> None:
        self._allowlist = allowlist
        self._approvals = approvals
        self._audit = audit
        self._require_approval = require_approval
        self._on_approval_needed = on_approval_needed

    def _default_watched_path(self) -> str | None:
        roots = self._allowlist.roots
        return str(roots[0]) if roots else None

    def _resolve_user_path(self, path: str) -> str:
        """Map empty or placeholder paths to the user's real watched folder."""
        raw = (path or "").strip().strip('"').strip("'")
        if not raw or raw in (".", "./"):
            default = self._default_watched_path()
            if default:
                return default
            raise PermissionError("No watched folders configured. Add one in Settings.")
        lower = raw.lower().replace("\\", "/")
        if lower.startswith("/") and ":" not in raw:
            default = self._default_watched_path()
            if default:
                return default
        for marker in _PLACEHOLDER_MARKERS:
            if marker in lower:
                default = self._default_watched_path()
                if default:
                    return default
                break
        p = Path(raw)
        # Relative names like "newfolder" → under first watched folder
        if not p.is_absolute() and (len(raw) < 2 or raw[1] != ":"):
            default = self._default_watched_path()
            if default:
                return str((Path(default) / p).resolve(strict=False))
        return raw

    def _resolve_allowed_path(self, path: str) -> Path:
        """Resolve user path string to an allowed Path."""
        return self._allowlist.resolve_allowed(self._resolve_user_path(path))

    def _needs_approval(self, tool: str) -> bool:
        return tool in self._require_approval

    def _approval_args(self, tool: str, path: str, content: str | None = None, **extra) -> dict:
        """Build args stored for approval UI and execute_approved (must include full payload)."""
        if tool == "write_file":
            return {"path": path, "content": content or "", "content_len": len(content or "")}
        return {"path": path, **extra}

    def _consume_approval(self, approval_id: str) -> ApprovalRequest | None:
        req = self._approvals.get(approval_id)
        if not req or req.status not in (ApprovalStatus.APPROVED, ApprovalStatus.PENDING):
            return None
        if req.status == ApprovalStatus.EXECUTED:
            return None
        req.status = ApprovalStatus.EXECUTED
        return req

    def _check_approval(self, tool: str, args: dict, approval_id: str | None) -> str | None:
        if not self._needs_approval(tool):
            return None
        if approval_id:
            req = self._approvals.get(approval_id)
            if req and req.status == ApprovalStatus.EXECUTED:
                return f"Error: approval {approval_id} was already used. Submit a new request."
            if req and req.status == ApprovalStatus.APPROVED:
                return None
        req = self._approvals.create(tool, args)
        if self._on_approval_needed:
            return self._on_approval_needed(req.id, {"tool": tool, **args})
        return f"APPROVAL_REQUIRED:{req.id}"

    def read_file(self, path: str) -> str:
        from backend.rag.text_utils import is_readable_text_extension, is_skipped_extension

        try:
            p = self._resolve_allowed_path(path)
        except PermissionError as e:
            return str(e)
        self._audit.log("read_file", {"path": str(p)})
        if not p.exists():
            return f"Error: file does not exist: {p}"
        if p.is_dir():
            return f"Error: {p} is a folder. Use list_directory to list contents."
        if not p.is_file():
            return f"Error: cannot read: {p}"
        suffix = p.suffix.lower()
        if is_skipped_extension(str(p)) or suffix in {".mp4", ".mp3", ".exe"}:
            return (
                f"Error: cannot read {suffix} files as text (video/audio/binary). "
                f"Use list_directory to see the file name only."
            )
        if not is_readable_text_extension(str(p)):
            return f"Error: unsupported type {suffix or '(no extension)'}. Supported: txt, md, pdf, docx, json, etc."
        try:
            if suffix == ".pdf":
                from backend.rag.extract import extract_text
                text = extract_text(p)
            elif suffix == ".docx":
                from backend.rag.extract import extract_text
                text = extract_text(p)
            else:
                text = p.read_text(encoding="utf-8", errors="replace")
            from backend.rag.text_utils import text_looks_readable, sanitize_for_context
            if not text_looks_readable(text, min_len=10):
                return f"Error: file appears to be binary or unreadable: {p}"
            return sanitize_for_context(text, max_len=50000)
        except Exception as e:
            return f"Error reading file: {e}"

    def write_file(self, path: str, content: str, approval_id: str | None = None) -> str:
        try:
            p = self._resolve_allowed_path(path)
        except PermissionError as e:
            return str(e)
        stored = self._approval_args("write_file", str(p), content)
        blocked = self._check_approval("write_file", stored, approval_id)
        if blocked:
            return blocked
        if approval_id:
            req = self._approvals.get(approval_id)
            if req and "content" in req.args:
                content = req.args["content"]
                p = Path(req.args.get("path", p))
            self._consume_approval(approval_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        self._audit.log("write_file", {"path": str(p), "bytes": len(content)})
        return f"Wrote {len(content)} bytes to {p}"

    def _perform_delete(
        self,
        p: Path,
        *,
        dry_run: bool,
        recursive: bool,
        audit_action: str,
    ) -> str:
        if dry_run:
            kind = "folder" if p.is_dir() else "file"
            return f"[dry-run] Would delete {kind}: {p}"
        if not p.exists():
            return f"Error: path does not exist: {p}"
        if p.is_dir():
            if not recursive and any(p.iterdir()):
                return f"Error: folder is not empty: {p}. Use recursive delete."
            shutil.rmtree(p) if recursive else p.rmdir()
            self._audit.log(audit_action, {"path": str(p), "recursive": recursive})
            return f"Deleted folder (and contents): {p}"
        p.unlink()
        self._audit.log(audit_action, {"path": str(p)})
        return f"Deleted file: {p}"

    def delete_file(self, path: str, approval_id: str | None = None, dry_run: bool = False) -> str:
        """Delete a file or folder (folders removed recursively)."""
        try:
            p = self._resolve_allowed_path(path)
        except PermissionError as e:
            return str(e)
        if not approval_id:
            if not p.exists():
                return f"Error: nothing to delete — path does not exist:\n  {p}"
            args = {"path": str(p), "dry_run": dry_run, "kind": "folder" if p.is_dir() else "file"}
            blocked = self._check_approval("delete_file", args, None)
            if blocked:
                return blocked
        if approval_id:
            req = self._approvals.get(approval_id)
            if req and req.args.get("path"):
                p = Path(req.args["path"])
            self._consume_approval(approval_id)
        return self._perform_delete(p, dry_run=dry_run, recursive=True, audit_action="delete_file")

    def delete_folder(
        self,
        path: str,
        approval_id: str | None = None,
        dry_run: bool = False,
        recursive: bool = True,
    ) -> str:
        """Delete a directory inside watched folders (recursive by default)."""
        try:
            p = self._resolve_allowed_path(path)
        except PermissionError as e:
            return str(e)
        if p.exists() and p.is_file():
            return f"Error: {p} is a file. Use delete_file instead."
        if not approval_id:
            if not p.exists():
                return f"Error: folder does not exist:\n  {p}"
            args = {"path": str(p), "dry_run": dry_run, "recursive": recursive}
            blocked = self._check_approval("delete_folder", args, None)
            if blocked:
                return blocked
        if approval_id:
            req = self._approvals.get(approval_id)
            if req and req.args.get("path"):
                p = Path(req.args["path"])
            self._consume_approval(approval_id)
        return self._perform_delete(p, dry_run=dry_run, recursive=recursive, audit_action="delete_folder")

    def move_file(self, src: str, dest: str, approval_id: str | None = None) -> str:
        args = {"src": src, "dest": dest}
        blocked = self._check_approval("move_file", args, approval_id)
        if blocked:
            return blocked
        s = self._allowlist.resolve_allowed(self._resolve_user_path(src))
        d = self._allowlist.resolve_allowed(self._resolve_user_path(dest))
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(s), str(d))
        self._audit.log("move_file", {"src": str(s), "dest": str(d)})
        return f"Moved {s} -> {d}"

    def create_folder(self, path: str, approval_id: str | None = None) -> str:
        """Create a directory (and parents) inside watched folders."""
        args = {"path": path}
        blocked = self._check_approval("create_folder", args, approval_id)
        if blocked:
            return blocked
        try:
            p = self._allowlist.resolve_allowed(self._resolve_user_path(path))
        except PermissionError as e:
            return str(e)
        if p.exists() and p.is_file():
            return f"Error: path is a file, not a folder: {path}"
        if p.exists() and p.is_dir():
            return f"Folder already exists: {p}"
        p.mkdir(parents=True, exist_ok=True)
        self._audit.log("create_folder", {"path": str(p)})
        return f"Created folder: {p}"

    def list_directory(self, path: str = "") -> str:
        try:
            p = self._resolve_allowed_path(path)
        except PermissionError as e:
            roots = self._allowlist.roots
            hint = "\n".join(f"  - {r}" for r in roots) if roots else "  (none — add a folder in Settings)"
            return f"{e}\n\nUse one of these watched folders:\n{hint}"
        if not p.is_dir():
            return f"Error: not a directory: {p}"
        entries = []
        for child in sorted(p.iterdir())[:200]:
            kind = "dir" if child.is_dir() else "file"
            entries.append(f"[{kind}] {child.name}")
        self._audit.log("list_directory", {"path": str(p)})
        return "\n".join(entries) if entries else "(empty)"

    def execute_approved(self, req: ApprovalRequest) -> str:
        """Run a previously approved tool call."""
        if req.status != ApprovalStatus.APPROVED:
            return "Error: approval not granted"
        if req.status == ApprovalStatus.EXECUTED:
            return "Error: already executed"
        aid = req.id
        name = req.tool_name
        args = req.args
        if name == "write_file":
            path = args["path"]
            content = args.get("content", "")
            if not content and args.get("content_len", 0) > 0:
                return "Error: file content was lost; please ask the agent to write the file again."
            result = self.write_file(path, content, approval_id=aid)
            return result
        if name == "create_folder":
            return self.create_folder(args["path"], approval_id=aid)
        if name == "delete_file":
            return self.delete_file(
                args["path"],
                approval_id=aid,
                dry_run=args.get("dry_run", False),
            )
        if name == "delete_folder":
            return self.delete_folder(
                args["path"],
                approval_id=aid,
                dry_run=args.get("dry_run", False),
                recursive=args.get("recursive", True),
            )
        if name == "move_file":
            return self.move_file(args["src"], args["dest"], approval_id=aid)
        return f"Error: unknown tool {name}"
