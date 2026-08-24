from __future__ import annotations

import builtins
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    delete,
    func,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Field, Session, SQLModel, col, select

from backend.app.domain.document import (
    TERMINAL_DOCUMENT_STATUSES,
    DocumentChunk,
    DocumentConflictError,
    DocumentImport,
    DocumentItem,
    DocumentJob,
    DocumentParseResult,
    DocumentSource,
    DocumentStatus,
    DocumentVersion,
)
from backend.app.infrastructure.workspaces import WorkspaceRecord  # noqa: F401


class DocumentRecord(SQLModel, table=True):
    __tablename__ = "documents"
    __table_args__ = (
        Index("uq_documents_workspace_path", "workspace_id", "path_key", unique=True),
    )

    id: str = Field(sa_column=Column(String(36), primary_key=True))
    workspace_id: str = Field(
        sa_column=Column(
            String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
        )
    )
    name: str = Field(sa_column=Column(String(255), nullable=False))
    relative_path: str = Field(sa_column=Column(String(2048), nullable=False))
    path_key: str = Field(sa_column=Column(String(2048), nullable=False))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class DocumentVersionRecord(SQLModel, table=True):
    __tablename__ = "document_versions"
    __table_args__ = (
        Index("uq_document_versions_workspace_hash", "workspace_id", "sha256", unique=True),
        Index("uq_document_versions_number", "document_id", "version_number", unique=True),
    )

    id: str = Field(sa_column=Column(String(36), primary_key=True))
    document_id: str = Field(
        sa_column=Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    )
    workspace_id: str = Field(
        sa_column=Column(
            String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
        )
    )
    version_number: int = Field(sa_column=Column(Integer, nullable=False))
    sha256: str = Field(sa_column=Column(String(64), nullable=False))
    size_bytes: int = Field(sa_column=Column(Integer, nullable=False))
    status: str = Field(sa_column=Column(String(16), nullable=False))
    parsed_text: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    error_code: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    error_message: str | None = Field(default=None, sa_column=Column(String(500), nullable=True))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class DocumentJobRecord(SQLModel, table=True):
    __tablename__ = "document_jobs"
    __table_args__ = (UniqueConstraint("version_id"),)

    id: str = Field(sa_column=Column(String(36), primary_key=True))
    version_id: str = Field(
        sa_column=Column(
            String(36), ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False
        )
    )
    status: str = Field(sa_column=Column(String(16), nullable=False))
    progress: int = Field(sa_column=Column(Integer, nullable=False))
    pid: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    error_code: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    error_message: str | None = Field(default=None, sa_column=Column(String(500), nullable=True))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    started_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    finished_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class DocumentChunkRecord(SQLModel, table=True):
    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("uq_document_chunks_version_ordinal", "version_id", "ordinal", unique=True),
    )

    id: str = Field(sa_column=Column(String(36), primary_key=True))
    version_id: str = Field(
        sa_column=Column(
            String(36), ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False
        )
    )
    ordinal: int = Field(sa_column=Column(Integer, nullable=False))
    source_type: str = Field(sa_column=Column(String(16), nullable=False))
    source_start: int = Field(sa_column=Column(Integer, nullable=False))
    source_end: int = Field(sa_column=Column(Integer, nullable=False))
    start_offset: int = Field(sa_column=Column(Integer, nullable=False))
    end_offset: int = Field(sa_column=Column(Integer, nullable=False))
    text: str = Field(sa_column=Column(Text, nullable=False))


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class SqlModelDocumentRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list(self, workspace_id: str) -> list[DocumentItem]:
        with Session(self._engine) as session:
            records = session.exec(
                select(DocumentRecord)
                .where(DocumentRecord.workspace_id == workspace_id)
                .order_by(col(DocumentRecord.updated_at).desc())
            ).all()
            return [self._item(session, record) for record in records]

    def get(self, workspace_id: str, document_id: str) -> DocumentItem | None:
        with Session(self._engine) as session:
            record = session.get(DocumentRecord, document_id)
            if record is None or record.workspace_id != workspace_id:
                return None
            return self._item(session, record)

    def get_by_job(self, job_id: str) -> DocumentItem | None:
        with Session(self._engine) as session:
            job = session.get(DocumentJobRecord, job_id)
            if job is None:
                return None
            version = session.get(DocumentVersionRecord, job.version_id)
            if version is None:
                return None
            document = session.get(DocumentRecord, version.document_id)
            return None if document is None else self._item(session, document)

    def find_version_by_hash(self, workspace_id: str, sha256: str) -> DocumentVersion | None:
        with Session(self._engine) as session:
            version = session.exec(
                select(DocumentVersionRecord).where(
                    DocumentVersionRecord.workspace_id == workspace_id,
                    DocumentVersionRecord.sha256 == sha256,
                )
            ).first()
            return None if version is None else self._version(version)

    def list_chunks(self, version_id: str) -> builtins.list[DocumentChunk]:
        with Session(self._engine) as session:
            records = session.exec(
                select(DocumentChunkRecord)
                .where(DocumentChunkRecord.version_id == version_id)
                .order_by(col(DocumentChunkRecord.ordinal))
            ).all()
            return [self._chunk(record) for record in records]

    def create_import(
        self,
        *,
        document_id: str,
        version_id: str,
        job_id: str,
        workspace_id: str,
        source: DocumentSource,
        created_at: datetime,
    ) -> DocumentImport:
        path_key = source.relative_path.casefold()
        with Session(self._engine) as session:
            document = session.exec(
                select(DocumentRecord).where(
                    DocumentRecord.workspace_id == workspace_id,
                    DocumentRecord.path_key == path_key,
                )
            ).first()
            if document is None:
                document = DocumentRecord(
                    id=document_id,
                    workspace_id=workspace_id,
                    name=source.name,
                    relative_path=source.relative_path,
                    path_key=path_key,
                    created_at=created_at,
                    updated_at=created_at,
                )
                version_number = 1
            else:
                document.name = source.name
                document.relative_path = source.relative_path
                document.updated_at = created_at
                maximum = session.exec(
                    select(func.max(DocumentVersionRecord.version_number)).where(
                        DocumentVersionRecord.document_id == document.id
                    )
                ).one()
                version_number = int(maximum or 0) + 1
            version = DocumentVersionRecord(
                id=version_id,
                document_id=document.id,
                workspace_id=workspace_id,
                version_number=version_number,
                sha256=source.sha256,
                size_bytes=source.size_bytes,
                status="queued",
                created_at=created_at,
            )
            job = DocumentJobRecord(
                id=job_id,
                version_id=version_id,
                status="queued",
                progress=0,
                created_at=created_at,
            )
            session.add(document)
            session.add(version)
            session.add(job)
            persisted_document_id = document.id
            try:
                session.commit()
            except IntegrityError as exception:
                session.rollback()
                raise DocumentConflictError from exception
        item = self.get(workspace_id, persisted_document_id)
        if item is None:
            raise RuntimeError("document import was not persisted")
        return DocumentImport(item, item.latest_version, item.job)

    def mark_running(self, job_id: str, *, pid: int, now: datetime) -> None:
        self._transition(job_id, "running", 10, now=now, pid=pid)

    def mark_passed(self, job_id: str, *, result: DocumentParseResult, now: datetime) -> None:
        with Session(self._engine) as session:
            job = session.get(DocumentJobRecord, job_id)
            if job is None or job.status in TERMINAL_DOCUMENT_STATUSES:
                return
            version = session.get(DocumentVersionRecord, job.version_id)
            if version is None:
                return
            session.exec(
                delete(DocumentChunkRecord).where(col(DocumentChunkRecord.version_id) == version.id)
            )
            for ordinal, chunk in enumerate(result.chunks, start=1):
                session.add(
                    DocumentChunkRecord(
                        id=str(uuid5(NAMESPACE_URL, f"document:{version.id}:chunk:{ordinal}")),
                        version_id=version.id,
                        ordinal=ordinal,
                        source_type=chunk.source_type,
                        source_start=chunk.source_start,
                        source_end=chunk.source_end,
                        start_offset=chunk.start_offset,
                        end_offset=chunk.end_offset,
                        text=chunk.text,
                    )
                )
            self._transition_in_session(
                session,
                job,
                "passed",
                100,
                now=now,
                parsed_text=result.text,
            )
            session.commit()

    def mark_failed(self, job_id: str, *, code: str, message: str, now: datetime) -> None:
        self._transition(job_id, "failed", 100, now=now, code=code, message=message)

    def mark_error(self, job_id: str, *, code: str, message: str, now: datetime) -> None:
        self._transition(job_id, "error", 100, now=now, code=code, message=message)

    def mark_timeout(self, job_id: str, *, now: datetime) -> None:
        self._transition(
            job_id,
            "timeout",
            100,
            now=now,
            code="DOCUMENT_PARSE_TIMEOUT",
            message="文档解析超时。",
        )

    def mark_cancelled(self, job_id: str, *, now: datetime) -> None:
        self._transition(job_id, "cancelled", 100, now=now)

    def recover_interrupted(self, *, now: datetime) -> None:
        with Session(self._engine) as session:
            jobs = session.exec(
                select(DocumentJobRecord).where(
                    col(DocumentJobRecord.status).in_(["queued", "running"])
                )
            ).all()
            for job in jobs:
                self._transition_in_session(
                    session,
                    job,
                    "error",
                    100,
                    now=now,
                    code="DOCUMENT_WORKER_INTERRUPTED",
                    message="应用重启后已将中断的解析任务标记为错误。",
                )
            session.commit()

    def _transition(
        self,
        job_id: str,
        status: DocumentStatus,
        progress: int,
        *,
        now: datetime,
        pid: int | None = None,
        parsed_text: str | None = None,
        code: str | None = None,
        message: str | None = None,
    ) -> None:
        with Session(self._engine) as session:
            job = session.get(DocumentJobRecord, job_id)
            if job is None or job.status in TERMINAL_DOCUMENT_STATUSES:
                return
            self._transition_in_session(
                session,
                job,
                status,
                progress,
                now=now,
                pid=pid,
                parsed_text=parsed_text,
                code=code,
                message=message,
            )
            session.commit()

    @staticmethod
    def _transition_in_session(
        session: Session,
        job: DocumentJobRecord,
        status: DocumentStatus,
        progress: int,
        *,
        now: datetime,
        pid: int | None = None,
        parsed_text: str | None = None,
        code: str | None = None,
        message: str | None = None,
    ) -> None:
        job.status = status
        job.progress = progress
        job.pid = pid
        job.error_code = code
        job.error_message = message
        if status == "running":
            job.started_at = now
        if status in TERMINAL_DOCUMENT_STATUSES:
            job.finished_at = now
        version = session.get(DocumentVersionRecord, job.version_id)
        if version is not None:
            version.status = status
            version.parsed_text = parsed_text
            version.error_code = code
            version.error_message = message
            session.add(version)
        session.add(job)

    @staticmethod
    def _version(record: DocumentVersionRecord) -> DocumentVersion:
        return DocumentVersion(
            record.id,
            record.document_id,
            record.version_number,
            record.sha256,
            record.size_bytes,
            record.status,  # type: ignore[arg-type]
            record.parsed_text,
            record.error_code,
            record.error_message,
            _utc(record.created_at) or record.created_at,
        )

    @staticmethod
    def _job(record: DocumentJobRecord) -> DocumentJob:
        return DocumentJob(
            record.id,
            record.version_id,
            record.status,  # type: ignore[arg-type]
            record.progress,
            record.error_code,
            record.error_message,
            _utc(record.created_at) or record.created_at,
            _utc(record.started_at),
            _utc(record.finished_at),
        )

    @staticmethod
    def _chunk(record: DocumentChunkRecord) -> DocumentChunk:
        return DocumentChunk(
            record.id,
            record.version_id,
            record.ordinal,
            record.source_type,  # type: ignore[arg-type]
            record.source_start,
            record.source_end,
            record.start_offset,
            record.end_offset,
            record.text,
        )

    def _item(self, session: Session, document: DocumentRecord) -> DocumentItem:
        version = session.exec(
            select(DocumentVersionRecord)
            .where(DocumentVersionRecord.document_id == document.id)
            .order_by(col(DocumentVersionRecord.version_number).desc())
        ).first()
        if version is None:
            raise RuntimeError("document has no versions")
        job = session.exec(
            select(DocumentJobRecord).where(DocumentJobRecord.version_id == version.id)
        ).one()
        return DocumentItem(
            document.id,
            document.workspace_id,
            document.name,
            document.relative_path,
            _utc(document.created_at) or document.created_at,
            _utc(document.updated_at) or document.updated_at,
            self._version(version),
            self._job(job),
        )
