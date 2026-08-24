from datetime import UTC, datetime

import pytest

from backend.app.application.websocket_execution import WebSocketExecutionService
from backend.app.core.errors import AppError
from backend.app.domain.http_execution import HttpEnvironment
from backend.app.domain.websocket_execution import (
    WebSocketExecution,
    WebSocketExecutionStartInput,
    WebSocketExecutionTaskRequest,
    WebSocketMessageAssertion,
)
from backend.app.domain.workspace import Workspace

NOW = datetime(2026, 8, 16, 2, 0, tzinfo=UTC)
WORKSPACE = Workspace("workspace-1", "支付", "C:/qa/pay", NOW, NOW)
ENVIRONMENT = HttpEnvironment(
    "environment-1",
    WORKSPACE.id,
    "开发环境",
    "https://api.example.test/v1",
    {"ROOM": "qa"},
    ("API_TOKEN",),
    NOW,
    NOW,
)


def execution(status: str = "queued") -> WebSocketExecution:
    return WebSocketExecution(
        "run-1",
        WORKSPACE.id,
        ENVIRONMENT.id,
        ENVIRONMENT.name,
        ENVIRONMENT.base_url,
        "/events?room={{ROOM}}",
        {"Authorization": "Bearer {{secret.API_TOKEN}}"},
        ENVIRONMENT.variables,
        ENVIRONMENT.secret_names,
        "hello",
        10,
        status,  # type: ignore[arg-type]
        0,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        NOW,
        None,
        None,
        (),
    )


class Workspaces:
    def get(self, workspace_id: str) -> Workspace | None:
        return WORKSPACE if workspace_id == WORKSPACE.id else None


class Environments:
    def get_environment(self, workspace_id: str, environment_id: str) -> HttpEnvironment | None:
        if workspace_id == WORKSPACE.id and environment_id == ENVIRONMENT.id:
            return ENVIRONMENT
        return None


class Repository:
    def __init__(self) -> None:
        self.run = execution()
        self.created: WebSocketExecutionStartInput | None = None

    def create_run(self, **kwargs: object) -> WebSocketExecution:
        self.created = kwargs["input"]  # type: ignore[assignment]
        return self.run

    def list_runs(self, workspace_id: str) -> list[WebSocketExecution]:
        return [self.run]

    def get_run(self, workspace_id: str, run_id: str) -> WebSocketExecution | None:
        return self.run if workspace_id == WORKSPACE.id and run_id == self.run.id else None


class Worker:
    def __init__(self) -> None:
        self.launched: list[WebSocketExecutionTaskRequest] = []
        self.cancelled: list[str] = []

    def recover_interrupted(self) -> None:
        return None

    def launch(self, request: WebSocketExecutionTaskRequest) -> None:
        self.launched.append(request)

    def cancel(self, run_id: str) -> None:
        self.cancelled.append(run_id)


def service(
    repository: Repository | None = None, worker: Worker | None = None
) -> WebSocketExecutionService:
    return WebSocketExecutionService(
        Workspaces(),
        Environments(),
        repository or Repository(),
        worker or Worker(),
        clock=lambda: NOW,
        id_factory=lambda: "run-1",
    )


def test_start_freezes_environment_and_launches_worker() -> None:
    repository = Repository()
    worker = Worker()
    use_cases = service(repository, worker)
    run = use_cases.start(
        WORKSPACE.id,
        WebSocketExecutionStartInput(
            ENVIRONMENT.id,
            "/events?room={{ROOM}}",
            {"Authorization": "Bearer {{secret.API_TOKEN}}"},
            '{"action":"subscribe"}',
            10,
            ('{"action":"next"}',),
            2,
            15,
            1,
            (WebSocketMessageAssertion(1, "text_contains", None, "done"),),
        ),
    )

    assert run.id == "run-1"
    assert repository.created is not None
    assert repository.created.path == "/events?room={{ROOM}}"
    assert repository.created.additional_messages == ('{"action":"next"}',)
    assert repository.created.receive_count == 2
    assert repository.created.ping_interval_seconds == 15
    assert repository.created.max_reconnect_attempts == 1
    assert repository.created.assertions[0].message_index == 1
    assert worker.launched == [WebSocketExecutionTaskRequest("run-1")]


@pytest.mark.parametrize("path", ["events", "//evil.example/socket", "/bad#fragment"])
def test_start_rejects_unsafe_path(path: str) -> None:
    with pytest.raises(AppError) as raised:
        service().start(
            WORKSPACE.id,
            WebSocketExecutionStartInput(ENVIRONMENT.id, path, {}, "hello", 10),
        )
    assert raised.value.code == "WEBSOCKET_REQUEST_INVALID"


def test_cancel_delegates_only_for_active_run() -> None:
    repository = Repository()
    worker = Worker()
    use_cases = service(repository, worker)

    use_cases.cancel(WORKSPACE.id, "run-1")

    assert worker.cancelled == ["run-1"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"additional_messages": tuple("x" for _ in range(10))},
        {"additional_messages": ("",)},
        {"receive_count": 0},
        {"receive_count": 21},
        {"ping_interval_seconds": 4},
        {"max_reconnect_attempts": 2},
        {
            "receive_count": 1,
            "assertions": (WebSocketMessageAssertion(1, "text_equals", None, "later"),),
        },
    ],
)
def test_start_rejects_invalid_sequence_heartbeat_reconnect_or_assertions(
    overrides: dict[str, object],
) -> None:
    values: dict[str, object] = {
        "environment_id": ENVIRONMENT.id,
        "path": "/events",
        "headers": {},
        "message": "hello",
        "timeout_seconds": 10,
    }
    values.update(overrides)

    with pytest.raises(AppError) as raised:
        service().start(WORKSPACE.id, WebSocketExecutionStartInput(**values))  # type: ignore[arg-type]

    assert raised.value.code == "WEBSOCKET_REQUEST_INVALID"
