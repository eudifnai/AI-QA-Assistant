from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, delete
from sqlalchemy.engine import Engine
from sqlmodel import Field, Session, SQLModel, col, select

from backend.app.domain.analysis import (
    TERMINAL_ANALYSIS_STATUSES,
    AnalysisCitation,
    AnalysisExecutionInput,
    AnalysisIssue,
    AnalysisOutput,
    AnalysisRun,
    AnalysisScore,
    AnalysisStatus,
)
from backend.app.domain.settings import ModelProvider
from backend.app.infrastructure.documents import (
    DocumentChunkRecord,
    DocumentRecord,  # noqa: F401
    DocumentVersionRecord,  # noqa: F401
)
from backend.app.infrastructure.workspaces import WorkspaceRecord  # noqa: F401


class AnalysisRunRecord(SQLModel, table=True):
    __tablename__ = "analysis_runs"
    __table_args__ = (Index("ix_analysis_runs_document_created", "document_id", "created_at"),)

    id: str = Field(sa_column=Column(String(36), primary_key=True))
    workspace_id: str = Field(
        sa_column=Column(
            String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
        )
    )
    document_id: str = Field(
        sa_column=Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    )
    version_id: str = Field(
        sa_column=Column(
            String(36), ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False
        )
    )
    provider: str = Field(sa_column=Column(String(32), nullable=False))
    model_name: str = Field(sa_column=Column(String(120), nullable=False))
    base_url: str = Field(sa_column=Column(String(2048), nullable=False))
    input_chunk_count: int = Field(sa_column=Column(Integer, nullable=False, server_default="0"))
    input_character_count: int = Field(
        sa_column=Column(Integer, nullable=False, server_default="0")
    )
    cloud_data_confirmed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    status: str = Field(sa_column=Column(String(16), nullable=False))
    progress: int = Field(sa_column=Column(Integer, nullable=False))
    pid: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    overall_score: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    error_code: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    error_message: str | None = Field(default=None, sa_column=Column(String(500), nullable=True))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    started_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    finished_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class AnalysisScoreRecord(SQLModel, table=True):
    __tablename__ = "analysis_scores"
    __table_args__ = (
        Index("uq_analysis_scores_run_dimension", "run_id", "dimension", unique=True),
    )

    id: str = Field(sa_column=Column(String(36), primary_key=True))
    run_id: str = Field(
        sa_column=Column(
            String(36), ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False
        )
    )
    dimension: str = Field(sa_column=Column(String(24), nullable=False))
    score: int = Field(sa_column=Column(Integer, nullable=False))
    summary: str = Field(sa_column=Column(Text, nullable=False))


class AnalysisIssueRecord(SQLModel, table=True):
    __tablename__ = "analysis_issues"
    __table_args__ = (Index("uq_analysis_issues_run_ordinal", "run_id", "ordinal", unique=True),)

    id: str = Field(sa_column=Column(String(36), primary_key=True))
    run_id: str = Field(
        sa_column=Column(
            String(36), ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False
        )
    )
    ordinal: int = Field(sa_column=Column(Integer, nullable=False))
    dimension: str = Field(sa_column=Column(String(24), nullable=False))
    severity: str = Field(sa_column=Column(String(16), nullable=False))
    title: str = Field(sa_column=Column(String(500), nullable=False))
    description: str = Field(sa_column=Column(Text, nullable=False))
    impact: str = Field(sa_column=Column(Text, nullable=False))
    suggestion: str = Field(sa_column=Column(Text, nullable=False))
    question: str = Field(sa_column=Column(Text, nullable=False))


class AnalysisCitationRecord(SQLModel, table=True):
    __tablename__ = "analysis_citations"
    __table_args__ = (
        Index("uq_analysis_citations_issue_ordinal", "issue_id", "ordinal", unique=True),
    )

    id: str = Field(sa_column=Column(String(36), primary_key=True))
    issue_id: str = Field(
        sa_column=Column(
            String(36), ForeignKey("analysis_issues.id", ondelete="CASCADE"), nullable=False
        )
    )
    chunk_id: str = Field(
        sa_column=Column(
            String(36), ForeignKey("document_chunks.id", ondelete="RESTRICT"), nullable=False
        )
    )
    ordinal: int = Field(sa_column=Column(Integer, nullable=False))


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class SqlModelAnalysisRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create(
        self,
        *,
        run_id: str,
        workspace_id: str,
        document_id: str,
        version_id: str,
        provider: ModelProvider,
        model_name: str,
        base_url: str,
        input_chunk_count: int,
        input_character_count: int,
        cloud_data_confirmed_at: datetime | None,
        created_at: datetime,
    ) -> AnalysisRun:
        with Session(self._engine) as session:
            session.add(
                AnalysisRunRecord(
                    id=run_id,
                    workspace_id=workspace_id,
                    document_id=document_id,
                    version_id=version_id,
                    provider=provider,
                    model_name=model_name,
                    base_url=base_url,
                    input_chunk_count=input_chunk_count,
                    input_character_count=input_character_count,
                    cloud_data_confirmed_at=cloud_data_confirmed_at,
                    status="queued",
                    progress=0,
                    created_at=created_at,
                )
            )
            session.commit()
        run = self.get(workspace_id, run_id)
        if run is None:
            raise RuntimeError("analysis run was not persisted")
        return run

    def list(self, workspace_id: str, document_id: str) -> list[AnalysisRun]:
        with Session(self._engine) as session:
            records = session.exec(
                select(AnalysisRunRecord)
                .where(
                    AnalysisRunRecord.workspace_id == workspace_id,
                    AnalysisRunRecord.document_id == document_id,
                )
                .order_by(col(AnalysisRunRecord.created_at).desc())
            ).all()
            return [self._run(session, record) for record in records]

    def get(self, workspace_id: str, run_id: str) -> AnalysisRun | None:
        with Session(self._engine) as session:
            record = session.get(AnalysisRunRecord, run_id)
            if record is None or record.workspace_id != workspace_id:
                return None
            return self._run(session, record)

    def get_any(self, run_id: str) -> AnalysisRun | None:
        with Session(self._engine) as session:
            record = session.get(AnalysisRunRecord, run_id)
            return None if record is None else self._run(session, record)

    def load_execution_input(self, run_id: str) -> AnalysisExecutionInput | None:
        with Session(self._engine) as session:
            run = session.get(AnalysisRunRecord, run_id)
            if run is None:
                return None
            chunks = session.exec(
                select(DocumentChunkRecord)
                .where(DocumentChunkRecord.version_id == run.version_id)
                .order_by(col(DocumentChunkRecord.ordinal))
            ).all()
            citations = tuple(
                AnalysisCitation(
                    chunk.id,
                    chunk.ordinal,
                    self._locator(chunk),
                    chunk.text,
                )
                for chunk in chunks
            )
            return AnalysisExecutionInput(
                run.id,
                ModelProvider(run.provider),
                run.base_url,
                run.model_name,
                citations,
            )

    def mark_running(self, run_id: str, *, pid: int, now: datetime) -> None:
        self._transition(run_id, "running", 10, now=now, pid=pid)

    def mark_generating(self, run_id: str, *, now: datetime) -> None:
        self._transition(run_id, "running", 60, now=now)

    def mark_passed(self, run_id: str, *, output: AnalysisOutput, now: datetime) -> None:
        with Session(self._engine) as session:
            run = session.get(AnalysisRunRecord, run_id)
            if run is None or run.status in TERMINAL_ANALYSIS_STATUSES:
                return
            session.exec(
                delete(AnalysisCitationRecord).where(
                    col(AnalysisCitationRecord.issue_id).in_(
                        select(AnalysisIssueRecord.id).where(
                            col(AnalysisIssueRecord.run_id) == run_id
                        )
                    )
                )
            )
            session.exec(
                delete(AnalysisIssueRecord).where(col(AnalysisIssueRecord.run_id) == run_id)
            )
            session.exec(
                delete(AnalysisScoreRecord).where(col(AnalysisScoreRecord.run_id) == run_id)
            )
            for score in output.dimension_scores:
                session.add(
                    AnalysisScoreRecord(
                        id=self._stable_id(run_id, f"score:{score.dimension}"),
                        run_id=run_id,
                        dimension=score.dimension,
                        score=score.score,
                        summary=score.summary,
                    )
                )
            for issue_ordinal, issue in enumerate(output.issues, start=1):
                issue_id = self._stable_id(run_id, f"issue:{issue_ordinal}")
                session.add(
                    AnalysisIssueRecord(
                        id=issue_id,
                        run_id=run_id,
                        ordinal=issue_ordinal,
                        dimension=issue.dimension,
                        severity=issue.severity,
                        title=issue.title,
                        description=issue.description,
                        impact=issue.impact,
                        suggestion=issue.suggestion,
                        question=issue.question,
                    )
                )
                for citation_ordinal, chunk_id in enumerate(issue.citation_chunk_ids, start=1):
                    session.add(
                        AnalysisCitationRecord(
                            id=self._stable_id(issue_id, f"citation:{citation_ordinal}"),
                            issue_id=issue_id,
                            chunk_id=chunk_id,
                            ordinal=citation_ordinal,
                        )
                    )
            self._transition_in_session(
                session, run, "passed", 100, now=now, overall_score=output.overall_score
            )
            session.commit()

    def mark_failed(self, run_id: str, *, code: str, message: str, now: datetime) -> None:
        self._transition(run_id, "failed", 100, now=now, code=code, message=message)

    def mark_error(self, run_id: str, *, code: str, message: str, now: datetime) -> None:
        self._transition(run_id, "error", 100, now=now, code=code, message=message)

    def mark_timeout(self, run_id: str, *, now: datetime) -> None:
        self._transition(
            run_id,
            "timeout",
            100,
            now=now,
            code="ANALYSIS_TIMEOUT",
            message="需求分析超时。",
        )

    def mark_cancelled(self, run_id: str, *, now: datetime) -> None:
        self._transition(run_id, "cancelled", 100, now=now)

    def recover_interrupted(self, *, now: datetime) -> None:
        with Session(self._engine) as session:
            records = session.exec(
                select(AnalysisRunRecord).where(
                    col(AnalysisRunRecord.status).in_(["queued", "running"])
                )
            ).all()
            for record in records:
                self._transition_in_session(
                    session,
                    record,
                    "error",
                    100,
                    now=now,
                    code="ANALYSIS_WORKER_INTERRUPTED",
                    message="应用重启后已将中断的分析任务标记为错误。",
                )
            session.commit()

    def _transition(
        self,
        run_id: str,
        status: AnalysisStatus,
        progress: int,
        *,
        now: datetime,
        pid: int | None = None,
        overall_score: int | None = None,
        code: str | None = None,
        message: str | None = None,
    ) -> None:
        with Session(self._engine) as session:
            run = session.get(AnalysisRunRecord, run_id)
            if run is None or run.status in TERMINAL_ANALYSIS_STATUSES:
                return
            self._transition_in_session(
                session,
                run,
                status,
                progress,
                now=now,
                pid=pid,
                overall_score=overall_score,
                code=code,
                message=message,
            )
            session.commit()

    @staticmethod
    def _transition_in_session(
        session: Session,
        run: AnalysisRunRecord,
        status: AnalysisStatus,
        progress: int,
        *,
        now: datetime,
        pid: int | None = None,
        overall_score: int | None = None,
        code: str | None = None,
        message: str | None = None,
    ) -> None:
        run.status = status
        run.progress = progress
        if pid is not None:
            run.pid = pid
        run.overall_score = overall_score
        run.error_code = code
        run.error_message = message
        if status == "running" and run.started_at is None:
            run.started_at = now
        if status in TERMINAL_ANALYSIS_STATUSES:
            run.finished_at = now
        session.add(run)

    def _run(self, session: Session, record: AnalysisRunRecord) -> AnalysisRun:
        scores = session.exec(
            select(AnalysisScoreRecord).where(AnalysisScoreRecord.run_id == record.id)
        ).all()
        dimension_order = {
            "completeness": 0,
            "consistency": 1,
            "clarity": 2,
            "testability": 3,
            "feasibility": 4,
        }
        scores = sorted(scores, key=lambda score: dimension_order.get(score.dimension, 5))
        issues = session.exec(
            select(AnalysisIssueRecord)
            .where(AnalysisIssueRecord.run_id == record.id)
            .order_by(col(AnalysisIssueRecord.ordinal))
        ).all()
        return AnalysisRun(
            record.id,
            record.workspace_id,
            record.document_id,
            record.version_id,
            ModelProvider(record.provider),
            record.model_name,
            record.base_url,
            record.input_chunk_count,
            record.input_character_count,
            _utc(record.cloud_data_confirmed_at),
            record.status,  # type: ignore[arg-type]
            record.progress,
            record.overall_score,
            record.error_code,
            record.error_message,
            _utc(record.created_at) or record.created_at,
            _utc(record.started_at),
            _utc(record.finished_at),
            tuple(
                AnalysisScore(
                    score.dimension,  # type: ignore[arg-type]
                    score.score,
                    score.summary,
                )
                for score in scores
            ),
            tuple(self._issue(session, issue) for issue in issues),
        )

    def _issue(self, session: Session, record: AnalysisIssueRecord) -> AnalysisIssue:
        rows = session.exec(
            select(AnalysisCitationRecord, DocumentChunkRecord)
            .join(
                DocumentChunkRecord,
                col(AnalysisCitationRecord.chunk_id) == col(DocumentChunkRecord.id),
            )
            .where(AnalysisCitationRecord.issue_id == record.id)
            .order_by(col(AnalysisCitationRecord.ordinal))
        ).all()
        return AnalysisIssue(
            record.id,
            record.ordinal,
            record.dimension,  # type: ignore[arg-type]
            record.severity,  # type: ignore[arg-type]
            record.title,
            record.description,
            record.impact,
            record.suggestion,
            record.question,
            tuple(
                AnalysisCitation(chunk.id, citation.ordinal, self._locator(chunk), chunk.text)
                for citation, chunk in rows
            ),
        )

    @staticmethod
    def _locator(chunk: DocumentChunkRecord) -> str:
        if chunk.source_type == "document":
            return "全文"
        labels = {"lines": "行", "block": "块", "page": "页"}
        label = labels.get(chunk.source_type, "位置")
        if chunk.source_start == chunk.source_end:
            return f"第 {chunk.source_start} {label}"
        return f"第 {chunk.source_start}-{chunk.source_end} {label}"

    @staticmethod
    def _stable_id(namespace: str, value: str) -> str:
        return str(uuid5(NAMESPACE_URL, f"analysis:{namespace}:{value}"))
