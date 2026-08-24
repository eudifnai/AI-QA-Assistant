from datetime import UTC, datetime

from google.protobuf import descriptor_pb2
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from backend.app.domain.proto_asset import ProtoAsset
from backend.app.infrastructure.proto_assets import SqlModelProtoAssetRepository
from backend.app.infrastructure.protobuf_codec import summarize_descriptor_set
from backend.app.infrastructure.workspaces import WorkspaceRecord

NOW = datetime(2026, 8, 16, 8, 0, tzinfo=UTC)


def descriptor_bytes() -> bytes:
    descriptor_set = descriptor_pb2.FileDescriptorSet()
    file_descriptor = descriptor_set.file.add()
    file_descriptor.name = "contracts/echo.proto"
    file_descriptor.package = "qa.echo"
    file_descriptor.syntax = "proto3"
    message = file_descriptor.message_type.add()
    message.name = "EchoRequest"
    field = message.field.add()
    field.name = "text"
    field.number = 1
    field.type = descriptor_pb2.FieldDescriptorProto.TYPE_STRING
    field.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    return bytes(descriptor_set.SerializeToString())


def test_repository_persists_and_updates_a_frozen_descriptor() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            WorkspaceRecord(
                id="workspace-1",
                name="支付",
                name_key="支付",
                path="C:/qa/pay",
                path_key="c:/qa/pay",
                created_at=NOW,
                last_opened_at=NOW,
            )
        )
        session.commit()
    descriptor = descriptor_bytes()
    summary = summarize_descriptor_set(descriptor, "contracts/echo.proto")
    asset = ProtoAsset(
        "asset-1",
        "workspace-1",
        "echo.proto",
        "contracts/echo.proto",
        "a" * 64,
        128,
        descriptor,
        summary.packages,
        summary.messages,
        summary.enums,
        summary.services,
        NOW,
        NOW,
    )
    repository = SqlModelProtoAssetRepository(engine)

    saved = repository.save(asset)
    loaded = repository.get("workspace-1", "asset-1")

    assert saved.messages[0].full_name == "qa.echo.EchoRequest"
    assert loaded == saved
    assert repository.find_by_hash("workspace-1", "a" * 64) == saved
    assert repository.find_by_path("workspace-1", "contracts/echo.proto") == saved
    assert repository.list("workspace-1") == [saved]
