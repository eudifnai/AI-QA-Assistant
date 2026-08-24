import os
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel
from websockets.sync.connection import Connection
from websockets.sync.server import serve

from backend.app.domain.http_execution import HttpEnvironmentInput
from backend.app.domain.websocket_execution import (
    WebSocketExecutionStartInput,
    WebSocketExecutionTaskRequest,
    WebSocketMessageAssertion,
)
from backend.app.infrastructure.database import create_database_engine
from backend.app.infrastructure.http_execution import SqlModelHttpExecutionRepository
from backend.app.infrastructure.websocket_execution import (
    SqlModelWebSocketExecutionRepository,
    WebSocketExecutionRecord,
)
from backend.app.infrastructure.workspaces import WorkspaceRecord
from backend.app.workers.websocket_execution import WebSocketExecutionWorkerManager

NOW = datetime(2026, 8, 16, 4, 0, tzinfo=UTC)


def seed_repository(
    tmp_path: Path, base_url: str
) -> tuple[SqlModelWebSocketExecutionRepository, str, Engine]:
    database_path = tmp_path / "websocket-process.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_database_engine(database_url)
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
    environments = SqlModelHttpExecutionRepository(engine)
    environment = environments.create_environment(
        "environment-1",
        "workspace-1",
        HttpEnvironmentInput("本地服务", base_url, {"ROOM": "qa"}),
        now=NOW,
    )
    repository = SqlModelWebSocketExecutionRepository(engine)
    repository.create_run(
        run_id="run-process",
        workspace_id="workspace-1",
        environment=environment,
        input=WebSocketExecutionStartInput(
            environment.id,
            "/events?room={{ROOM}}",
            {},
            "subscribe {{ROOM}}",
            10,
            ("next {{ROOM}}",),
            2,
            5,
            0,
            (WebSocketMessageAssertion(1, "json_path_equals", "$.state", '"done"'),),
        ),
        created_at=NOW,
    )
    return repository, database_url, engine


def test_independent_websocket_worker_persists_received_sequence(tmp_path: Path) -> None:
    def handler(connection: Connection) -> None:
        assert connection.recv(timeout=5) == "subscribe qa"
        assert connection.recv(timeout=5) == "next qa"
        connection.send("ack qa")
        connection.send('{"state":"done"}')

    server = serve(handler, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.socket.getsockname()[1])
    try:
        repository, database_url, engine = seed_repository(tmp_path, f"http://127.0.0.1:{port}")
        manager = WebSocketExecutionWorkerManager(
            repository, database_url=database_url, timeout_seconds=15
        )
        manager.launch(WebSocketExecutionTaskRequest("run-process"))
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            run = repository.get_any("run-process")
            if run is not None and not run.can_cancel:
                break
            time.sleep(0.05)

        result = repository.get_run("workspace-1", "run-process")
        assert result is not None
        assert result.status == "passed"
        assert result.response_message == "ack qa"
        assert [item.message for item in result.responses] == ["ack qa", '{"state":"done"}']
        assert result.assertion_results[0].passed is True
        assert result.ping_interval_seconds == 5
        assert [event.code for event in result.events] == [
            "WEBSOCKET_EXECUTION_QUEUED",
            "WEBSOCKET_WORKER_STARTED",
            "WEBSOCKET_SEQUENCE_RECEIVED",
        ]
        with Session(engine) as session:
            record = session.get(WebSocketExecutionRecord, "run-process")
            assert record is not None
            assert record.pid not in (None, os.getpid())
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_independent_websocket_worker_marks_failed_assertion(tmp_path: Path) -> None:
    def handler(connection: Connection) -> None:
        assert connection.recv(timeout=5) == "subscribe qa"
        assert connection.recv(timeout=5) == "next qa"
        connection.send("ack qa")
        connection.send('{"state":"pending"}')

    server = serve(handler, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.socket.getsockname()[1])
    try:
        repository, database_url, _ = seed_repository(tmp_path, f"http://127.0.0.1:{port}")
        manager = WebSocketExecutionWorkerManager(
            repository, database_url=database_url, timeout_seconds=15
        )
        manager.launch(WebSocketExecutionTaskRequest("run-process"))
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            run = repository.get_any("run-process")
            if run is not None and not run.can_cancel:
                break
            time.sleep(0.05)

        result = repository.get_run("workspace-1", "run-process")
        assert result is not None
        assert result.status == "failed"
        assert result.error_code == "WEBSOCKET_ASSERTION_FAILED"
        assert result.assertion_results[0].passed is False
        assert result.responses[1].message == '{"state":"pending"}'
        assert result.events[-1].code == "WEBSOCKET_ASSERTION_FAILED"
    finally:
        server.shutdown()
        thread.join(timeout=5)
