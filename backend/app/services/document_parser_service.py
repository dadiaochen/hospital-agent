"""Independent text/PDF/image parsing paths converging on ParsedDocument."""

from __future__ import annotations

import re
from io import BytesIO

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from rapidocr import RapidOCR

from app.core.exceptions import InvalidRequestError
from app.schemas.parsed_document import (
    DocumentInputType,
    ParsedDocument,
    ParsedMetric,
    ParsedSection,
    ParsedTable,
)


_METRIC_PATTERN = re.compile(
    r"^\s*(?P<name>[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9_ /()-]{0,48})"
    r"\s*[:：]\s*(?P<value>[-+]?\d+(?:\.\d+)?)\s*(?P<unit>[A-Za-z%/μµ0-9.-]+)?"
    r"(?:\s*[（(]\s*(?P<range>[^()（）]{1,48})\s*[)）])?\s*$"
)


class DocumentParserService:
    """Parse untrusted inputs without making medical conclusions or network calls."""

    def __init__(self) -> None:
        self._ocr_engine: RapidOCR | None = None

    def parse(
        self,
        *,
        input_type: DocumentInputType,
        document_type: str,
        text: str = "",
        content: bytes | None = None,
        extracted_text: str = "",
    ) -> ParsedDocument:
        if input_type == "text":
            return self.parse_text(document_type=document_type, text=text)
        if input_type == "pdf":
            return self.parse_pdf(
                document_type=document_type,
                content=content or b"",
                fallback_text=extracted_text or text,
            )
        return self.parse_image(
            document_type=document_type,
            content=content or b"",
            extracted_text=extracted_text or text,
        )

    def parse_text(self, *, document_type: str, text: str) -> ParsedDocument:
        normalized = self._normalize_text(text)
        return self._build(
            input_type="text",
            document_type=document_type,
            raw_text=normalized,
            parser_version="text-parser-v1",
        )

    def parse_pdf(
        self,
        *,
        document_type: str,
        content: bytes,
        fallback_text: str = "",
    ) -> ParsedDocument:
        if not content.startswith(b"%PDF"):
            raise InvalidRequestError("PDF 内容格式无效")
        try:
            reader = PdfReader(BytesIO(content))
            extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
        except (PdfReadError, OSError, ValueError) as exc:
            raise InvalidRequestError("PDF 文本解析失败") from exc
        # A provider-supplied text fallback is only used for image-based PDFs
        # whose pages carry no extractable text layer.
        raw_text = self._normalize_text(extracted or fallback_text)
        result = self._build(
            input_type="pdf",
            document_type=document_type,
            raw_text=raw_text,
            parser_version="pdf-parser-v1",
        )
        return result.model_copy(update={"sections": self._with_page(result.sections)})

    def parse_image(
        self,
        *,
        document_type: str,
        content: bytes,
        extracted_text: str = "",
    ) -> ParsedDocument:
        try:
            with Image.open(BytesIO(content)) as image:
                image.verify()
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise InvalidRequestError("图像内容格式无效") from exc
        ocr_text = self._normalize_text(extracted_text) or self._ocr_text(content)
        return self._build(
            input_type="image",
            document_type=document_type,
            raw_text=ocr_text,
            parser_version="rapidocr-image-parser-v1",
        )

    def _build(
        self,
        *,
        input_type: DocumentInputType,
        document_type: str,
        raw_text: str,
        parser_version: str,
    ) -> ParsedDocument:
        sections = self._sections(raw_text)
        tables = self._tables(raw_text)
        metrics = self._metrics(sections, tables)
        return ParsedDocument(
            input_type=input_type,
            document_type=document_type.strip() or "medical_report",
            raw_text=raw_text,
            sections=sections,
            tables=tables,
            metrics=metrics,
            parser_version=parser_version,
        )

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized: list[str] = []
        previous_was_blank = False
        for line in str(text).splitlines():
            stripped = line.strip()
            if stripped:
                normalized.append(stripped)
                previous_was_blank = False
            elif normalized and not previous_was_blank:
                # A single blank line is semantic for consecutive Markdown tables.
                normalized.append("")
                previous_was_blank = True
        return "\n".join(normalized).strip()

    @staticmethod
    def _sections(raw_text: str) -> list[ParsedSection]:
        if not raw_text:
            return []
        chunks = re.split(r"\n(?=#+\s+|[\u4e00-\u9fffA-Za-z]{2,20}[：:])", raw_text)
        return [
            ParsedSection(id=f"section-{index}", title="报告内容" if index == 1 else f"报告内容 {index}", content=chunk)
            for index, chunk in enumerate(chunks, start=1)
            if chunk.strip()
        ]

    @staticmethod
    def _tables(raw_text: str) -> list[ParsedTable]:
        groups: list[list[str]] = []
        current: list[str] = []
        for line in raw_text.splitlines():
            if "|" in line:
                current.append(line)
            elif current:
                groups.append(current)
                current = []
        if current:
            groups.append(current)

        tables: list[ParsedTable] = []
        for group in groups:
            rows = [[cell.strip() for cell in line.strip("|").split("|")] for line in group]
            rows = [row for row in rows if not all(set(cell) <= {"-", ":"} for cell in row)]
            if len(rows) >= 2 and rows[0]:
                tables.append(ParsedTable(
                    id=f"table-{len(tables) + 1}", headers=rows[0], rows=rows[1:]
                ))
        return tables

    @staticmethod
    def _metrics(sections: list[ParsedSection], tables: list[ParsedTable]) -> list[ParsedMetric]:
        metrics: list[ParsedMetric] = []
        for section in sections:
            for line in section.content.splitlines():
                matched = _METRIC_PATTERN.match(line)
                if matched:
                    metrics.append(ParsedMetric(
                        id=f"metric-{len(metrics) + 1}", name=matched.group("name").strip(),
                        value=matched.group("value"), unit=(matched.group("unit") or "").strip() or None,
                        reference_display=(matched.group("range") or "").strip() or None,
                        source_section_id=section.id,
                    ))
        for table in tables:
            if len(table.headers) >= 2:
                for row in table.rows:
                    if len(row) >= 2 and row[0] and re.fullmatch(r"[-+]?\d+(?:\.\d+)?", row[1]):
                        metrics.append(ParsedMetric(
                            id=f"metric-{len(metrics) + 1}", name=row[0], value=row[1],
                            unit=row[2] if len(row) > 2 and row[2] else None,
                            reference_display=row[3] if len(row) > 3 and row[3] else None,
                            source_section_id=table.id,
                        ))
        return metrics

    def _ocr_text(self, content: bytes) -> str:
        """Run local OCR only; an OCR failure degrades to an empty result."""

        try:
            if self._ocr_engine is None:
                self._ocr_engine = RapidOCR()
            output = self._ocr_engine(content)
            return self._normalize_text("\n".join(output.txts or ()))
        except (OSError, RuntimeError, ValueError):
            return ""

    @staticmethod
    def _with_page(sections: list[ParsedSection]) -> list[ParsedSection]:
        return [section.model_copy(update={"page_number": 1}) for section in sections]


__all__ = ["DocumentParserService"]
