import os
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel

from backend.app.domain.http_execution import (
    HttpAssertion,
    HttpEnvironmentInput,
    HttpExecutionStartInput,
    HttpExecutionTaskRequest,
)
from backend.app.infrastructure.database import create_database_engine
from backend.app.infrastructure.http_execution import (
    HttpExecutionRecord,
    SqlModelHttpExecutionRepository,
)
from backend.app.infrastructure.workspaces import WorkspaceRecord
from backend.app.workers.http_execution import HttpExecutionWorkerManager

NOW = datetime(2026, 8, 15, 2, 0, tzinfo=UTC)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        assert self.path == "/api/health?client=desktop"
        payload = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *args: object) -> None:
        return


def seed_repository(
    tmp_path: Path,
    base_url: str,
) -> tuple[SqlModelHttpExecutionRepository, str, Engine]:
    database_path = tmp_path / "http-process.db"
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
    repository = SqlModelHttpExecutionRepository(engine)
    environment = repository.create_environment(
        "environment-1",
        "workspace-1",
        HttpEnvironmentInput("本地服务", base_url, {"CLIENT": "desktop"}),
        now=NOW,
    )
    repository.create_run(
        run_id="run-process",
        workspace_id="workspace-1",
        environment=environment,
        input=HttpExecutionStartInput(
            "environment-1",
            "GET",
            "/health?client={{CLIENT}}",
            {},
            None,
            10,
            assertions=(HttpAssertion("status_code", None, "200"),),
        ),
        created_at=NOW,
    )
    return repository, database_url, engine


def test_independent_http_worker_executes_and_persists_safe_result(tmp_path: Path) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        repository, database_url, engine = seed_repository(
            tmp_path, f"http://127.0.0.1:{server.server_port}/api"
        )
        manager = HttpExecutionWorkerManager(
            repository,
            database_url=database_url,
            timeout_seconds=15,
        )

        manager.launch(HttpExecutionTaskRequest("run-process"))
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            run = repository.get_any("run-process")
            if run is not None and run.status in {
                "passed",
                "failed",
                "error",
                "cancelled",
                "timeout",
            }:
                break
            time.sleep(0.05)

        result = repository.get_run("workspace-1", "run-process")
        assert result is not None
        assert result.status == "passed"
        assert result.response_status_code == 200
        assert result.response_body == '{"ok":true}'
        assert result.assertion_results[0].passed is True
        assert [event.code for event in result.events] == [
            "HTTP_EXECUTION_QUEUED",
            "HTTP_WORKER_STARTED",
            "HTTP_REQUEST_ATTEMPT_STARTED",
            "HTTP_ASSERTIONS_PASSED",
        ]
        with Session(engine) as session:
            record = session.get(HttpExecutionRecord, "run-process")
            assert record is not None
            assert record.pid not in (None, os.getpid())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
