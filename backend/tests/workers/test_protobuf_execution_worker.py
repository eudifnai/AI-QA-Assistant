import multiprocessing
from multiprocessing.process import BaseProcess
from typing import Any, ClassVar, cast

import pytest
from google.protobuf import descriptor_pb2

import backend.app.workers.protobuf_execution as worker_module
from backend.app.domain.protobuf_execution import (
    ProtoExecutionInput,
    ProtoExecutionTaskRequest,
    ProtoFieldAssertion,
    ProtoTransportResult,
)
from backend.app.infrastructure.protobuf_codec import DynamicProtobufCodec
from backend.app.infrastructure.protobuf_execution import SqlModelProtoExecutionRepository
from backend.app.infrastructure.protobuf_runner import ProtoRunnerError
from backend.app.workers.protobuf_execution import ProtoExecutionWorkerManager, _run_request


def descriptor_bytes() -> bytes:
    descriptor_set = descriptor_pb2.FileDescriptorSet()
    file = descriptor_set.file.add()
    file.name = "echo.proto"
    file.package = "demo"
    file.syntax = "proto3"
    request = file.message_type.add()
    request.name = "Request"
    field = request.field.add()
    field.name = "id"
    field.number = 1
    field.type = descriptor_pb2.FieldDescriptorProto.TYPE_INT32
    response = file.message_type.add()
    response.name = "Response"
    for number, (name, field_type) in enumerate(
        [
            ("ok", descriptor_pb2.FieldDescriptorProto.TYPE_BOOL),
            ("note", descriptor_pb2.FieldDescriptorProto.TYPE_STRING),
        ],
        1,
    ):
        field = response.field.add()
        field.name = name
        field.number = number
        field.type = field_type
    return bytes(descriptor_set.SerializeToString())


class Secrets:
    def get(self, environment_id: str, name: str) -> str | None:
        assert environment_id == "environment-1"
        return "secret-value" if name == "TOKEN" else None


class Runner:
    def __init__(self, response: bytes) -> None:
        self.response = response
        self.captured: dict[str, Any] = {}

    def execute(self, **kwargs: Any) -> ProtoTransportResult:
        self.captured = kwargs
        return ProtoTransportResult(200, {"X-Echo": "***"}, self.response, 12)


def test_worker_encodes_sends_decodes_redacts_and_asserts() -> None:
    descriptor = descriptor_bytes()
    codec = DynamicProtobufCodec()
    response = codec.encode(descriptor, "demo.Response", {"ok": True, "note": "secret-value"})
    runner = Runner(response)

    result = _run_request(
        ProtoExecutionInput(
            "run-1",
            "environment-1",
            "https://api.example.com/v1",
            {"TENANT": "qa"},
            ("TOKEN",),
            descriptor,
            "/echo/{{TENANT}}",
            {"Authorization": "Bearer {{secret.TOKEN}}"},
            "demo.Request",
            "demo.Response",
            {"id": 7},
            10,
            (ProtoFieldAssertion("$.ok", "true"),),
        ),
        store_factory=Secrets,
        runner=runner,  # type: ignore[arg-type]
        codec=codec,
    )

    assert runner.captured["url"] == "https://api.example.com/v1/echo/qa"
    assert runner.captured["headers"] == {"Authorization": "Bearer secret-value"}
    assert runner.captured["payload"] == codec.encode(descriptor, "demo.Request", {"id": 7})
    assert result.payload == {"ok": True, "note": "***"}
    assert result.assertion_results[0].passed is True
    assert "secret-value" not in repr(result)


class RecordingRepository:
    def __init__(self) -> None:
        self.errors: list[tuple[str, str, str]] = []
        self.cancelled: list[str] = []
        self.timed_out: list[str] = []

    def recover_interrupted(self, *, now: object) -> None:
        return

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

    def start(self) -> None:
        return

    def join(self, timeout: float | None = None) -> None:
        return

    def is_alive(self) -> bool:
        return self.alive

    def terminate(self) -> None:
        self.terminate_calls += 1
        self.alive = False
        self.exitcode = -15


class StartFailingProcess(ManagedProcess):
    def start(self) -> None:
        raise RuntimeError("spawn failed")


class ProcessContext:
    def Process(self, **_kwargs: object) -> ManagedProcess:
        return ManagedProcess(alive=True, exitcode=None)


def manager(monkeypatch: object, repository: RecordingRepository) -> ProtoExecutionWorkerManager:
    monkeypatch.setattr(multiprocessing, "get_context", lambda _method: ProcessContext())  # type: ignore[attr-defined]
    return ProtoExecutionWorkerManager(
        cast(SqlModelProtoExecutionRepository, repository),
        database_url="sqlite:///unused.db",
        timeout_seconds=10,
    )


def test_worker_manager_covers_cancel_timeout_crash_and_secret_free_args(
    monkeypatch: object,
) -> None:
    repository = RecordingRepository()
    subject = manager(monkeypatch, repository)
    cancelled = ManagedProcess(alive=True, exitcode=None)
    subject._processes["cancel"] = cast(BaseProcess, cancelled)
    subject.cancel("cancel")
    timed_out = ManagedProcess(alive=True, exitcode=None)
    subject._processes["timeout"] = cast(BaseProcess, timed_out)
    subject._supervise("timeout", cast(BaseProcess, timed_out))
    crashed = ManagedProcess(alive=False, exitcode=7)
    subject._processes["crash"] = cast(BaseProcess, crashed)
    subject._supervise("crash", cast(BaseProcess, crashed))

    captured: dict[str, object] = {}

    class CapturingContext:
        def Process(self, **kwargs: object) -> ManagedProcess:
            captured.update(kwargs)
            return ManagedProcess(alive=False, exitcode=0)

    subject._context = cast(Any, CapturingContext())
    subject.launch(ProtoExecutionTaskRequest("run-1"))

    assert repository.cancelled == ["cancel"]
    assert repository.timed_out == ["timeout"]
    assert repository.errors == [("crash", "PROTO_WORKER_CRASHED", "Protobuf 执行进程意外退出。")]
    assert captured["args"] == ("sqlite:///unused.db", ProtoExecutionTaskRequest("run-1"))
    assert "secret-value" not in repr(captured)


def test_worker_manager_marks_a_spawn_failure_as_error(monkeypatch: object) -> None:
    repository = RecordingRepository()
    subject = manager(monkeypatch, repository)

    class FailingContext:
        def Process(self, **_kwargs: object) -> ManagedProcess:
            return StartFailingProcess(alive=False, exitcode=None)

    subject._context = cast(Any, FailingContext())
    with pytest.raises(RuntimeError, match="spawn failed"):
        subject.launch(ProtoExecutionTaskRequest("run-start-failure"))

    assert repository.errors == [
        (
            "run-start-failure",
            "PROTO_WORKER_START_FAILED",
            "无法启动 Protobuf 执行进程。",
        )
    ]


def test_worker_job_maps_a_known_transport_failure_to_safe_terminal_state(
    monkeypatch: object,
) -> None:
    class JobRepository:
        failed: ClassVar[list[tuple[str, str, str]]] = []

        def __init__(self, _engine: object) -> None:
            return

        def load_execution_input(self, run_id: str) -> object:
            return object()

        def mark_running(self, run_id: str, *, pid: int, now: object) -> None:
            return

        def mark_failed(self, run_id: str, *, code: str, message: str, now: object) -> None:
            self.failed.append((run_id, code, message))

    monkeypatch.setattr(worker_module, "create_database_engine", lambda _url: object())  # type: ignore[attr-defined]
    monkeypatch.setattr(worker_module, "SqlModelProtoExecutionRepository", JobRepository)  # type: ignore[attr-defined]
    monkeypatch.setattr(  # type: ignore[attr-defined]
        worker_module,
        "_run_request",
        lambda _execution: (_ for _ in ()).throw(ProtoRunnerError("timeout")),
    )

    worker_module.run_protobuf_execution_job(
        "sqlite:///unused.db", ProtoExecutionTaskRequest("run-timeout")
    )

    assert JobRepository.failed == [("run-timeout", "PROTO_REQUEST_TIMEOUT", "Protobuf 请求超时。")]
