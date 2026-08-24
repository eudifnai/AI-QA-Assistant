import multiprocessing
from multiprocessing.process import BaseProcess
from typing import cast

from backend.app.domain.websocket_execution import (
    WebSocketExecutionInput,
    WebSocketExecutionTaskRequest,
    WebSocketMessageAssertion,
)
from backend.app.infrastructure.websocket_execution import SqlModelWebSocketExecutionRepository
from backend.app.infrastructure.websocket_runner import WebSocketRunner
from backend.app.workers.websocket_execution import WebSocketExecutionWorkerManager, _run_request


class Secrets:
    def get(self, environment_id: str, name: str) -> str | None:
        assert environment_id == "environment-1"
        return "top-secret" if name == "API_TOKEN" else None


class Connection:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.responses = iter(["ack top-secret", '{"state":"done"}'])

    def __enter__(self) -> "Connection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def send(self, message: str) -> None:
        self.sent.append(message)

    def recv(self, timeout: float | None = None) -> str:
        return next(self.responses)


def test_worker_resolves_templates_in_child_and_redacts_response() -> None:
    captured: dict[str, object] = {}
    connection = Connection()

    def connect(uri: str, **kwargs: object) -> Connection:
        captured.update(uri=uri, **kwargs)
        return connection

    result = _run_request(
        WebSocketExecutionInput(
            base_url="https://api.example.test/v1",
            path_template="/events?room={{ROOM}}",
            headers_template={"Authorization": "Bearer {{secret.API_TOKEN}}"},
            variables={"ROOM": "qa"},
            secret_names=("API_TOKEN",),
            message_template="subscribe {{ROOM}}",
            timeout_seconds=10,
            additional_message_templates=("next {{ROOM}}",),
            receive_count=2,
            ping_interval_seconds=15,
            max_reconnect_attempts=1,
            assertions=(WebSocketMessageAssertion(1, "json_path_equals", "$.state", '"done"'),),
        ),
        environment_id="environment-1",
        store_factory=Secrets,
        runner=WebSocketRunner(connect),
    )

    assert captured["uri"] == "wss://api.example.test/v1/events?room=qa"
    assert captured["additional_headers"] == {"Authorization": "Bearer top-secret"}
    assert captured["ping_interval"] == 15
    assert connection.sent == ["subscribe qa", "next qa"]
    assert result.message == "ack ***"
    assert [item.message for item in result.responses] == ["ack ***", '{"state":"done"}']
    assert result.assertion_results[0].passed is True
    assert "top-secret" not in repr(result)


class RecordingRepository:
    def __init__(self) -> None:
        self.errors: list[tuple[str, str, str]] = []
        self.cancelled: list[str] = []
        self.timed_out: list[str] = []

    def recover_interrupted(self, *, now: object) -> None:
        return None

    def mark_error(self, run_id: str, *, code: str, message: str, now: object) -> None:
        self.errors.append((run_id, code, message))

    def mark_cancelled(self, run_id: str, *, now: object) -> None:
        self.cancelled.append(run_id)

    def mark_timeout(self, run_id: str, *, now: object) -> None:
        self.timed_out.append(run_id)


class ManagedProcess:
    def __init__(self, *, alive: bool, exitcode: int | None) -> None:
        self.alive = alive
        self.exitcode = exitcode
        self.terminate_calls = 0
        self.join_timeouts: list[float | None] = []

    def start(self) -> None:
        return None

    def join(self, timeout: float | None = None) -> None:
        self.join_timeouts.append(timeout)

    def is_alive(self) -> bool:
        return self.alive

    def terminate(self) -> None:
        self.terminate_calls += 1
        self.alive = False
        self.exitcode = -15


class ProcessContext:
    def Process(self, **_kwargs: object) -> ManagedProcess:
        return ManagedProcess(alive=True, exitcode=None)


def manager(
    monkeypatch: object, repository: RecordingRepository
) -> WebSocketExecutionWorkerManager:
    monkeypatch.setattr(  # type: ignore[attr-defined]
        multiprocessing, "get_context", lambda _method: ProcessContext()
    )
    return WebSocketExecutionWorkerManager(
        cast(SqlModelWebSocketExecutionRepository, repository),
        database_url="sqlite:///unused.db",
        timeout_seconds=10,
    )


def test_worker_manager_covers_cancel_timeout_and_crash(monkeypatch: object) -> None:
    repository = RecordingRepository()
    subject = manager(monkeypatch, repository)
    cancelled = ManagedProcess(alive=True, exitcode=None)
    subject._processes["run-cancel"] = cast(BaseProcess, cancelled)
    subject.cancel("run-cancel")

    timed_out = ManagedProcess(alive=True, exitcode=None)
    subject._processes["run-timeout"] = cast(BaseProcess, timed_out)
    subject._supervise("run-timeout", cast(BaseProcess, timed_out))

    crashed = ManagedProcess(alive=False, exitcode=7)
    subject._processes["run-crash"] = cast(BaseProcess, crashed)
    subject._supervise("run-crash", cast(BaseProcess, crashed))

    assert repository.cancelled == ["run-cancel"]
    assert repository.timed_out == ["run-timeout"]
    assert repository.errors == [
        ("run-crash", "WEBSOCKET_WORKER_CRASHED", "WebSocket 执行进程意外退出。")
    ]
    assert cancelled.terminate_calls == 1
    assert timed_out.terminate_calls == 1


def test_worker_process_args_never_include_secret(monkeypatch: object) -> None:
    repository = RecordingRepository()
    subject = manager(monkeypatch, repository)
    captured: dict[str, object] = {}

    class CapturingContext:
        def Process(self, **kwargs: object) -> ManagedProcess:
            captured.update(kwargs)
            return ManagedProcess(alive=True, exitcode=None)

    subject._context = cast(object, CapturingContext())  # type: ignore[assignment]
    subject.launch(WebSocketExecutionTaskRequest("run-1"))

    assert captured["args"] == (
        "sqlite:///unused.db",
        WebSocketExecutionTaskRequest("run-1"),
    )
    assert "top-secret" not in repr(captured)
