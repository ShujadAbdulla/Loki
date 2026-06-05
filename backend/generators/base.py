from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path


class BaseGenerator(ABC):
    def __init__(self, config, audit, llm=None):
        self._config = config
        self._audit = audit
        self._llm = llm
        self._output_dir = Path(config.generators.output_folder)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._template_dir = Path(config.generators.template_folder)
        self._template_dir.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def generate(self, prompt: str, template_path: Path | None = None) -> Path:
        pass

    def _get_template(self, ext: str) -> Path | None:
        templates = list(self._template_dir.glob(f"*.{ext}"))
        return templates[0] if templates else None

    def _unique_output_path(self, name: str, ext: str) -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name[:40])
        return self._output_dir / f"{safe}_{ts}.{ext}"

    def _llm_json(self, system: str, prompt: str) -> dict:
        import json
        import re
        if not self._llm:
            raise RuntimeError("LLM not available for generation")
        msg = f"{system}\n\nUser request: {prompt}\n\nRespond with valid JSON only."
        result = self._llm.invoke(msg)
        content = result.content if hasattr(result, "content") else str(result)
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\n?", "", content)
            content = re.sub(r"\n?```$", "", content)
        return json.loads(content)
