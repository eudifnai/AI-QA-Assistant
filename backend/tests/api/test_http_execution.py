from datetime import UTC, datetime

from fastapi.testclient import TestClient

from backend.app.application.http_execution import HttpExecutionUseCases
from backend.app.domain.http_execution import (
    HttpEnvironment,
    HttpEnvironmentInput,
    HttpExecution,
    HttpExecutionStartInput,
)
from backend.app.main import create_app

NOW = datetime(2026, 8, 15, 1, 0, tzinfo=UTC)
ENVIRONMENT = HttpEnvironment(
    "environment-1",
    "workspace-1",
    "开发环境",
    "https://api.example.test/v1",
    {"USER_ID": "42"},
    ("API_TOKEN",),
    NOW,
    NOW,
)
RUN = HttpExecution(
    "run-1",
    "workspace-1",
    "environment-1",
    "开发环境",
    "GET",
    "https://api.example.test/v1",
    "/users/{{USER_ID}}",
    {"Authorization": "Bearer {{secret.API_TOKEN}}"},
    None,
    20,
    "queued",
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


class StubHttpExecution(HttpExecutionUseCases):
    environment_input: HttpEnvironmentInput | None = None
    execution_input: HttpExecutionStartInput | None = None
    secret_value: str | None = None

    def list_environments(self, workspace_id: str) -> list[HttpEnvironment]:
        return [ENVIRONMENT]

    def create_environment(self, workspace_id: str, input: HttpEnvironmentInput) -> HttpEnvironment:
        self.environment_input = input
        return ENVIRONMENT

    def update_environment(
        self, workspace_id: str, environment_id: str, input: HttpEnvironmentInput
    ) -> HttpEnvironment:
        self.environment_input = input
        return ENVIRONMENT

    def delete_environment(self, workspace_id: str, environment_id: str) -> None:
        return None

    def set_secret(
        self, workspace_id: str, environment_id: str, name: str, secret: str
    ) -> HttpEnvironment:
        self.secret_value = secret
        return ENVIRONMENT

    def delete_secret(self, workspace_id: str, environment_id: str, name: str) -> HttpEnvironment:
        return ENVIRONMENT

    def start(self, workspace_id: str, input: HttpExecutionStartInput) -> HttpExecution:
        self.execution_input = input
        return RUN

    def list_runs(self, workspace_id: str) -> list[HttpExecution]:
        return [RUN]

    def get_run(self, workspace_id: str, run_id: str) -> HttpExecution:
        return RUN

    def cancel(self, workspace_id: str, run_id: str) -> HttpExecution:
        return RUN

    def rerun(self, workspace_id: str, run_id: str) -> HttpExecution:
        return RUN


def test_http_environment_secret_and_execution_api() -> None:
    service = StubHttpExecution()
    app = create_app(http_execution_service=service)
    environment_body = {
        "name": "开发环境",
        "base_url": "https://api.example.test/v1",
        "variables": {"USER_ID": "42"},
    }
    execution_body = {
        "environment_id": "environment-1",
        "method": "GET",
        "path": "/users/{{USER_ID}}",
        "headers": {"Authorization": "Bearer {{secret.API_TOKEN}}"},
        "body": None,
        "timeout_seconds": 20,
    }
    with TestClient(app) as client:
        listed = client.get("/api/workspaces/workspace-1/http-environments")
        created = client.post(
            "/api/workspaces/workspace-1/http-environments", json=environment_body
        )
        updated = client.put(
            "/api/workspaces/workspace-1/http-environments/environment-1",
            json=environment_body,
        )
        secret = client.put(
            "/api/workspaces/workspace-1/http-environments/environment-1/secrets/API_TOKEN",
            json={"secret": "top-secret"},
        )
        started = client.post("/api/workspaces/workspace-1/http-executions", json=execution_body)
        runs = client.get("/api/workspaces/workspace-1/http-executions")
        fetched = client.get("/api/workspaces/workspace-1/http-executions/run-1")
        cancelled = client.post("/api/workspaces/workspace-1/http-executions/run-1/cancel")
        rerun = client.post("/api/workspaces/workspace-1/http-executions/run-1/rerun")
        deleted = client.delete("/api/workspaces/workspace-1/http-environments/environment-1")

    assert listed.status_code == 200
    assert created.status_code == 201
    assert updated.status_code == 200
    assert secret.status_code == 200
    assert "top-secret" not in secret.text
    assert secret.json()["secret_names"] == ["API_TOKEN"]
    assert started.status_code == 202
    assert started.json()["headers_template"] == {"Authorization": "Bearer {{secret.API_TOKEN}}"}
    assert runs.status_code == fetched.status_code == cancelled.status_code == 200
    assert rerun.status_code == 202
    assert deleted.status_code == 204
    assert service.secret_value == "top-secret"
    assert service.execution_input == HttpExecutionStartInput(
        "environment-1",
        "GET",
        "/users/{{USER_ID}}",
        {"Authorization": "Bearer {{secret.API_TOKEN}}"},
        None,
        20,
    )


def test_http_api_rejects_extra_fields_and_invalid_timeout() -> None:
    app = create_app(http_execution_service=StubHttpExecution())
    with TestClient(app) as client:
        response = client.post(
            "/api/workspaces/workspace-1/http-executions",
            json={
                "environment_id": "environment-1",
                "method": "GET",
                "path": "/health",
                "headers": {},
                "timeout_seconds": 0,
                "secret": "must-not-be-accepted",
            },
        )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert "must-not-be-accepted" not in response.text
