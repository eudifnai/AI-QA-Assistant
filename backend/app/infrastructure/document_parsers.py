import zlib
from io import BytesIO
from pathlib import PurePath
from zipfile import BadZipFile, LargeZipFile, ZipFile

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from backend.app.domain.document import (
    DocumentChunkDraft,
    DocumentChunkSourceType,
    DocumentParseResult,
)

MAX_EXTRACTED_TEXT_CHARS = 5_000_000
MAX_PDF_PAGES = 2_000
MAX_DOCX_BLOCKS = 100_000
MAX_DOCX_ARCHIVE_ENTRIES = 10_000
MAX_DOCX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_DOCUMENT_CHUNKS = 100_000


class DocumentParseError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class DocumentTextParser:
    def __init__(
        self,
        *,
        max_text_chars: int = MAX_EXTRACTED_TEXT_CHARS,
        max_docx_uncompressed_bytes: int = MAX_DOCX_UNCOMPRESSED_BYTES,
    ) -> None:
        self._max_text_chars = max_text_chars
        self._max_docx_uncompressed_bytes = max_docx_uncompressed_bytes

    def parse(self, content: bytes, relative_path: str) -> str:
        return self.parse_document(content, relative_path).text

    def parse_document(self, content: bytes, relative_path: str) -> DocumentParseResult:
        normalized_path = relative_path.casefold()
        suffix = (
            normalized_path
            if normalized_path.startswith(".") and "/" not in normalized_path
            else PurePath(normalized_path).suffix
        )
        if suffix in {".md", ".txt"}:
            text = self._parse_utf8(content)
            return DocumentParseResult(text, self._text_chunks(text))
        if suffix == ".docx":
            return self._parse_docx(content)
        if suffix == ".pdf":
            return self._parse_pdf(content)
        raise DocumentParseError("unsupported_format")

    def _parse_utf8(self, content: bytes) -> str:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exception:
            raise DocumentParseError("invalid_encoding") from exception
        return self._validate_output(text)

    def _parse_docx(self, content: bytes) -> DocumentParseResult:
        self._validate_docx_container(content)
        try:
            document = Document(BytesIO(content))
        except (
            BadZipFile,
            PackageNotFoundError,
            SyntaxError,
            KeyError,
            ValueError,
            OSError,
        ) as exception:
            raise DocumentParseError("corrupt_document") from exception
        blocks: list[tuple[str, DocumentChunkSourceType, int, int]] = []
        extracted_chars = 0
        for index, block in enumerate(document.iter_inner_content(), start=1):
            if index > MAX_DOCX_BLOCKS:
                raise DocumentParseError("document_too_complex")
            if isinstance(block, Paragraph):
                text = block.text.strip()
                if text:
                    blocks.append((text, "block", index, index))
                    extracted_chars += len(text)
            elif isinstance(block, Table):
                rows = [
                    "\t".join(cell.text.replace("\n", " ").strip() for cell in row.cells).rstrip()
                    for row in block.rows
                ]
                table_text = "\n".join(row for row in rows if row)
                if table_text:
                    blocks.append((table_text, "block", index, index))
                    extracted_chars += len(table_text)
            self._ensure_length(extracted_chars)
        return self._compose_chunks(blocks)

    def _parse_pdf(self, content: bytes) -> DocumentParseResult:
        if not content.startswith(b"%PDF-"):
            raise DocumentParseError("corrupt_document")
        try:
            reader = PdfReader(BytesIO(content), strict=False)
            if reader.is_encrypted:
                raise DocumentParseError("encrypted_pdf")
            if len(reader.pages) > MAX_PDF_PAGES:
                raise DocumentParseError("document_too_complex")
            pages: list[tuple[str, DocumentChunkSourceType, int, int]] = []
            extracted_chars = 0
            for page_number, page in enumerate(reader.pages, start=1):
                text = (page.extract_text() or "").strip()
                if text:
                    page_text = f"[第 {page_number} 页]\n{text}"
                    pages.append((page_text, "page", page_number, page_number))
                    extracted_chars += len(page_text)
                    self._ensure_length(extracted_chars)
        except DocumentParseError:
            raise
        except (
            PdfReadError,
            UnicodeDecodeError,
            ValueError,
            TypeError,
            KeyError,
            OSError,
            zlib.error,
        ) as exception:
            raise DocumentParseError("corrupt_document") from exception
        return self._compose_chunks(pages)

    def _text_chunks(self, text: str) -> tuple[DocumentChunkDraft, ...]:
        chunks: list[DocumentChunkDraft] = []
        group_start_offset: int | None = None
        group_start_line = 0
        group_end_line = 0
        group_end_offset = 0
        offset = 0
        lines = text.splitlines(keepends=True)
        for line_number, full_line in enumerate(lines, start=1):
            line = full_line.rstrip("\r\n")
            if line.strip():
                if group_start_offset is None:
                    group_start_offset = offset
                    group_start_line = line_number
                group_end_line = line_number
                group_end_offset = offset + len(line)
            elif group_start_offset is not None:
                chunks.append(
                    DocumentChunkDraft(
                        "lines",
                        group_start_line,
                        group_end_line,
                        group_start_offset,
                        group_end_offset,
                        text[group_start_offset:group_end_offset],
                    )
                )
                group_start_offset = None
            offset += len(full_line)
        if group_start_offset is not None:
            chunks.append(
                DocumentChunkDraft(
                    "lines",
                    group_start_line,
                    group_end_line,
                    group_start_offset,
                    group_end_offset,
                    text[group_start_offset:group_end_offset],
                )
            )
        self._ensure_chunk_count(len(chunks))
        return tuple(chunks)

    def _compose_chunks(
        self, units: list[tuple[str, DocumentChunkSourceType, int, int]]
    ) -> DocumentParseResult:
        self._ensure_chunk_count(len(units))
        text = self._validate_output("\n\n".join(unit[0] for unit in units))
        chunks: list[DocumentChunkDraft] = []
        offset = 0
        for unit_text, source_type, source_start, source_end in units:
            end_offset = offset + len(unit_text)
            chunks.append(
                DocumentChunkDraft(
                    source_type,
                    source_start,
                    source_end,
                    offset,
                    end_offset,
                    unit_text,
                )
            )
            offset = end_offset + 2
        return DocumentParseResult(text, tuple(chunks))

    @staticmethod
    def _ensure_chunk_count(count: int) -> None:
        if count > MAX_DOCUMENT_CHUNKS:
            raise DocumentParseError("document_too_complex")

    def _validate_docx_container(self, content: bytes) -> None:
        try:
            with ZipFile(BytesIO(content)) as archive:
                entries = archive.infolist()
                names = {entry.filename for entry in entries}
                if (
                    len(entries) > MAX_DOCX_ARCHIVE_ENTRIES
                    or sum(entry.file_size for entry in entries) > self._max_docx_uncompressed_bytes
                ):
                    raise DocumentParseError("document_too_complex")
                if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                    raise DocumentParseError("corrupt_document")
        except DocumentParseError:
            raise
        except (BadZipFile, LargeZipFile, OSError) as exception:
            raise DocumentParseError("corrupt_document") from exception

    def _ensure_length(self, extracted_chars: int) -> None:
        if extracted_chars > self._max_text_chars:
            raise DocumentParseError("extracted_text_too_large")

    def _validate_output(self, text: str) -> str:
        if not text.strip():
            raise DocumentParseError("empty_text")
        if len(text) > self._max_text_chars:
            raise DocumentParseError("extracted_text_too_large")
        return text
