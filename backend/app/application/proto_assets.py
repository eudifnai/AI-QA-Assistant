from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from backend.app.core.errors import AppError
from backend.app.domain.proto_asset import (
    ProtoAsset,
    ProtoAssetConflictError,
    ProtoCompileResult,
    ProtoDecodeResult,
    ProtoEncodeResult,
    ProtoSource,
)
from backend.app.domain.workspace import Workspace
from backend.app.infrastructure.proto_files import ProtoFileError
from backend.app.infrastructure.protobuf_codec import ProtoCodecError, ProtoCompilerError

MAX_CODEC_INPUT_BYTES = 1024 * 1024
MAX_CODEC_BINARY_BYTES = 2 * 1024 * 1024


class WorkspaceReader(Protocol):
    def get(self, workspace_id: str) -> Workspace | None: ...


class ProtoAssetRepository(Protocol):
    def list(self, workspace_id: str) -> list[ProtoAsset]: ...

    def get(self, workspace_id: str, asset_id: str) -> ProtoAsset | None: ...

    def find_by_hash(self, workspace_id: str, sha256: str) -> ProtoAsset | None: ...

    def find_by_path(self, workspace_id: str, path_key: str) -> ProtoAsset | None: ...

    def save(self, asset: ProtoAsset) -> ProtoAsset: ...


class ProtoFiles(Protocol):
    def inspect(self, workspace_path: str, source_path: str) -> ProtoSource: ...


class ProtoCompiler(Protocol):
    def compile(self, workspace_path: str, relative_path: str) -> ProtoCompileResult: ...


class ProtoCodec(Protocol):
    def encode(
        self, descriptor_set: bytes, message_type: str, payload: dict[str, Any]
    ) -> bytes: ...

    def decode(
        self, descriptor_set: bytes, message_type: str, payload: bytes
    ) -> dict[str, Any]: ...


class ProtoAssetUseCases(Protocol):
    def list_assets(self, workspace_id: str) -> list[ProtoAsset]: ...

    def get_asset(self, workspace_id: str, asset_id: str) -> ProtoAsset: ...

    def import_asset(self, workspace_id: str, source_path: str) -> ProtoAsset: ...

    def encode(
        self,
        workspace_id: str,
        asset_id: str,
        *,
        expected_sha256: str,
        message_type: str,
        payload: dict[str, Any],
    ) -> ProtoEncodeResult: ...

    def decode(
        self,
        workspace_id: str,
        asset_id: str,
        *,
        expected_sha256: str,
        message_type: str,
        data_base64: str,
    ) -> ProtoDecodeResult: ...


class ProtoAssetService:
    def __init__(
        self,
        workspaces: WorkspaceReader,
        repository: ProtoAssetRepository,
        files: ProtoFiles,
        compiler: ProtoCompiler,
        codec: ProtoCodec,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._workspaces = workspaces
        self._repository = repository
        self._files = files
        self._compiler = compiler
        self._codec = codec
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))

    def list_assets(self, workspace_id: str) -> list[ProtoAsset]:
        self._workspace(workspace_id)
        return self._repository.list(workspace_id)

    def get_asset(self, workspace_id: str, asset_id: str) -> ProtoAsset:
        self._workspace(workspace_id)
        asset = self._repository.get(workspace_id, asset_id)
        if asset is None:
            raise AppError(
                code="PROTO_ASSET_NOT_FOUND", message="未找到该 Proto 资产。", status_code=404
            )
        return asset

    def import_asset(self, workspace_id: str, source_path: str) -> ProtoAsset:
        workspace = self._workspace(workspace_id)
        try:
            source = self._files.inspect(workspace.path, source_path)
        except ProtoFileError as exception:
            raise self._file_error(exception.reason) from exception
        duplicate = self._repository.find_by_hash(workspace_id, source.sha256)
        if duplicate is not None:
            return duplicate
        try:
            compiled = self._compiler.compile(workspace.path, source.relative_path)
        except ProtoCompilerError as exception:
            raise self._compiler_error(exception) from exception
        try:
            confirmed_source = self._files.inspect(workspace.path, source_path)
        except ProtoFileError as exception:
            raise self._file_error(exception.reason) from exception
        if confirmed_source != source:
            raise AppError(
                code="PROTO_FILE_CHANGED",
                message="Proto 文件在编译期间发生变化。请重新导入。",
                status_code=409,
            )
        existing = self._repository.find_by_path(workspace_id, source.relative_path.casefold())
        now = self._clock()
        asset = ProtoAsset(
            existing.id if existing is not None else self._id_factory(),
            workspace_id,
            source.name,
            source.relative_path,
            source.sha256,
            source.size_bytes,
            compiled.descriptor_set,
            compiled.packages,
            compiled.messages,
            compiled.enums,
            compiled.services,
            existing.created_at if existing is not None else now,
            now,
        )
        try:
            return self._repository.save(asset)
        except ProtoAssetConflictError as exception:
            raise AppError(
                code="PROTO_ASSET_CONFLICT",
                message="该 Proto 文件或内容已导入。",
                status_code=409,
            ) from exception

    def encode(
        self,
        workspace_id: str,
        asset_id: str,
        *,
        expected_sha256: str,
        message_type: str,
        payload: dict[str, Any],
    ) -> ProtoEncodeResult:
        asset = self._codec_asset(workspace_id, asset_id, expected_sha256)
        try:
            json_bytes = json.dumps(
                payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")
            ).encode("utf-8")
        except (TypeError, ValueError) as exception:
            raise AppError(
                code="PROTO_JSON_INVALID", message="JSON 编码输入无效。", status_code=422
            ) from exception
        if len(json_bytes) > MAX_CODEC_INPUT_BYTES:
            raise AppError(
                code="PROTO_JSON_TOO_LARGE", message="JSON 编码输入超过 1 MiB。", status_code=413
            )
        try:
            encoded = self._codec.encode(asset.descriptor_set, message_type, payload)
        except ProtoCodecError as exception:
            raise AppError(
                code=exception.code, message=exception.message, status_code=422
            ) from exception
        if len(encoded) > MAX_CODEC_BINARY_BYTES:
            raise AppError(
                code="PROTO_BINARY_TOO_LARGE",
                message="Protobuf 编码结果超过 2 MiB。",
                status_code=413,
            )
        return ProtoEncodeResult(base64.b64encode(encoded).decode("ascii"), len(encoded))

    def decode(
        self,
        workspace_id: str,
        asset_id: str,
        *,
        expected_sha256: str,
        message_type: str,
        data_base64: str,
    ) -> ProtoDecodeResult:
        asset = self._codec_asset(workspace_id, asset_id, expected_sha256)
        if len(data_base64) > (MAX_CODEC_BINARY_BYTES * 4 // 3) + 8:
            raise AppError(
                code="PROTO_BINARY_TOO_LARGE",
                message="Protobuf 二进制超过 2 MiB。",
                status_code=413,
            )
        try:
            encoded = base64.b64decode(data_base64, validate=True)
        except (binascii.Error, ValueError) as exception:
            raise AppError(
                code="PROTO_BASE64_INVALID", message="Base64 数据格式无效。", status_code=422
            ) from exception
        if len(encoded) > MAX_CODEC_BINARY_BYTES:
            raise AppError(
                code="PROTO_BINARY_TOO_LARGE",
                message="Protobuf 二进制超过 2 MiB。",
                status_code=413,
            )
        try:
            decoded = self._codec.decode(asset.descriptor_set, message_type, encoded)
        except ProtoCodecError as exception:
            raise AppError(
                code=exception.code, message=exception.message, status_code=422
            ) from exception
        return ProtoDecodeResult(decoded, len(encoded))

    def _codec_asset(self, workspace_id: str, asset_id: str, expected_sha256: str) -> ProtoAsset:
        asset = self.get_asset(workspace_id, asset_id)
        if asset.sha256 != expected_sha256:
            raise AppError(
                code="PROTO_ASSET_VERSION_CONFLICT",
                message="Proto 资产版本已变化。请刷新后重试。",
                status_code=409,
            )
        return asset

    def _workspace(self, workspace_id: str) -> Workspace:
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise AppError(
                code="WORKSPACE_NOT_FOUND", message="未找到该工作空间。", status_code=404
            )
        return workspace

    @staticmethod
    def _file_error(reason: str) -> AppError:
        mapping = {
            "path_invalid": ("PROTO_PATH_INVALID", "请选择本机绝对 Proto 文件路径。", 400),
            "path_outside_workspace": (
                "PROTO_PATH_OUTSIDE_WORKSPACE",
                "Proto 文件必须位于当前工作空间内。",
                400,
            ),
            "file_not_found": ("PROTO_FILE_NOT_FOUND", "未找到该 Proto 文件。", 404),
            "unsupported_format": ("PROTO_FORMAT_UNSUPPORTED", "仅支持 .proto 文件。", 415),
            "file_too_large": ("PROTO_FILE_TOO_LARGE", "Proto 文件超过大小限制。", 413),
            "file_unavailable": ("PROTO_FILE_UNAVAILABLE", "无法读取该 Proto 文件。", 422),
        }
        code, message_text, status_code = mapping.get(
            reason, ("PROTO_FILE_INVALID", "Proto 文件不可用。", 422)
        )
        return AppError(code=code, message=message_text, status_code=status_code)

    @staticmethod
    def _compiler_error(exception: ProtoCompilerError) -> AppError:
        status_code = 504 if exception.code == "PROTO_COMPILE_TIMEOUT" else 422
        if exception.code in {"PROTO_DESCRIPTOR_TOO_LARGE", "PROTO_TOO_COMPLEX"}:
            status_code = 413
        return AppError(code=exception.code, message=exception.message, status_code=status_code)
