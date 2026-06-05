"""Build LangChain tools for the agent."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from backend.config import AppConfig
from backend.security.allowlist import PathAllowlist
from backend.security.approvals import ApprovalQueue
from backend.security.audit import AuditLog
from backend.rag.store import VectorStore
from backend.tools.fs_tools import FileTools
from backend.tools.gen_tool import GenTools
from backend.tools.media_tool import MediaTool
from backend.tools.rag_search import RagSearchTool
from backend.tools.web_search import WebSearchTool


class ReadFileInput(BaseModel):
    path: str = Field(description="Absolute or relative path within watched folders")


class WriteFileInput(BaseModel):
    path: str = Field(description="Path to write")
    content: str = Field(description="File content")
    approval_id: str | None = Field(default=None, description="Approval ID if already approved")


class DeleteFileInput(BaseModel):
    path: str
    approval_id: str | None = None
    dry_run: bool = False


class DeleteFolderInput(BaseModel):
    path: str = Field(description="Full path to the folder to delete")
    approval_id: str | None = None
    dry_run: bool = False
    recursive: bool = Field(default=True, description="Delete folder and all contents")


class MoveFileInput(BaseModel):
    src: str
    dest: str
    approval_id: str | None = None


class ListDirInput(BaseModel):
    path: str = Field(
        default="",
        description=(
            "Full Windows path under a watched folder, e.g. C:\\Users\\You\\Desktop\\testbyloki. "
            "Leave empty to list the first watched folder."
        ),
    )


class CreateFolderInput(BaseModel):
    path: str = Field(description="Full path of the new folder inside a watched directory")
    approval_id: str | None = Field(default=None, description="Approval ID if already approved")


class SearchQueryInput(BaseModel):
    query: str = Field(description="Search query")


class ProcessMediaInput(BaseModel):
    path: str = Field(description="Path to media file (image, audio, video, pdf, office doc)")


class GenerateInput(BaseModel):
    prompt: str = Field(description="Description of document to generate")


def build_tools(
    config: AppConfig,
    allowlist: PathAllowlist,
    approvals: ApprovalQueue,
    audit: AuditLog,
    store: VectorStore,
    fs: FileTools | None = None,
    llm=None,
) -> list[StructuredTool]:
    if fs is None:
        fs = FileTools(
            allowlist,
            approvals,
            audit,
            set(config.security.require_approval_for),
        )
    web = WebSearchTool(config, audit)
    rag = RagSearchTool(store, config, audit)
    media = MediaTool(config, audit, store, allowlist)
    gen = GenTools(config, audit, llm) if llm else None

    tools: list[StructuredTool] = [
        StructuredTool.from_function(
            name="process_media",
            description=(
                "Process images, audio, video, PDFs, and office files using hybrid pipeline. "
                "Use for .mp4, .mp3, .png, .jpg, scanned PDFs, .pptx, .xlsx."
            ),
            func=media.process_media,
            args_schema=ProcessMediaInput,
        ),
        StructuredTool.from_function(
            name="read_file",
            description="Read text from txt, md, pdf, docx, json, etc. For media files use process_media instead.",
            func=fs.read_file,
            args_schema=ReadFileInput,
        ),
        StructuredTool.from_function(
            name="write_file",
            description="Write content to a file (creates parent folders automatically). May require user approval.",
            func=fs.write_file,
            args_schema=WriteFileInput,
        ),
        StructuredTool.from_function(
            name="create_folder",
            description="Create a new folder inside watched directories. Path must be under a watched folder. May require user approval.",
            func=fs.create_folder,
            args_schema=CreateFolderInput,
        ),
        StructuredTool.from_function(
            name="delete_file",
            description="Delete a file or folder (folders deleted recursively with all contents). Requires approval.",
            func=fs.delete_file,
            args_schema=DeleteFileInput,
        ),
        StructuredTool.from_function(
            name="delete_folder",
            description=(
                "Delete a folder and optionally all contents (recursive=true). "
                "Use this when the user asks to delete a directory. Requires approval."
            ),
            func=fs.delete_folder,
            args_schema=DeleteFolderInput,
        ),
        StructuredTool.from_function(
            name="move_file",
            description="Move/rename a file within watched folders.",
            func=fs.move_file,
            args_schema=MoveFileInput,
        ),
        StructuredTool.from_function(
            name="list_directory",
            description=(
                "List files and subfolders in a watched directory. "
                "Use the exact Windows path from the watched folders list. "
                "If the user does not name a path, call with path='' (empty string)."
            ),
            func=fs.list_directory,
            args_schema=ListDirInput,
        ),
        StructuredTool.from_function(
            name="search_local_documents",
            description=(
                "Search text inside indexed documents (PDF, docx, txt). "
                "Do NOT use for listing folder contents — use list_directory instead."
            ),
            func=rag.search,
            args_schema=SearchQueryInput,
        ),
    ]

    if web.available:
        tools.append(
            StructuredTool.from_function(
                name="web_search",
                description="Search the public web for current information. Returns URLs and snippets.",
                func=web.search,
                args_schema=SearchQueryInput,
            )
        )

    if gen:
        for name, desc, fn in [
            ("generate_docx", "Generate a Word document (.docx) from a prompt.", gen.generate_docx),
            ("generate_pptx", "Generate a PowerPoint (.pptx) from a prompt.", gen.generate_pptx),
            ("generate_pdf", "Generate a PDF document from a prompt.", gen.generate_pdf),
            ("generate_xlsx", "Generate an Excel spreadsheet (.xlsx) from a prompt.", gen.generate_xlsx),
        ]:
            tools.append(StructuredTool.from_function(
                name=name, description=desc, func=fn, args_schema=GenerateInput,
            ))

    return tools
