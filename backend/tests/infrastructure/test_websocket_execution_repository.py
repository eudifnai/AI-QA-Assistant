from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import Session, SQLModel

from backend.app.domain.http_execution import HttpEnvironmentInput
from backend.app.domain.websocket_execution import WebSocketExecutionStartInput
from backend.app.infrastructure.database import create_database_engine
from backend.app.infrastructure.http_execution import SqlModelHttpExecutionRepository
from backend.app.infrastructure.websocket_execution import (
    SqlModelWebSocketExecutionRepository,
    WebSocketExecutionRecord,
)
from backend.app.infrastructure.workspaces import WorkspaceRecord

NOW = datetime(2026, 8, 16, 5, 0, tzinfo=UTC)


def test_repository_exposes_legacy_single_response_as_sequence(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite:///{(tmp_path / 'legacy-websocket.db').as_posix()}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            WorkspaceRecord(
                id="workspace-1",
                name="支付",
                name_key="支付",
                path=str(tmp_path),
                path_key=str(tmp_path).casefold(),
                created_at=NOW,
                last_opened_at=NOW,
            )
        )
        session.commit()
    environment = SqlModelHttpExecutionRepository(engine).create_environment(
        "environment-1",
        "workspace-1",
        HttpEnvironmentInput("开发", "https://api.example.test", {}),
        now=NOW,
    )
    repository = SqlModelWebSocketExecutionRepository(engine)
    repository.create_run(
        run_id="run-legacy",
        workspace_id="workspace-1",
        environment=environment,
        input=WebSocketExecutionStartInput(environment.id, "/events", {}, "hello", 10),
        created_at=NOW,
    )
    with Session(engine) as session:
        record = session.get(WebSocketExecutionRecord, "run-legacy")
        assert record is not None
        record.status = "passed"
        record.progress = 100
        record.response_message = "legacy ack"
        record.response_encoding = "text"
        record.response_size_bytes = 10
        record.responses_json = "[]"
        record.finished_at = NOW
        session.add(record)
        session.commit()

    result = repository.get_run("workspace-1", "run-legacy")

    assert result is not None
    assert [
        (item.ordinal, item.message, item.encoding, item.size_bytes) for item in result.responses
    ] == [(0, "legacy ack", "text", 10)]
