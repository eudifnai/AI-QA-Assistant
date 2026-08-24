from datetime import UTC, datetime

import pytest

from backend.app.application.http_execution import HttpExecutionService
from backend.app.core.errors import AppError
from backend.app.domain.http_execution import (
    HttpAssertion,
    HttpEnvironment,
    HttpEnvironmentInput,
    HttpExecution,
    HttpExecutionStartInput,
    HttpExecutionTaskRequest,
)
from backend.app.domain.workspace import Workspace

NOW = datetime(2026, 8, 15, 1, 0, tzinfo=UTC)
WORKSPACE = Workspace("workspace-1", "支付", "C:/qa/pay", NOW, NOW)


def environment(secret_names: tuple[str, ...] = ()) -> HttpEnvironment:
    return HttpEnvironment(
        "environment-1",
        WORKSPACE.id,
        "开发环境",
        "https://api.example.test/v1",
        {"USER_ID": "42"},
        secret_names,
        NOW,
        NOW,
    )


def execution(status: str = "queued") -> HttpExecution:
    return HttpExecution(
        "run-1",
        WORKSPACE.id,
        "environment-1",
        "开发环境",
        "POST",
        "https://api.example.test/v1",
        "/users/{{USER_ID}}",
        {"Authorization": "Bearer {{secret.API_TOKEN}}"},
        '{"name":"qa"}',
        20,
        status,  # type: ignore[arg-type]
        0,
        None,
        None,
        {},
        None,
        None,
        None,
        None,
        None,
        None,
        NOW,
        None,
        None,
    )


class Workspaces:
    def get(self, workspace_id: str) -> Workspace | None:
        return WORKSPACE if workspace_id == WORKSPACE.id else None


class Repository:
    def __init__(self) -> None:
        self.environment = environment()
        self.run = execution()
        self.created_environment: HttpEnvironmentInput | None = None
        self.created_run: HttpExecutionStartInput | None = None

    def list_environments(self, workspace_id: str) -> list[HttpEnvironment]:
        return [self.environment]

    def get_environment(self, workspace_id: str, environment_id: str) -> HttpEnvironment | None:
        if workspace_id == WORKSPACE.id and environment_id == self.environment.id:
            return self.environment
        return None

    def find_environment_by_name(self, workspace_id: str, name_key: str) -> HttpEnvironment | None:
        return None

    def create_environment(
        self,
        environment_id: str,
        workspace_id: str,
        input: HttpEnvironmentInput,
        *,
        now: datetime,
    ) -> HttpEnvironment:
        self.created_environment = input
        self.environment = HttpEnvironment(
            environment_id, workspace_id, input.name, input.base_url, input.variables, (), now, now
        )
        return self.environment

    def update_environment(
        self, environment_id: str, input: HttpEnvironmentInput, *, now: datetime
    ) -> HttpEnvironment:
        self.environment = HttpEnvironment(
            environment_id,
            WORKSPACE.id,
            input.name,
            input.base_url,
            input.variables,
            self.environment.secret_names,
            NOW,
            now,
        )
        return self.environment

    def delete_environment(self, environment_id: str) -> None:
        return None

    def add_secret_name(self, environment_id: str, name: str, *, now: datetime) -> HttpEnvironment:
        self.environment = environment(tuple(sorted({*self.environment.secret_names, name})))
        return self.environment

    def remove_secret_name(
        self, environment_id: str, name: str, *, now: datetime
    ) -> HttpEnvironment:
        self.environment = environment(
            tuple(item for item in self.environment.secret_names if item != name)
        )
        return self.environment

    def create_run(
        self,
        *,
        run_id: str,
        workspace_id: str,
        environment: HttpEnvironment,
        input: HttpExecutionStartInput,
        created_at: datetime,
    ) -> HttpExecution:
        self.created_run = input
        self.run = execution()
        return self.run

    def list_runs(self, workspace_id: str) -> list[HttpExecution]:
        return [self.run]

    def get_run(self, workspace_id: str, run_id: str) -> HttpExecution | None:
        return self.run if workspace_id == WORKSPACE.id and run_id == "run-1" else None

    def recreate_run(
        self, source_run_id: str, new_run_id: str, *, created_at: datetime
    ) -> HttpExecution:
        self.run = execution()
        return self.run


class Secrets:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get(self, environment_id: str, name: str) -> str | None:
        return self.values.get((environment_id, name))

    def set(self, environment_id: str, name: str, secret: str) -> None:
        self.values[(environment_id, name)] = secret

    def delete(self, environment_id: str, name: str) -> None:
        self.values.pop((environment_id, name), None)


class Worker:
    request: HttpExecutionTaskRequest | None = None
    cancelled: str | None = None
    recovered = False

    def launch(self, request: HttpExecutionTaskRequest) -> None:
        self.request = request

    def cancel(self, run_id: str) -> None:
        self.cancelled = run_id

    def recover_interrupted(self) -> None:
        self.recovered = True


def service(
    repository: Repository | None = None,
    secrets: Secrets | None = None,
    worker: Worker | None = None,
) -> HttpExecutionService:
    return HttpExecutionService(
        Workspaces(),
        repository or Repository(),
        secrets or Secrets(),
        worker or Worker(),
        clock=lambda: NOW,
        id_factory=lambda: "run-1",
    )


def test_environment_normalizes_url_and_keeps_only_public_variables() -> None:
    repository = Repository()

    result = service(repository).create_environment(
        WORKSPACE.id,
        HttpEnvironmentInput(" 开发环境 ", "https://api.example.test/v1/", {"USER_ID": "42"}),
    )

    assert result.base_url == "https://api.example.test/v1"
    assert result.secret_names == ()
    assert repository.created_environment == HttpEnvironmentInput(
        "开发环境", "https://api.example.test/v1", {"USER_ID": "42"}
    )


def test_secret_value_is_written_only_to_secret_store() -> None:
    repository = Repository()
    secrets = Secrets()

    result = service(repository, secrets).set_secret(
        WORKSPACE.id, "environment-1", "API_TOKEN", "top-secret"
    )

    assert result.secret_names == ("API_TOKEN",)
    assert secrets.values[("environment-1", "API_TOKEN")] == "top-secret"
    assert "top-secret" not in repr(repository.environment)


def test_start_freezes_template_and_launches_worker_without_secret_value() -> None:
    repository = Repository()
    repository.environment = environment(("API_TOKEN",))
    worker = Worker()
    input = HttpExecutionStartInput(
        "environment-1",
        "POST",
        "/users/{{USER_ID}}",
        {"Authorization": "Bearer {{secret.API_TOKEN}}"},
        '{"source":"desktop"}',
        20,
    )

    run = service(repository, worker=worker).start(WORKSPACE.id, input)

    assert run.status == "queued"
    assert repository.created_run == input
    assert worker.recovered is True
    assert worker.request == HttpExecutionTaskRequest("run-1")
    assert "top-secret" not in repr(repository.created_run)


def test_start_rejects_unknown_template_reference_and_header_injection() -> None:
    subject = service()
    with pytest.raises(AppError) as missing:
        subject.start(
            WORKSPACE.id,
            HttpExecutionStartInput("environment-1", "GET", "/{{UNKNOWN}}", {}, None, 10),
        )
    assert missing.value.code == "HTTP_TEMPLATE_INVALID"

    with pytest.raises(AppError) as injection:
        subject.start(
            WORKSPACE.id,
            HttpExecutionStartInput(
                "environment-1", "GET", "/health", {"X-Test": "ok\r\nInjected: yes"}, None, 10
            ),
        )
    assert injection.value.code == "HTTP_REQUEST_HEADERS_INVALID"


def test_cancel_respects_workspace_scope() -> None:
    worker = Worker()
    subject = service(worker=worker)

    subject.cancel(WORKSPACE.id, "run-1")
    assert worker.cancelled == "run-1"

    with pytest.raises(AppError) as missing:
        subject.get_run("other-workspace", "run-1")
    assert missing.value.code == "WORKSPACE_NOT_FOUND"


def test_retry_is_limited_to_safe_methods_and_valid_attempt_count() -> None:
    subject = service()

    with pytest.raises(AppError) as unsafe:
        subject.start(
            WORKSPACE.id,
            HttpExecutionStartInput(
                "environment-1", "POST", "/orders", {}, "{}", 10, max_attempts=2
            ),
        )
    assert unsafe.value.code == "HTTP_RETRY_METHOD_UNSAFE"

    with pytest.raises(AppError) as invalid:
        subject.start(
            WORKSPACE.id,
            HttpExecutionStartInput(
                "environment-1", "GET", "/health", {}, None, 10, max_attempts=4
            ),
        )
    assert invalid.value.code == "HTTP_RETRY_INVALID"


def test_start_validates_and_freezes_assertions() -> None:
    repository = Repository()
    assertions = (
        HttpAssertion("status_code", None, "200"),
        HttpAssertion("json_path_equals", "$.ok", "true"),
    )

    service(repository).start(
        WORKSPACE.id,
        HttpExecutionStartInput(
            "environment-1", "GET", "/health", {}, None, 10, assertions=assertions
        ),
    )

    assert repository.created_run is not None
    assert repository.created_run.assertions == assertions


def test_terminal_execution_can_rerun_frozen_template() -> None:
    repository = Repository()
    repository.run = execution("passed")
    worker = Worker()

    rerun = service(repository, worker=worker).rerun(WORKSPACE.id, "run-1")

    assert rerun.status == "queued"
    assert worker.request == HttpExecutionTaskRequest("run-1")
