from dataclasses import dataclass
from datetime import datetime
from typing import Literal

DocumentStatus = Literal[
    "pending", "queued", "running", "passed", "failed", "error", "cancelled", "timeout"
]
DocumentChunkSourceType = Literal["document", "lines", "block", "page"]
TERMINAL_DOCUMENT_STATUSES: frozenset[DocumentStatus] = frozenset(
    {"passed", "failed", "error", "cancelled", "timeout"}
)


@dataclass(frozen=True, slots=True)
class DocumentSource:
    name: str
    relative_path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class DocumentJob:
    id: str
    version_id: str
    status: DocumentStatus
    progress: int
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @property
    def can_cancel(self) -> bool:
        return self.status not in TERMINAL_DOCUMENT_STATUSES


@dataclass(frozen=True, slots=True)
class DocumentVersion:
    id: str
    document_id: str
    version_number: int
    sha256: str
    size_bytes: int
    status: DocumentStatus
    parsed_text: str | None
    error_code: str | None
    error_message: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class DocumentChunkDraft:
    source_type: DocumentChunkSourceType
    source_start: int
    source_end: int
    start_offset: int
    end_offset: int
    text: str


@dataclass(frozen=True, slots=True)
class DocumentParseResult:
    text: str
    chunks: tuple[DocumentChunkDraft, ...]


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    id: str
    version_id: str
    ordinal: int
    source_type: DocumentChunkSourceType
    source_start: int
    source_end: int
    start_offset: int
    end_offset: int
    text: str

    @property
    def locator(self) -> str:
        labels = {
            "document": "全文",
            "lines": "行",
            "block": "块",
            "page": "页",
        }
        if self.source_type == "document":
            return labels[self.source_type]
        label = labels[self.source_type]
        if self.source_start == self.source_end:
            return f"第 {self.source_start} {label}"
        return f"第 {self.source_start}-{self.source_end} {label}"


@dataclass(frozen=True, slots=True)
class DocumentItem:
    id: str
    workspace_id: str
    name: str
    relative_path: str
    created_at: datetime
    updated_at: datetime
    latest_version: DocumentVersion
    job: DocumentJob


@dataclass(frozen=True, slots=True)
class DocumentImport:
    document: DocumentItem
    version: DocumentVersion
    job: DocumentJob


@dataclass(frozen=True, slots=True)
class DocumentImportResult:
    source_path: str
    document: DocumentItem | None
    error_code: str | None
    error_message: str | None


@dataclass(frozen=True, slots=True)
class DocumentParseRequest:
    job_id: str
    workspace_path: str
    relative_path: str
    expected_sha256: str


class DocumentConflictError(Exception):
    pass
