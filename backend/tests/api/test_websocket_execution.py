from datetime import UTC, datetime

from fastapi.testclient import TestClient

from backend.app.application.websocket_execution import WebSocketExecutionUseCases
from backend.app.domain.websocket_execution import (
    WebSocketExecution,
    WebSocketExecutionStartInput,
)
from backend.app.main import create_app

NOW = datetime(2026, 8, 16, 3, 0, tzinfo=UTC)
RUN = WebSocketExecution(
    "run-1",
    "workspace-1",
    "environment-1",
    "开发环境",
    "https://api.example.test/v1",
    "/events",
    {},
    {},
    (),
    "hello",
    10,
    "queued",
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


class StubWebSocketExecution(WebSocketExecutionUseCases):
    execution_input: WebSocketExecutionStartInput | None = None

    def start(self, workspace_id: str, input: WebSocketExecutionStartInput) -> WebSocketExecution:
        self.execution_input = input
        return RUN

    def list_runs(self, workspace_id: str) -> list[WebSocketExecution]:
        return [RUN]

    def get_run(self, workspace_id: str, run_id: str) -> WebSocketExecution:
        return RUN

    def cancel(self, workspace_id: str, run_id: str) -> WebSocketExecution:
        return RUN


def test_websocket_execution_api_accepts_template_without_secret_value() -> None:
    service = StubWebSocketExecution()
    app = create_app(websocket_execution_service=service)
    body = {
        "environment_id": "environment-1",
        "path": "/events?room={{ROOM}}",
        "headers": {"Authorization": "Bearer {{secret.API_TOKEN}}"},
        "message": '{"action":"subscribe"}',
        "timeout_seconds": 10,
        "additional_messages": ['{"action":"next"}'],
        "receive_count": 2,
        "ping_interval_seconds": 15,
        "max_reconnect_attempts": 1,
        "assertions": [
            {
                "message_index": 1,
                "kind": "json_path_equals",
                "path": "$.state",
                "expected": '"done"',
            }
        ],
    }

    with TestClient(app) as client:
        response = client.post("/api/workspaces/workspace-1/websocket-executions", json=body)
        listed = client.get("/api/workspaces/workspace-1/websocket-executions")
        cancelled = client.post("/api/workspaces/workspace-1/websocket-executions/run-1/cancel")

    assert response.status_code == 202
    assert listed.status_code == 200
    assert cancelled.status_code == 200
    assert service.execution_input is not None
    assert service.execution_input.message == '{"action":"subscribe"}'
    assert service.execution_input.additional_messages == ('{"action":"next"}',)
    assert service.execution_input.receive_count == 2
    assert service.execution_input.max_reconnect_attempts == 1
    assert response.json()["responses"] == []
    assert "top-secret" not in response.text
