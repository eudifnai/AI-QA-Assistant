from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from backend.app.application.protobuf_execution import ProtoExecutionService
from backend.app.core.errors import AppError
from backend.app.domain.http_execution import HttpEnvironment
from backend.app.domain.proto_asset import ProtoAsset, ProtoMethod, ProtoService
from backend.app.domain.protobuf_execution import (
    ProtoExecutionStartInput,
    ProtoExecutionTaskRequest,
    ProtoFieldAssertion,
)
from backend.app.domain.workspace import Workspace

NOW = datetime(2026, 8, 16, tzinfo=UTC)
SHA = "a" * 64


class Workspaces:
    def get(self, workspace_id: str) -> Workspace | None:
        if workspace_id != "workspace-1":
            return None
        return Workspace("workspace-1", "Demo", "E:/workspace", NOW, NOW)


class Environments:
    def get_environment(self, workspace_id: str, environment_id: str) -> HttpEnvironment | None:
        if (workspace_id, environment_id) != ("workspace-1", "environment-1"):
            return None
        return HttpEnvironment(
            "environment-1",
            "workspace-1",
            "Local",
            "https://api.example.com/v1",
            {"TENANT": "qa"},
            ("API_TOKEN",),
            NOW,
            NOW,
        )


class Assets:
    def __init__(self, *, streaming: bool = False) -> None:
        self.asset = ProtoAsset(
            "asset-1",
            "workspace-1",
            "echo.proto",
            "echo.proto",
            SHA,
            100,
            b"descriptor",
            ("demo",),
            (),
            (),
            (
                ProtoService(
                    "EchoService",
                    "demo.EchoService",
                    (
                        ProtoMethod(
                            "Echo",
                            "demo.EchoRequest",
                            "demo.EchoResponse",
                            streaming,
                            False,
                        ),
                    ),
                ),
            ),
            NOW,
            NOW,
        )

    def get(self, workspace_id: str, asset_id: str) -> ProtoAsset | None:
        return self.asset if (workspace_id, asset_id) == ("workspace-1", "asset-1") else None


class Codec:
    def __init__(self) -> None:
        self.calls: list[tuple[bytes, str, dict[str, Any]]] = []

    def encode(self, descriptor_set: bytes, message_type: str, payload: dict[str, Any]) -> bytes:
        self.calls.append((descriptor_set, message_type, payload))
        return b"encoded"


class Repository:
    def __init__(self) -> None:
        self.create_kwargs: dict[str, object] | None = None

    def create_run(self, **kwargs: object) -> object:
        self.create_kwargs = kwargs
        return type("Run", (), {"id": "run-1"})()

    def list_runs(self, workspace_id: str) -> list[object]:
        return []

    def get_run(self, workspace_id: str, run_id: str) -> object | None:
        return None


class Worker:
    def __init__(self) -> None:
        self.launched: list[ProtoExecutionTaskRequest] = []
        self.recover_count = 0

    def recover_interrupted(self) -> None:
        self.recover_count += 1

    def launch(self, request: ProtoExecutionTaskRequest) -> None:
        self.launched.append(request)

    def cancel(self, run_id: str) -> None:
        return


def input_for(**overrides: object) -> ProtoExecutionStartInput:
    values: dict[str, object] = {
        "environment_id": "environment-1",
        "asset_id": "asset-1",
        "expected_sha256": SHA,
        "service_name": "demo.EchoService",
        "method_name": "Echo",
        "path": "/echo/{{TENANT}}",
        "headers": {"Authorization": "Bearer {{secret.API_TOKEN}}"},
        "request_payload": {"id": 7},
        "timeout_seconds": 10,
        "assertions": (ProtoFieldAssertion("$.ok", "true"),),
    }
    values.update(overrides)
    return ProtoExecutionStartInput(**values)  # type: ignore[arg-type]


def service_for(
    *, assets: Assets | None = None
) -> tuple[ProtoExecutionService, Repository, Worker, Codec]:
    repository = Repository()
    worker = Worker()
    codec = Codec()
    return (
        ProtoExecutionService(
            Workspaces(),
            Environments(),
            assets or Assets(),
            repository,  # type: ignore[arg-type]
            codec,
            worker,
            clock=lambda: NOW,
            id_factory=lambda: "run-1",
        ),
        repository,
        worker,
        codec,
    )


def test_start_freezes_asset_method_environment_and_launches_worker() -> None:
    service, repository, worker, codec = service_for()

    run = service.start("workspace-1", input_for())

    assert run.id == "run-1"
    assert repository.create_kwargs is not None
    assert repository.create_kwargs["request_message_type"] == "demo.EchoRequest"
    assert repository.create_kwargs["response_message_type"] == "demo.EchoResponse"
    assert codec.calls == [(b"descriptor", "demo.EchoRequest", {"id": 7})]
    assert worker.launched == [ProtoExecutionTaskRequest("run-1")]
    assert worker.recover_count == 1


def test_start_rejects_stale_asset_snapshot_without_launching() -> None:
    service, repository, worker, _ = service_for()

    with pytest.raises(AppError) as raised:
        service.start("workspace-1", input_for(expected_sha256="b" * 64))

    assert raised.value.code == "PROTO_ASSET_VERSION_CONFLICT"
    assert repository.create_kwargs is None
    assert worker.launched == []


def test_start_rejects_streaming_rpc() -> None:
    service, repository, worker, _ = service_for(assets=Assets(streaming=True))

    with pytest.raises(AppError) as raised:
        service.start("workspace-1", input_for())

    assert raised.value.code == "PROTO_STREAMING_UNSUPPORTED"
    assert repository.create_kwargs is None
    assert worker.launched == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"path": "https://evil.example/echo"},
        {"headers": {"Bad Header": "value"}},
        {"timeout_seconds": 0},
        {"assertions": tuple(ProtoFieldAssertion("$.ok", "true") for _ in range(21))},
    ],
)
def test_start_rejects_invalid_requests(overrides: dict[str, object]) -> None:
    service, repository, worker, _ = service_for()

    with pytest.raises(AppError) as raised:
        service.start("workspace-1", input_for(**overrides))

    assert raised.value.code == "PROTO_EXECUTION_REQUEST_INVALID"
    assert repository.create_kwargs is None
    assert worker.launched == []
