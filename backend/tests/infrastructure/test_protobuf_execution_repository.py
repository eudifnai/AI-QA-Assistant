from datetime import UTC, datetime

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from backend.app.domain.http_execution import HttpEnvironment
from backend.app.domain.proto_asset import ProtoAsset
from backend.app.domain.protobuf_execution import (
    ProtoExecutionResult,
    ProtoExecutionStartInput,
    ProtoFieldAssertion,
    ProtoFieldAssertionResult,
)
from backend.app.infrastructure.http_execution import HttpEnvironmentRecord
from backend.app.infrastructure.proto_assets import ProtoAssetRecord
from backend.app.infrastructure.protobuf_execution import SqlModelProtoExecutionRepository
from backend.app.infrastructure.workspaces import WorkspaceRecord

NOW = datetime(2026, 8, 16, 8, 0, tzinfo=UTC)


def setup_repository() -> tuple[SqlModelProtoExecutionRepository, HttpEnvironment, ProtoAsset]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            WorkspaceRecord(
                id="workspace-1",
                name="Demo",
                name_key="demo",
                path="C:/qa",
                path_key="c:/qa",
                created_at=NOW,
                last_opened_at=NOW,
            )
        )
        session.add(
            HttpEnvironmentRecord(
                id="environment-1",
                workspace_id="workspace-1",
                name="Local",
                name_key="local",
                base_url="https://api.example.com",
                variables_json='{"TENANT":"qa"}',
                secret_names_json='["TOKEN"]',
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.add(
            ProtoAssetRecord(
                id="asset-1",
                workspace_id="workspace-1",
                name="echo.proto",
                relative_path="echo.proto",
                path_key="echo.proto",
                sha256="a" * 64,
                size_bytes=20,
                descriptor_set=b"descriptor",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.commit()
    environment = HttpEnvironment(
        "environment-1",
        "workspace-1",
        "Local",
        "https://api.example.com",
        {"TENANT": "qa"},
        ("TOKEN",),
        NOW,
        NOW,
    )
    asset = ProtoAsset(
        "asset-1",
        "workspace-1",
        "echo.proto",
        "echo.proto",
        "a" * 64,
        20,
        b"descriptor",
        (),
        (),
        (),
        (),
        NOW,
        NOW,
    )
    return SqlModelProtoExecutionRepository(engine), environment, asset


def test_repository_freezes_input_and_persists_assertion_result() -> None:
    repository, environment, asset = setup_repository()
    assertion = ProtoFieldAssertion("$.ok", "true")
    run = repository.create_run(
        run_id="run-1",
        workspace_id="workspace-1",
        environment=environment,
        asset=asset,
        input=ProtoExecutionStartInput(
            "environment-1",
            "asset-1",
            "a" * 64,
            "demo.Echo",
            "Call",
            "/echo/{{TENANT}}",
            {"Authorization": "Bearer {{secret.TOKEN}}"},
            {"id": 7},
            10,
            (assertion,),
        ),
        request_message_type="demo.Request",
        response_message_type="demo.Response",
        created_at=NOW,
    )

    execution_input = repository.load_execution_input("run-1")
    assert run.status == "queued"
    assert execution_input is not None
    assert execution_input.descriptor_set == b"descriptor"
    assert execution_input.secret_names == ("TOKEN",)
    assert execution_input.request_payload == {"id": 7}

    repository.mark_running("run-1", pid=123, now=NOW)
    result = ProtoExecutionResult(
        200,
        {"Content-Type": "application/x-protobuf"},
        {"ok": True},
        2,
        14,
        (ProtoFieldAssertionResult("$.ok", "true", "true", True, "字段值符合预期。"),),
    )
    repository.mark_completed("run-1", result=result, now=NOW)
    loaded = repository.get_run("workspace-1", "run-1")

    assert loaded is not None
    assert loaded.status == "passed"
    assert loaded.response_payload == {"ok": True}
    assert loaded.assertion_results[0].passed is True
    assert [event.code for event in loaded.events] == [
        "PROTO_EXECUTION_QUEUED",
        "PROTO_WORKER_STARTED",
        "PROTO_EXECUTION_PASSED",
    ]


def test_repository_terminal_state_cannot_be_overwritten() -> None:
    repository, environment, asset = setup_repository()
    repository.create_run(
        run_id="run-1",
        workspace_id="workspace-1",
        environment=environment,
        asset=asset,
        input=ProtoExecutionStartInput(
            "environment-1", "asset-1", "a" * 64, "demo.Echo", "Call", "/echo", {}, {}, 10
        ),
        request_message_type="demo.Request",
        response_message_type="demo.Response",
        created_at=NOW,
    )

    repository.mark_cancelled("run-1", now=NOW)
    repository.mark_error("run-1", code="LATE", message="late", now=NOW)

    loaded = repository.get_run("workspace-1", "run-1")
    assert loaded is not None
    assert loaded.status == "cancelled"
    assert loaded.error_code == "PROTO_EXECUTION_CANCELLED"


def test_repository_recovers_a_queued_run_after_restart() -> None:
    repository, environment, asset = setup_repository()
    repository.create_run(
        run_id="run-1",
        workspace_id="workspace-1",
        environment=environment,
        asset=asset,
        input=ProtoExecutionStartInput(
            "environment-1", "asset-1", "a" * 64, "demo.Echo", "Call", "/echo", {}, {}, 10
        ),
        request_message_type="demo.Request",
        response_message_type="demo.Response",
        created_at=NOW,
    )

    repository.recover_interrupted(now=NOW)

    loaded = repository.get_run("workspace-1", "run-1")
    assert loaded is not None
    assert loaded.status == "error"
    assert loaded.error_code == "PROTO_EXECUTION_INTERRUPTED"
