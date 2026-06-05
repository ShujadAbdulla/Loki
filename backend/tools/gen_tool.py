"""LangChain tools for file generation."""

from __future__ import annotations

from backend.generators.docx_generator import DocxGenerator
from backend.generators.pdf_generator import PdfGenerator
from backend.generators.pptx_generator import PptxGenerator
from backend.generators.xlsx_generator import XlsxGenerator


class GenTools:
    def __init__(self, config, audit, llm):
        self._config = config
        self._audit = audit
        self._llm = llm

    def generate_docx(self, prompt: str) -> str:
        path = DocxGenerator(self._config, self._audit, self._llm).generate(prompt)
        return str(path)

    def generate_pptx(self, prompt: str) -> str:
        path = PptxGenerator(self._config, self._audit, self._llm).generate(prompt)
        return str(path)

    def generate_pdf(self, prompt: str) -> str:
        path = PdfGenerator(self._config, self._audit, self._llm).generate(prompt)
        return str(path)

    def generate_xlsx(self, prompt: str) -> str:
        path = XlsxGenerator(self._config, self._audit, self._llm).generate(prompt)
        return str(path)
