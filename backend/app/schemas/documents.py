from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain.document import (
    DocumentChunk,
    DocumentChunkSourceType,
    DocumentImportResult,
    DocumentItem,
    DocumentJob,
    DocumentStatus,
    DocumentVersion,
)


class DocumentImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_path: str = Field(min_length=1, max_length=32767)


DocumentSourcePath = Annotated[str, Field(min_length=1, max_length=32767)]


class DocumentBatchImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_paths: list[DocumentSourcePath] = Field(min_length=1, max_length=50)


class DocumentJobResponse(BaseModel):
    id: str
    status: DocumentStatus
    progress: int
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def from_domain(cls, job: DocumentJob) -> "DocumentJobResponse":
        return cls(**{field: getattr(job, field) for field in cls.model_fields})


class DocumentVersionResponse(BaseModel):
    id: str
    version_number: int
    sha256: str
    size_bytes: int
    status: DocumentStatus
    parsed_text: str | None
    error_code: str | None
    error_message: str | None
    created_at: datetime

    @classmethod
    def from_domain(cls, version: DocumentVersion) -> "DocumentVersionResponse":
        return cls(**{field: getattr(version, field) for field in cls.model_fields})


class DocumentResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    relative_path: str
    created_at: datetime
    updated_at: datetime
    latest_version: DocumentVersionResponse
    job: DocumentJobResponse

    @classmethod
    def from_domain(cls, document: DocumentItem) -> "DocumentResponse":
        return cls(
            id=document.id,
            workspace_id=document.workspace_id,
            name=document.name,
            relative_path=document.relative_path,
            created_at=document.created_at,
            updated_at=document.updated_at,
            latest_version=DocumentVersionResponse.from_domain(document.latest_version),
            job=DocumentJobResponse.from_domain(document.job),
        )


class DocumentChunkResponse(BaseModel):
    id: str
    ordinal: int
    source_type: DocumentChunkSourceType
    source_start: int
    source_end: int
    start_offset: int
    end_offset: int
    text: str
    locator: str

    @classmethod
    def from_domain(cls, chunk: DocumentChunk) -> "DocumentChunkResponse":
        return cls(
            id=chunk.id,
            ordinal=chunk.ordinal,
            source_type=chunk.source_type,
            source_start=chunk.source_start,
            source_end=chunk.source_end,
            start_offset=chunk.start_offset,
            end_offset=chunk.end_offset,
            text=chunk.text,
            locator=chunk.locator,
        )


class DocumentImportResultResponse(BaseModel):
    source_path: str
    status: Literal["accepted", "rejected"]
    document: DocumentResponse | None
    error_code: str | None
    error_message: str | None

    @classmethod
    def from_domain(cls, result: DocumentImportResult) -> "DocumentImportResultResponse":
        accepted = result.document is not None
        return cls(
            source_path=result.source_path,
            status="accepted" if accepted else "rejected",
            document=(
                DocumentResponse.from_domain(result.document)
                if result.document is not None
                else None
            ),
            error_code=result.error_code,
            error_message=result.error_message,
        )
