import os
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from google.protobuf import descriptor_pb2
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel

from backend.app.domain.http_execution import HttpEnvironmentInput
from backend.app.domain.proto_asset import ProtoAsset
from backend.app.domain.protobuf_execution import (
    ProtoExecutionStartInput,
    ProtoExecutionTaskRequest,
    ProtoFieldAssertion,
)
from backend.app.infrastructure.database import create_database_engine
from backend.app.infrastructure.http_execution import SqlModelHttpExecutionRepository
from backend.app.infrastructure.proto_assets import SqlModelProtoAssetRepository
from backend.app.infrastructure.protobuf_codec import DynamicProtobufCodec, summarize_descriptor_set
from backend.app.infrastructure.protobuf_execution import (
    ProtoExecutionRecord,
    SqlModelProtoExecutionRepository,
)
from backend.app.infrastructure.workspaces import WorkspaceRecord
from backend.app.workers.protobuf_execution import ProtoExecutionWorkerManager

NOW = datetime(2026, 8, 16, 10, 0, tzinfo=UTC)


def descriptor_bytes() -> bytes:
    descriptor_set = descriptor_pb2.FileDescriptorSet()
    file = descriptor_set.file.add()
    file.name = "echo.proto"
    file.package = "demo"
    file.syntax = "proto3"
    request = file.message_type.add()
    request.name = "Request"
    request_field = request.field.add()
    request_field.name = "id"
    request_field.number = 1
    request_field.type = descriptor_pb2.FieldDescriptorProto.TYPE_INT32
    response = file.message_type.add()
    response.name = "Response"
    response_field = response.field.add()
    response_field.name = "ok"
    response_field.number = 1
    response_field.type = descriptor_pb2.FieldDescriptorProto.TYPE_BOOL
    service = file.service.add()
    service.name = "Echo"
    method = service.method.add()
    method.name = "Call"
    method.input_type = ".demo.Request"
    method.output_type = ".demo.Response"
    return bytes(descriptor_set.SerializeToString())


class Handler(BaseHTTPRequestHandler):
    descriptor = descriptor_bytes()

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        request = DynamicProtobufCodec().decode(
            self.descriptor, "demo.Request", self.rfile.read(length)
        )
        assert request == {"id": 7}
        response = DynamicProtobufCodec().encode(self.descriptor, "demo.Response", {"ok": True})
        self.send_response(200)
        self.send_header("Content-Type", "application/x-protobuf")
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, _format: str, *args: object) -> None:
        return


def seed_repository(
    tmp_path: Path, base_url: str
) -> tuple[SqlModelProtoExecutionRepository, str, Engine]:
    database_path = tmp_path / "protobuf-process.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_database_engine(database_url)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            WorkspaceRecord(
                id="workspace-1",
                name="Demo",
                name_key="demo",
                path=str(tmp_path),
                path_key=str(tmp_path).casefold(),
                created_at=NOW,
                last_opened_at=NOW,
            )
        )
        session.commit()
    environment = SqlModelHttpExecutionRepository(engine).create_environment(
        "environment-1", "workspace-1", HttpEnvironmentInput("Local", base_url, {}), now=NOW
    )
    descriptor = descriptor_bytes()
    summary = summarize_descriptor_set(descriptor, "echo.proto")
    asset = SqlModelProtoAssetRepository(engine).save(
        ProtoAsset(
            "asset-1",
            "workspace-1",
            "echo.proto",
            "echo.proto",
            "a" * 64,
            100,
            descriptor,
            summary.packages,
            summary.messages,
            summary.enums,
            summary.services,
            NOW,
            NOW,
        )
    )
    repository = SqlModelProtoExecutionRepository(engine)
    repository.create_run(
        run_id="run-process",
        workspace_id="workspace-1",
        environment=environment,
        asset=asset,
        input=ProtoExecutionStartInput(
            environment.id,
            asset.id,
            asset.sha256,
            "demo.Echo",
            "Call",
            "/echo",
            {},
            {"id": 7},
            10,
            (ProtoFieldAssertion("$.ok", "true"),),
        ),
        request_message_type="demo.Request",
        response_message_type="demo.Response",
        created_at=NOW,
    )
    return repository, database_url, engine


def test_independent_protobuf_worker_persists_decoded_response(tmp_path: Path) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        repository, database_url, engine = seed_repository(
            tmp_path, f"http://127.0.0.1:{server.server_port}"
        )
        manager = ProtoExecutionWorkerManager(
            repository, database_url=database_url, timeout_seconds=15
        )
        manager.launch(ProtoExecutionTaskRequest("run-process"))
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            run = repository.get_any("run-process")
            if run is not None and not run.can_cancel:
                break
            time.sleep(0.05)

        result = repository.get_run("workspace-1", "run-process")
        assert result is not None
        assert result.status == "passed"
        assert result.response_payload == {"ok": True}
        assert result.assertion_results[0].passed is True
        with Session(engine) as session:
            record = session.get(ProtoExecutionRecord, "run-process")
            assert record is not None
            assert record.pid not in (None, os.getpid())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
