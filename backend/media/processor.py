"""Hybrid media pipeline: MarkItDown → LLM judge → Vision fallback."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from backend.media.markitdown_adapter import convert_to_text

MEDIA_EXTENSIONS = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".doc", ".ppt", ".xls",
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp",
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg",
    ".mp4", ".mov", ".avi", ".mkv", ".webm",
    ".zip", ".txt", ".md", ".csv", ".json", ".yaml", ".yml",
    ".html", ".xml", ".py",
}


class MediaType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    OFFICE = "office"
    PDF = "pdf"
    ARCHIVE = "archive"
    UNKNOWN = "unknown"


MEDIA_MAP = {
    ".pdf": MediaType.PDF,
    ".docx": MediaType.OFFICE, ".pptx": MediaType.OFFICE, ".xlsx": MediaType.OFFICE,
    ".doc": MediaType.OFFICE, ".ppt": MediaType.OFFICE, ".xls": MediaType.OFFICE,
    ".png": MediaType.IMAGE, ".jpg": MediaType.IMAGE, ".jpeg": MediaType.IMAGE,
    ".webp": MediaType.IMAGE, ".gif": MediaType.IMAGE, ".bmp": MediaType.IMAGE,
    ".mp3": MediaType.AUDIO, ".wav": MediaType.AUDIO, ".m4a": MediaType.AUDIO,
    ".aac": MediaType.AUDIO, ".flac": MediaType.AUDIO, ".ogg": MediaType.AUDIO,
    ".mp4": MediaType.VIDEO, ".mov": MediaType.VIDEO, ".avi": MediaType.VIDEO,
    ".mkv": MediaType.VIDEO, ".webm": MediaType.VIDEO,
    ".zip": MediaType.ARCHIVE,
    ".txt": MediaType.TEXT, ".md": MediaType.TEXT, ".csv": MediaType.TEXT,
    ".json": MediaType.TEXT, ".yaml": MediaType.TEXT, ".yml": MediaType.TEXT,
    ".html": MediaType.TEXT, ".xml": MediaType.TEXT, ".py": MediaType.TEXT,
}


def detect_media_type(path: Path) -> MediaType:
    return MEDIA_MAP.get(path.suffix.lower(), MediaType.UNKNOWN)


def has_media_extension(path_str: str) -> bool:
    try:
        return Path(path_str).suffix.lower() in MEDIA_EXTENSIONS
    except Exception:
        return False


class MediaProcessor:
    def __init__(self, config, audit, llm_judge=None):
        self._config = config
        self._audit = audit
        self._llm_judge = llm_judge

    def process(self, path: Path, query: str = "") -> str:
        mt = detect_media_type(path)

        if mt == MediaType.AUDIO:
            return self._run_whisper(path)

        if mt == MediaType.VIDEO:
            return self._process_video(path)

        if mt == MediaType.TEXT:
            return path.read_text(encoding="utf-8", errors="replace")

        md_text = convert_to_text(path, self._audit)
        if md_text and self._judge_output(md_text):
            self._audit.log("media_markitdown_success", {"path": str(path), "chars": len(md_text)}, category="FILE")
            return md_text

        self._audit.log("media_vision_fallback", {"path": str(path), "reason": "markitdown_insufficient"}, category="FILE")
        return self._run_vision(path)

    def _judge_output(self, text: str) -> bool:
        if not text or len(text.strip()) < 100:
            return False
        if len(text.strip()) > 300:
            return True
        if self._llm_judge:
            try:
                prompt = f"Does this text contain meaningful, readable content? Answer YES or NO only.\n\n{text[:500]}"
                result = self._llm_judge.invoke(prompt)
                content = result.content if hasattr(result, "content") else str(result)
                return "YES" in content.upper()
            except Exception:
                pass
        return True

    def _run_vision(self, path: Path) -> str:
        try:
            import ollama
            with open(path, "rb") as f:
                img_bytes = f.read()
            response = ollama.chat(
                model=self._config.agent.vision_model,
                messages=[{
                    "role": "user",
                    "content": (
                        "Describe this image in detail. Include: "
                        "1) All visible text (transcribe exactly). "
                        "2) Layout and structure. "
                        "3) Any charts, diagrams, or visual elements. "
                        "4) Document type if recognisable."
                    ),
                    "images": [img_bytes],
                }],
            )
            return response["message"]["content"]
        except Exception as e:
            self._audit.log("vision_error", {"path": str(path), "error": str(e)}, category="ERROR")
            return f"[Vision processing failed for {path.name}: {e}]"

    def _run_whisper(self, path: Path) -> str:
        try:
            from faster_whisper import WhisperModel
            model_name = getattr(self._config.media, "whisper_model", "base")
            model = WhisperModel(model_name, device="cpu", compute_type="int8")
            segments, _ = model.transcribe(str(path), beam_size=5)
            transcript = " ".join(seg.text for seg in segments)
            self._audit.log("whisper_transcribed", {"path": str(path), "chars": len(transcript)}, category="FILE")
            return transcript
        except Exception as e:
            self._audit.log("whisper_error", {"path": str(path), "error": str(e)}, category="ERROR")
            return f"[Audio transcription failed for {path.name}: {e}]"

    def _process_video(self, path: Path) -> str:
        import os
        import tempfile
        parts = []
        max_frames = getattr(self._config.media, "max_vision_frames", 5)
        interval = getattr(self._config.media, "video_frame_interval", 30)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            audio_path = tmp.name
        try:
            import ffmpeg
            ffmpeg.input(str(path)).output(audio_path, ac=1, ar=16000).overwrite_output().run(quiet=True)
            transcript = self._run_whisper(Path(audio_path))
            if transcript:
                parts.append(f"AUDIO TRANSCRIPT:\n{transcript}")
        except Exception as e:
            parts.append(f"[Audio extraction failed: {e}]")
        finally:
            if os.path.exists(audio_path):
                os.unlink(audio_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                import ffmpeg
                ffmpeg.input(str(path)).filter("fps", fps=f"1/{interval}").output(
                    f"{tmpdir}/frame_%04d.jpg", vframes=max_frames
                ).overwrite_output().run(quiet=True)
                frame_files = sorted(Path(tmpdir).glob("frame_*.jpg"))
                frame_descriptions = []
                for i, frame in enumerate(frame_files[:max_frames]):
                    desc = self._run_vision(frame)
                    frame_descriptions.append(f"Frame {i+1} (t={i*interval}s): {desc}")
                if frame_descriptions:
                    parts.append("VIDEO FRAMES:\n" + "\n".join(frame_descriptions))
            except Exception as e:
                parts.append(f"[Frame extraction failed: {e}]")

        return "\n\n".join(parts) if parts else f"[Video processing failed for {path.name}]"
