import multiprocessing
from multiprocessing.process import BaseProcess
from typing import cast

import pytest

import backend.app.workers.http_execution as worker_module
from backend.app.domain.http_execution import (
    HttpExecutionInput,
    HttpExecutionResult,
    HttpExecutionTaskRequest,
)
from backend.app.infrastructure.http_execution import SqlModelHttpExecutionRepository
from backend.app.infrastructure.http_runner import HttpRunnerError, StdlibHttpRunner
from backend.app.workers.http_execution import (
    HttpExecutionWorkerManager,
    _execute_with_retries,
    _failure,
    _run_request,
)


class Secrets:
    def get(self, environment_id: str, name: str) -> str | None:
        assert environment_id == "environment-1"
        return "top-secret" if name == "API_TOKEN" else None


class Runner:
    values: dict[str, object] | None = None

    def execute(self, **values: object) -> HttpExecutionResult:
        self.values = values
        return HttpExecutionResult(200, {}, "ok", "text", 2, 10)


def test_worker_reads_secret_by_reference_and_expands_only_in_transport() -> None:
    execution = HttpExecutionInput(
        "run-1",
        "https://api.example.test/v1",
        {"USER_ID": "42"},
        ("API_TOKEN",),
        "GET",
        "/users/{{USER_ID}}",
        {"Authorization": "Bearer {{secret.API_TOKEN}}"},
        None,
        20,
    )
    runner = Runner()

    result = _run_request(
        execution,
        environment_id="environment-1",
        store_factory=Secrets,  # type: ignore[arg-type]
        runner=cast(StdlibHttpRunner, runner),
    )

    assert result.status_code == 200
    assert runner.values is not None
    assert runner.values["url"] == "https://api.example.test/v1/users/42"
    assert runner.values["headers"] == {"Authorization": "Bearer top-secret"}
    assert runner.values["secrets"] == ("top-secret",)
    assert "top-secret" not in repr(execution)


def test_worker_failure_messages_are_stable_and_safe() -> None:
    assert _failure("timeout") == ("HTTP_REQUEST_TIMEOUT", "等待目标 HTTP 服务响应超时。")
    assert _failure("unknown") == ("HTTP_REQUEST_FAILED", "HTTP 请求执行失败。")


def test_worker_retries_retryable_failure_for_safe_method(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    events: list[tuple[str, int]] = []
    result = HttpExecutionResult(200, {}, "ok", "text", 2, 5)

    def run_request(*_args: object, **_kwargs: object) -> HttpExecutionResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise HttpRunnerError("unavailable")
        return result

    monkeypatch.setattr(worker_module, "_run_request", run_request)
    execution = HttpExecutionInput(
        "run-1", "https://api.test", {}, (), "GET", "/health", {}, None, 5, 3
    )

    actual = _execute_with_retries(
        execution,
        environment_id="environment-1",
        event=lambda _level, code, _message, attempt: events.append((code, attempt)),
        sleeper=lambda _seconds: None,
    )

    assert actual is result
    assert calls == 2
    assert events == [
        ("HTTP_REQUEST_ATTEMPT_STARTED", 1),
        ("HTTP_REQUEST_RETRY_SCHEDULED", 1),
        ("HTTP_REQUEST_ATTEMPT_STARTED", 2),
    ]


def test_worker_never_retries_non_idempotent_method_even_if_persisted_input_is_corrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fail(*_args: object, **_kwargs: object) -> HttpExecutionResult:
        nonlocal calls
        calls += 1
        raise HttpRunnerError("timeout")

    monkeypatch.setattr(worker_module, "_run_request", fail)
    execution = HttpExecutionInput(
        "run-1", "https://api.test", {}, (), "POST", "/orders", {}, "{}", 5, 3
    )

    with pytest.raises(HttpRunnerError, match="timeout"):
        _execute_with_retries(
            execution,
            environment_id="environment-1",
            event=lambda *_args: None,
            sleeper=lambda _seconds: None,
        )

    assert calls == 1


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
    monkeypatch: object,
    repository: RecordingRepository,
) -> HttpExecutionWorkerManager:
    monkeypatch.setattr(multiprocessing, "get_context", lambda _method: ProcessContext())  # type: ignore[attr-defined]
    return HttpExecutionWorkerManager(
        cast(SqlModelHttpExecutionRepository, repository),
        database_url="sqlite:///unused.db",
        timeout_seconds=10,
    )


def test_worker_manager_cancels_live_process(monkeypatch: object) -> None:
    repository = RecordingRepository()
    subject = manager(monkeypatch, repository)
    process = ManagedProcess(alive=True, exitcode=None)
    subject._processes["run-cancel"] = cast(BaseProcess, process)

    subject.cancel("run-cancel")

    assert repository.cancelled == ["run-cancel"]
    assert process.terminate_calls == 1
    assert process.join_timeouts == [5]


def test_worker_manager_marks_timeout_and_crash(monkeypatch: object) -> None:
    repository = RecordingRepository()
    subject = manager(monkeypatch, repository)
    timed_out = ManagedProcess(alive=True, exitcode=None)
    subject._processes["run-timeout"] = cast(BaseProcess, timed_out)

    subject._supervise("run-timeout", cast(BaseProcess, timed_out))

    assert repository.timed_out == ["run-timeout"]
    assert timed_out.terminate_calls == 1

    crashed = ManagedProcess(alive=False, exitcode=7)
    subject._processes["run-crash"] = cast(BaseProcess, crashed)
    subject._supervise("run-crash", cast(BaseProcess, crashed))
    assert repository.errors == [("run-crash", "HTTP_WORKER_CRASHED", "HTTP 执行进程意外退出。")]


def test_worker_process_args_never_include_secret(monkeypatch: object) -> None:
    repository = RecordingRepository()
    subject = manager(monkeypatch, repository)
    captured: dict[str, object] = {}

    class CapturingContext:
        def Process(self, **kwargs: object) -> ManagedProcess:
            captured.update(kwargs)
            return ManagedProcess(alive=True, exitcode=None)

    subject._context = cast(object, CapturingContext())  # type: ignore[assignment]
    subject.launch(HttpExecutionTaskRequest("run-1"))

    assert captured["args"] == ("sqlite:///unused.db", HttpExecutionTaskRequest("run-1"))
    assert "top-secret" not in repr(captured)
