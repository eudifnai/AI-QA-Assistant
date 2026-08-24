from datetime import UTC, datetime

from fastapi.testclient import TestClient

from backend.app.application.protobuf_execution import ProtoExecutionUseCases
from backend.app.domain.protobuf_execution import (
    ProtoExecution,
    ProtoExecutionStartInput,
    ProtoFieldAssertion,
)
from backend.app.main import create_app

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
RUN = ProtoExecution(
    id="run-1",
    workspace_id="workspace-1",
    environment_id="environment-1",
    environment_name="开发环境",
    asset_id="asset-1",
    asset_name="echo.proto",
    asset_sha256="a" * 64,
    service_name="demo.Echo",
    method_name="Call",
    base_url="https://api.example.test/v1",
    path_template="/echo",
    headers_template={"Authorization": "Bearer {{secret.TOKEN}}"},
    request_message_type="demo.Request",
    response_message_type="demo.Response",
    request_payload={"id": 7},
    timeout_seconds=10,
    assertions=(ProtoFieldAssertion("$.ok", "true"),),
    assertion_results=(),
    status="queued",
    progress=0,
    pid=None,
    response_status_code=None,
    response_headers={},
    response_payload=None,
    response_size_bytes=None,
    duration_ms=None,
    error_code=None,
    error_message=None,
    created_at=NOW,
    started_at=None,
    finished_at=None,
    events=(),
)


class StubProtoExecution(ProtoExecutionUseCases):
    execution_input: ProtoExecutionStartInput | None = None

    def start(self, workspace_id: str, input: ProtoExecutionStartInput) -> ProtoExecution:
        self.execution_input = input
        return RUN

    def list_runs(self, workspace_id: str) -> list[ProtoExecution]:
        return [RUN]

    def get_run(self, workspace_id: str, run_id: str) -> ProtoExecution:
        return RUN

    def cancel(self, workspace_id: str, run_id: str) -> ProtoExecution:
        return RUN


def request_body() -> dict[str, object]:
    return {
        "environment_id": "environment-1",
        "asset_id": "asset-1",
        "expected_sha256": "a" * 64,
        "service_name": "demo.Echo",
        "method_name": "Call",
        "path": "/echo/{{TENANT}}",
        "headers": {"Authorization": "Bearer {{secret.TOKEN}}"},
        "request_payload": {"id": 7},
        "timeout_seconds": 10,
        "assertions": [{"path": "$.ok", "expected_json": "true"}],
    }


def test_protobuf_execution_api_starts_lists_gets_and_cancels_without_descriptor() -> None:
    service = StubProtoExecution()
    app = create_app(protobuf_execution_service=service)
    with TestClient(app) as client:
        started = client.post(
            "/api/workspaces/workspace-1/protobuf-executions", json=request_body()
        )
        listed = client.get("/api/workspaces/workspace-1/protobuf-executions")
        loaded = client.get("/api/workspaces/workspace-1/protobuf-executions/run-1")
        cancelled = client.post("/api/workspaces/workspace-1/protobuf-executions/run-1/cancel")

    assert started.status_code == 202
    assert listed.status_code == loaded.status_code == cancelled.status_code == 200
    assert service.execution_input is not None
    assert service.execution_input.request_payload == {"id": 7}
    assert "descriptor" not in started.text
    assert "secret-value" not in started.text


def test_protobuf_execution_api_forbids_unknown_fields() -> None:
    service = StubProtoExecution()
    app = create_app(protobuf_execution_service=service)
    body = request_body()
    body["unknown"] = True
    with TestClient(app) as client:
        response = client.post("/api/workspaces/workspace-1/protobuf-executions", json=body)
    assert response.status_code == 422
    assert service.execution_input is None
