from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.websockets import WebSocketDisconnect

from backend.app.core.config import Settings
from backend.app.domain.task_events import TaskSnapshot
from backend.app.main import create_app

NOW = datetime(2026, 8, 16, 6, 0, tzinfo=UTC)


class ChangingTasks:
    def __init__(self) -> None:
        self.calls = 0

    def list_snapshots(self, workspace_id: str) -> list[TaskSnapshot]:
        assert workspace_id == "workspace-1"
        self.calls += 1
        return [
            TaskSnapshot(
                "analysis",
                "run-1",
                workspace_id,
                "queued" if self.calls == 1 else "running",
                0 if self.calls == 1 else 35,
                NOW,
            )
        ]


def test_task_event_websocket_authenticates_without_token_in_url_and_orders_changes() -> None:
    service = ChangingTasks()
    app = create_app(
        settings=Settings(session_token=SecretStr("desktop-session-token")),
        task_event_service=service,
        task_event_poll_interval_seconds=0.01,
    )

    with (
        TestClient(app) as client,
        client.websocket_connect(
            "/api/workspaces/workspace-1/task-events",
            subprotocols=[
                "ai-qa-task-events",
                "auth.ZGVza3RvcC1zZXNzaW9uLXRva2Vu",
            ],
        ) as websocket,
    ):
        ready = websocket.receive_json()
        changed = websocket.receive_json()

    assert websocket.accepted_subprotocol == "ai-qa-task-events"
    assert ready["kind"] == "stream_ready"
    assert ready["sequence"] == 1
    assert ready["task"] is None
    assert changed == {
        "protocol_version": 1,
        "stream_id": ready["stream_id"],
        "sequence": 2,
        "kind": "task_updated",
        "task": {
            "task_type": "analysis",
            "task_id": "run-1",
            "workspace_id": "workspace-1",
            "status": "running",
            "progress": 35,
            "changed_at": "2026-08-16T06:00:00Z",
        },
    }
    assert "desktop-session-token" not in "/api/workspaces/workspace-1/task-events"


def test_task_event_websocket_rejects_wrong_subprotocol_token_without_leaking_it() -> None:
    app = create_app(
        settings=Settings(session_token=SecretStr("desktop-session-token")),
        task_event_service=ChangingTasks(),
        task_event_poll_interval_seconds=0.01,
    )

    with (
        TestClient(app) as client,
        pytest.raises(WebSocketDisconnect) as raised,
        client.websocket_connect(
            "/api/workspaces/workspace-1/task-events",
            subprotocols=[
                "ai-qa-task-events",
                "auth.d3Jvbmctc2Vzc2lvbi10b2tlbg",
            ],
        ),
    ):
        pass

    assert raised.value.code == 1008
    assert "wrong-session-token" not in raised.value.reason
    assert "desktop-session-token" not in raised.value.reason
