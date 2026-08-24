from pathlib import Path

from alembic import command

from backend.app.application.proto_assets import ProtoAssetService
from backend.app.application.workspaces import WorkspaceService
from backend.app.infrastructure.database import create_database_engine
from backend.app.infrastructure.proto_assets import SqlModelProtoAssetRepository
from backend.app.infrastructure.proto_files import LocalProtoFiles
from backend.app.infrastructure.protobuf_codec import DynamicProtobufCodec, GrpcToolsProtoCompiler
from backend.app.infrastructure.workspace_storage import LocalWorkspaceStorage
from backend.app.infrastructure.workspaces import SqlModelWorkspaceRepository
from tests.integration.test_migrations import migration_config


def test_proto_asset_and_descriptor_survive_service_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "proto-assets.db"
    command.upgrade(migration_config(database_path), "head")
    engine = create_database_engine(f"sqlite:///{database_path.as_posix()}")
    workspace_path = tmp_path / "workspace"
    workspace = WorkspaceService(
        SqlModelWorkspaceRepository(engine),
        LocalWorkspaceStorage(minimum_free_bytes=1),
    ).create(name="Proto 项目", path=str(workspace_path))
    proto_path = workspace_path / "contracts" / "echo.proto"
    proto_path.parent.mkdir()
    proto_path.write_text(
        'syntax = "proto3"; package qa.echo; message Echo { string text = 1; }',
        encoding="utf-8",
    )

    service = ProtoAssetService(
        SqlModelWorkspaceRepository(engine),
        SqlModelProtoAssetRepository(engine),
        LocalProtoFiles(max_bytes=1024 * 1024),
        GrpcToolsProtoCompiler(),
        DynamicProtobufCodec(),
    )
    imported = service.import_asset(workspace.id, str(proto_path))

    restarted = ProtoAssetService(
        SqlModelWorkspaceRepository(engine),
        SqlModelProtoAssetRepository(engine),
        LocalProtoFiles(max_bytes=1024 * 1024),
        GrpcToolsProtoCompiler(),
        DynamicProtobufCodec(),
    )
    recovered = restarted.get_asset(workspace.id, imported.id)
    encoded = restarted.encode(
        workspace.id,
        imported.id,
        expected_sha256=imported.sha256,
        message_type="qa.echo.Echo",
        payload={"text": "hello"},
    )

    assert recovered == imported
    assert restarted.decode(
        workspace.id,
        imported.id,
        expected_sha256=imported.sha256,
        message_type="qa.echo.Echo",
        data_base64=encoded.data_base64,
    ).payload == {"text": "hello"}
