from datetime import UTC, datetime

import pytest

from backend.app.application.proto_assets import ProtoAssetService
from backend.app.core.errors import AppError
from backend.app.domain.proto_asset import (
    ProtoAsset,
    ProtoCompileResult,
    ProtoField,
    ProtoMessage,
    ProtoSource,
)
from backend.app.domain.workspace import Workspace

NOW = datetime(2026, 8, 16, 8, 0, tzinfo=UTC)
WORKSPACE = Workspace("workspace-1", "支付", "C:/qa/pay", NOW, NOW)
SOURCE = ProtoSource("echo.proto", "contracts/echo.proto", "a" * 64, 128)
MESSAGE = ProtoMessage(
    name="EchoRequest",
    full_name="qa.echo.EchoRequest",
    fields=(ProtoField("text", 1, "TYPE_STRING", "LABEL_OPTIONAL", None),),
)
COMPILED = ProtoCompileResult(
    descriptor_set=b"descriptor",
    packages=("qa.echo",),
    messages=(MESSAGE,),
    enums=(),
    services=(),
)


class Workspaces:
    def get(self, workspace_id: str) -> Workspace | None:
        return WORKSPACE if workspace_id == WORKSPACE.id else None


class Files:
    def inspect(self, workspace_path: str, source_path: str) -> ProtoSource:
        assert workspace_path == WORKSPACE.path
        assert source_path.endswith("echo.proto")
        return SOURCE


class ChangingFiles(Files):
    def __init__(self) -> None:
        self.calls = 0

    def inspect(self, workspace_path: str, source_path: str) -> ProtoSource:
        self.calls += 1
        if self.calls == 1:
            return SOURCE
        return ProtoSource(SOURCE.name, SOURCE.relative_path, "b" * 64, SOURCE.size_bytes)


class Compiler:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def compile(self, workspace_path: str, relative_path: str) -> ProtoCompileResult:
        self.calls.append((workspace_path, relative_path))
        return COMPILED


class Codec:
    def __init__(self) -> None:
        self.encoded = b"\x0a\x02hi"

    def encode(self, descriptor_set: bytes, message_type: str, payload: dict[str, object]) -> bytes:
        assert descriptor_set == COMPILED.descriptor_set
        assert message_type == MESSAGE.full_name
        assert payload == {"text": "hi"}
        return self.encoded

    def decode(self, descriptor_set: bytes, message_type: str, payload: bytes) -> dict[str, object]:
        assert descriptor_set == COMPILED.descriptor_set
        assert message_type == MESSAGE.full_name
        assert payload == self.encoded
        return {"text": "hi"}


class Repository:
    def __init__(self) -> None:
        self.asset: ProtoAsset | None = None
        self.saved: ProtoAsset | None = None

    def list(self, workspace_id: str) -> list[ProtoAsset]:
        return (
            [self.asset]
            if self.asset is not None and self.asset.workspace_id == workspace_id
            else []
        )

    def get(self, workspace_id: str, asset_id: str) -> ProtoAsset | None:
        if (
            self.asset is not None
            and self.asset.workspace_id == workspace_id
            and self.asset.id == asset_id
        ):
            return self.asset
        return None

    def find_by_hash(self, workspace_id: str, sha256: str) -> ProtoAsset | None:
        if (
            self.asset is not None
            and self.asset.workspace_id == workspace_id
            and self.asset.sha256 == sha256
        ):
            return self.asset
        return None

    def find_by_path(self, workspace_id: str, path_key: str) -> ProtoAsset | None:
        if (
            self.asset is not None
            and self.asset.workspace_id == workspace_id
            and self.asset.relative_path.casefold() == path_key
        ):
            return self.asset
        return None

    def save(self, asset: ProtoAsset) -> ProtoAsset:
        self.saved = asset
        self.asset = asset
        return asset


def make_service(
    repository: Repository | None = None,
    compiler: Compiler | None = None,
    files: Files | None = None,
) -> ProtoAssetService:
    return ProtoAssetService(
        Workspaces(),
        repository or Repository(),
        files or Files(),
        compiler or Compiler(),
        Codec(),
        clock=lambda: NOW,
        id_factory=lambda: "asset-1",
    )


def test_import_compiles_and_freezes_a_proto_asset() -> None:
    repository = Repository()
    compiler = Compiler()

    asset = make_service(repository, compiler).import_asset(
        WORKSPACE.id, "C:/qa/pay/contracts/echo.proto"
    )

    assert asset.id == "asset-1"
    assert asset.sha256 == SOURCE.sha256
    assert asset.messages == (MESSAGE,)
    assert asset.descriptor_set == b"descriptor"
    assert compiler.calls == [(WORKSPACE.path, SOURCE.relative_path)]
    assert repository.saved == asset


def test_duplicate_content_is_idempotent_without_recompiling() -> None:
    repository = Repository()
    compiler = Compiler()
    repository.asset = ProtoAsset(
        "asset-existing",
        WORKSPACE.id,
        SOURCE.name,
        SOURCE.relative_path,
        SOURCE.sha256,
        SOURCE.size_bytes,
        COMPILED.descriptor_set,
        COMPILED.packages,
        COMPILED.messages,
        COMPILED.enums,
        COMPILED.services,
        NOW,
        NOW,
    )

    imported = make_service(repository, compiler).import_asset(
        WORKSPACE.id, "C:/qa/pay/contracts/echo.proto"
    )

    assert imported.id == "asset-existing"
    assert compiler.calls == []
    assert repository.saved is None


def test_import_rejects_a_file_changed_during_compilation() -> None:
    repository = Repository()

    with pytest.raises(AppError) as raised:
        make_service(repository, files=ChangingFiles()).import_asset(
            WORKSPACE.id, "C:/qa/pay/contracts/echo.proto"
        )

    assert raised.value.code == "PROTO_FILE_CHANGED"
    assert repository.saved is None


def test_codec_rejects_a_stale_descriptor_snapshot() -> None:
    repository = Repository()
    repository.asset = ProtoAsset(
        "asset-1",
        WORKSPACE.id,
        SOURCE.name,
        SOURCE.relative_path,
        SOURCE.sha256,
        SOURCE.size_bytes,
        COMPILED.descriptor_set,
        COMPILED.packages,
        COMPILED.messages,
        COMPILED.enums,
        COMPILED.services,
        NOW,
        NOW,
    )

    with pytest.raises(AppError) as raised:
        make_service(repository).encode(
            WORKSPACE.id,
            "asset-1",
            expected_sha256="b" * 64,
            message_type=MESSAGE.full_name,
            payload={"text": "hi"},
        )

    assert raised.value.code == "PROTO_ASSET_VERSION_CONFLICT"


def test_codec_encodes_and_decodes_the_frozen_descriptor() -> None:
    repository = Repository()
    repository.asset = ProtoAsset(
        "asset-1",
        WORKSPACE.id,
        SOURCE.name,
        SOURCE.relative_path,
        SOURCE.sha256,
        SOURCE.size_bytes,
        COMPILED.descriptor_set,
        COMPILED.packages,
        COMPILED.messages,
        COMPILED.enums,
        COMPILED.services,
        NOW,
        NOW,
    )
    service = make_service(repository)

    encoded = service.encode(
        WORKSPACE.id,
        "asset-1",
        expected_sha256=SOURCE.sha256,
        message_type=MESSAGE.full_name,
        payload={"text": "hi"},
    )
    decoded = service.decode(
        WORKSPACE.id,
        "asset-1",
        expected_sha256=SOURCE.sha256,
        message_type=MESSAGE.full_name,
        data_base64=encoded.data_base64,
    )

    assert encoded.size_bytes == 4
    assert decoded.payload == {"text": "hi"}


def test_codec_rejects_invalid_base64_before_decoding() -> None:
    repository = Repository()
    repository.asset = ProtoAsset(
        "asset-1",
        WORKSPACE.id,
        SOURCE.name,
        SOURCE.relative_path,
        SOURCE.sha256,
        SOURCE.size_bytes,
        COMPILED.descriptor_set,
        COMPILED.packages,
        COMPILED.messages,
        COMPILED.enums,
        COMPILED.services,
        NOW,
        NOW,
    )

    with pytest.raises(AppError) as raised:
        make_service(repository).decode(
            WORKSPACE.id,
            "asset-1",
            expected_sha256=SOURCE.sha256,
            message_type=MESSAGE.full_name,
            data_base64="***not-base64***",
        )

    assert raised.value.code == "PROTO_BASE64_INVALID"
