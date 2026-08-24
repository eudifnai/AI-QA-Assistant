from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import Session, SQLModel

from backend.app.infrastructure.analysis import AnalysisRunRecord
from backend.app.infrastructure.database import create_database_engine
from backend.app.infrastructure.documents import (
    DocumentJobRecord,
    DocumentRecord,
    DocumentVersionRecord,
)
from backend.app.infrastructure.task_events import SqlModelTaskSnapshotReader
from backend.app.infrastructure.workspaces import WorkspaceRecord

NOW = datetime(2026, 8, 16, 6, 0, tzinfo=UTC)


def test_snapshot_reader_joins_document_jobs_and_scopes_all_tasks_to_workspace(
    tmp_path: Path,
) -> None:
    engine = create_database_engine(f"sqlite:///{(tmp_path / 'task-events.db').as_posix()}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for workspace_id in ("workspace-1", "workspace-2"):
            session.add(
                WorkspaceRecord(
                    id=workspace_id,
                    name=workspace_id,
                    name_key=workspace_id,
                    path=str(tmp_path / workspace_id),
                    path_key=str(tmp_path / workspace_id).casefold(),
                    created_at=NOW,
                    last_opened_at=NOW,
                )
            )
            document_id = f"document-{workspace_id[-1]}"
            version_id = f"version-{workspace_id[-1]}"
            session.add(
                DocumentRecord(
                    id=document_id,
                    workspace_id=workspace_id,
                    name="requirements.md",
                    relative_path="requirements.md",
                    path_key="requirements.md",
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            session.add(
                DocumentVersionRecord(
                    id=version_id,
                    document_id=document_id,
                    workspace_id=workspace_id,
                    version_number=1,
                    sha256=workspace_id[-1] * 64,
                    size_bytes=10,
                    status="running",
                    created_at=NOW,
                )
            )
            session.add(
                DocumentJobRecord(
                    id=f"job-{workspace_id[-1]}",
                    version_id=version_id,
                    status="running",
                    progress=35,
                    created_at=NOW,
                    started_at=NOW,
                )
            )
        session.add(
            AnalysisRunRecord(
                id="analysis-1",
                workspace_id="workspace-1",
                document_id="document-1",
                version_id="version-1",
                provider="ollama",
                model_name="qwen",
                base_url="http://127.0.0.1:11434",
                status="queued",
                progress=0,
                created_at=NOW,
            )
        )
        session.commit()

    snapshots = SqlModelTaskSnapshotReader(engine).list_snapshots("workspace-1")

    assert [(item.task_type, item.task_id, item.status, item.progress) for item in snapshots] == [
        ("analysis", "analysis-1", "queued", 0),
        ("document_parse", "job-1", "running", 35),
    ]
    assert all(item.workspace_id == "workspace-1" for item in snapshots)
