from datetime import UTC, datetime
from typing import cast

from sqlalchemy.engine import Engine
from sqlmodel import Session, col, select

from backend.app.domain.task_events import TaskSnapshot, TaskStatus, TaskType
from backend.app.infrastructure.analysis import AnalysisRunRecord
from backend.app.infrastructure.documents import DocumentJobRecord, DocumentVersionRecord
from backend.app.infrastructure.http_execution import HttpExecutionRecord
from backend.app.infrastructure.protobuf_execution import ProtoExecutionRecord
from backend.app.infrastructure.websocket_execution import WebSocketExecutionRecord

MAX_SNAPSHOTS_PER_TYPE = 100


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _changed_at(
    created_at: datetime,
    started_at: datetime | None,
    finished_at: datetime | None,
) -> datetime:
    return _utc(finished_at or started_at or created_at)


class SqlModelTaskSnapshotReader:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_snapshots(self, workspace_id: str) -> list[TaskSnapshot]:
        with Session(self._engine) as session:
            document_jobs = session.exec(
                select(DocumentJobRecord)
                .join(
                    DocumentVersionRecord,
                    col(DocumentJobRecord.version_id) == col(DocumentVersionRecord.id),
                )
                .where(DocumentVersionRecord.workspace_id == workspace_id)
                .order_by(col(DocumentJobRecord.created_at).desc())
                .limit(MAX_SNAPSHOTS_PER_TYPE)
            ).all()
            analysis_runs = session.exec(
                select(AnalysisRunRecord)
                .where(AnalysisRunRecord.workspace_id == workspace_id)
                .order_by(col(AnalysisRunRecord.created_at).desc())
                .limit(MAX_SNAPSHOTS_PER_TYPE)
            ).all()
            http_runs = session.exec(
                select(HttpExecutionRecord)
                .where(HttpExecutionRecord.workspace_id == workspace_id)
                .order_by(col(HttpExecutionRecord.created_at).desc())
                .limit(MAX_SNAPSHOTS_PER_TYPE)
            ).all()
            websocket_runs = session.exec(
                select(WebSocketExecutionRecord)
                .where(WebSocketExecutionRecord.workspace_id == workspace_id)
                .order_by(col(WebSocketExecutionRecord.created_at).desc())
                .limit(MAX_SNAPSHOTS_PER_TYPE)
            ).all()
            protobuf_runs = session.exec(
                select(ProtoExecutionRecord)
                .where(ProtoExecutionRecord.workspace_id == workspace_id)
                .order_by(col(ProtoExecutionRecord.created_at).desc())
                .limit(MAX_SNAPSHOTS_PER_TYPE)
            ).all()

        snapshots = [
            TaskSnapshot(
                "document_parse",
                item.id,
                workspace_id,
                cast(TaskStatus, item.status),
                item.progress,
                _changed_at(item.created_at, item.started_at, item.finished_at),
            )
            for item in document_jobs
        ]
        snapshots.extend(
            TaskSnapshot(
                cast(TaskType, task_type),
                item.id,
                workspace_id,
                cast(TaskStatus, item.status),
                item.progress,
                _changed_at(item.created_at, item.started_at, item.finished_at),
            )
            for task_type, records in (
                ("analysis", analysis_runs),
                ("http_execution", http_runs),
                ("websocket_execution", websocket_runs),
                ("protobuf_execution", protobuf_runs),
            )
            for item in records
        )
        return sorted(snapshots, key=lambda item: item.key)
