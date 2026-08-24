from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from backend.app.core.errors import AppError
from backend.app.domain.http_execution import HttpEnvironment, HttpTemplateError, resolve_template
from backend.app.domain.proto_asset import ProtoAsset, ProtoMethod
from backend.app.domain.protobuf_execution import (
    ProtoExecution,
    ProtoExecutionStartInput,
    ProtoExecutionTaskRequest,
    build_protobuf_url,
)
from backend.app.domain.workspace import Workspace
from backend.app.infrastructure.protobuf_codec import ProtoCodecError

MAX_HEADERS = 50
MAX_HEADER_VALUE_LENGTH = 8192
MAX_REQUEST_JSON_BYTES = 1024 * 1024
MAX_ASSERTIONS = 20
HEADER_NAME_PATTERN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]{1,128}$")
RESERVED_HEADERS = frozenset({"content-length", "content-type", "accept", "host"})


class WorkspaceReader(Protocol):
    def get(self, workspace_id: str) -> Workspace | None: ...


class HttpEnvironmentReader(Protocol):
    def get_environment(self, workspace_id: str, environment_id: str) -> HttpEnvironment | None: ...


class ProtoAssetReader(Protocol):
    def get(self, workspace_id: str, asset_id: str) -> ProtoAsset | None: ...


class ProtoCodec(Protocol):
    def encode(
        self, descriptor_set: bytes, message_type: str, payload: dict[str, Any]
    ) -> bytes: ...


class ProtoExecutionRepository(Protocol):
    def create_run(
        self,
        *,
        run_id: str,
        workspace_id: str,
        environment: HttpEnvironment,
        asset: ProtoAsset,
        input: ProtoExecutionStartInput,
        request_message_type: str,
        response_message_type: str,
        created_at: datetime,
    ) -> ProtoExecution: ...

    def list_runs(self, workspace_id: str) -> list[ProtoExecution]: ...

    def get_run(self, workspace_id: str, run_id: str) -> ProtoExecution | None: ...


class ProtoExecutionWorker(Protocol):
    def recover_interrupted(self) -> None: ...

    def launch(self, request: ProtoExecutionTaskRequest) -> None: ...

    def cancel(self, run_id: str) -> None: ...


class ProtoExecutionUseCases(Protocol):
    def start(self, workspace_id: str, input: ProtoExecutionStartInput) -> ProtoExecution: ...

    def list_runs(self, workspace_id: str) -> list[ProtoExecution]: ...

    def get_run(self, workspace_id: str, run_id: str) -> ProtoExecution: ...

    def cancel(self, workspace_id: str, run_id: str) -> ProtoExecution: ...


class ProtoExecutionService:
    def __init__(
        self,
        workspaces: WorkspaceReader,
        environments: HttpEnvironmentReader,
        assets: ProtoAssetReader,
        repository: ProtoExecutionRepository,
        codec: ProtoCodec,
        worker: ProtoExecutionWorker,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._workspaces = workspaces
        self._environments = environments
        self._assets = assets
        self._repository = repository
        self._codec = codec
        self._worker = worker
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))
        self._recovered = False

    def start(self, workspace_id: str, input: ProtoExecutionStartInput) -> ProtoExecution:
        self._workspace(workspace_id)
        self._ensure_recovered()
        environment = self._environment(workspace_id, input.environment_id)
        asset = self._asset(workspace_id, input.asset_id)
        if asset.sha256 != input.expected_sha256:
            raise AppError(
                code="PROTO_ASSET_VERSION_CONFLICT",
                message="Proto 资产版本已变化。请刷新后重试。",
                status_code=409,
            )
        method = self._method(asset, input.service_name, input.method_name)
        normalized = self._validate_input(input, environment)
        try:
            self._codec.encode(asset.descriptor_set, method.input_type, normalized.request_payload)
        except ProtoCodecError as exception:
            raise AppError(
                code=exception.code, message=exception.message, status_code=422
            ) from exception
        run = self._repository.create_run(
            run_id=self._id_factory(),
            workspace_id=workspace_id,
            environment=environment,
            asset=asset,
            input=normalized,
            request_message_type=method.input_type,
            response_message_type=method.output_type,
            created_at=self._clock(),
        )
        self._worker.launch(ProtoExecutionTaskRequest(run.id))
        return run

    def list_runs(self, workspace_id: str) -> list[ProtoExecution]:
        self._workspace(workspace_id)
        self._ensure_recovered()
        return self._repository.list_runs(workspace_id)

    def get_run(self, workspace_id: str, run_id: str) -> ProtoExecution:
        self._workspace(workspace_id)
        self._ensure_recovered()
        run = self._repository.get_run(workspace_id, run_id)
        if run is None:
            raise AppError(
                code="PROTO_EXECUTION_NOT_FOUND",
                message="未找到该 Protobuf 执行任务。",
                status_code=404,
            )
        return run

    def cancel(self, workspace_id: str, run_id: str) -> ProtoExecution:
        run = self.get_run(workspace_id, run_id)
        if not run.can_cancel:
            raise AppError(
                code="PROTO_EXECUTION_FINISHED",
                message="该 Protobuf 执行任务已经结束。",
                status_code=409,
            )
        self._worker.cancel(run.id)
        return self._repository.get_run(workspace_id, run.id) or run

    def _workspace(self, workspace_id: str) -> Workspace:
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise AppError(
                code="WORKSPACE_NOT_FOUND", message="未找到该工作空间。", status_code=404
            )
        return workspace

    def _environment(self, workspace_id: str, environment_id: str) -> HttpEnvironment:
        environment = self._environments.get_environment(workspace_id, environment_id)
        if environment is None:
            raise AppError(
                code="HTTP_ENVIRONMENT_NOT_FOUND",
                message="未找到该 HTTP/Protobuf 环境。",
                status_code=404,
            )
        return environment

    def _asset(self, workspace_id: str, asset_id: str) -> ProtoAsset:
        asset = self._assets.get(workspace_id, asset_id)
        if asset is None:
            raise AppError(
                code="PROTO_ASSET_NOT_FOUND", message="未找到该 Proto 资产。", status_code=404
            )
        return asset

    @staticmethod
    def _method(asset: ProtoAsset, service_name: str, method_name: str) -> ProtoMethod:
        service = next((item for item in asset.services if item.full_name == service_name), None)
        method = (
            None
            if service is None
            else next((item for item in service.methods if item.name == method_name), None)
        )
        if method is None:
            raise AppError(
                code="PROTO_METHOD_NOT_FOUND",
                message="未找到指定的 Proto RPC 方法。",
                status_code=422,
            )
        if method.client_streaming or method.server_streaming:
            raise AppError(
                code="PROTO_STREAMING_UNSUPPORTED",
                message="当前切片仅支持非流式 Proto RPC 消息。",
                status_code=422,
            )
        return method

    @staticmethod
    def _validate_input(
        input: ProtoExecutionStartInput, environment: HttpEnvironment
    ) -> ProtoExecutionStartInput:
        try:
            encoded_json = json.dumps(
                input.request_payload,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
            assertions = tuple(item.validate() for item in input.assertions)
        except (TypeError, ValueError) as exception:
            raise ProtoExecutionService._invalid() from exception
        if (
            not 1 <= input.timeout_seconds <= 60
            or len(encoded_json) > MAX_REQUEST_JSON_BYTES
            or len(input.headers) > MAX_HEADERS
            or len(assertions) > MAX_ASSERTIONS
        ):
            raise ProtoExecutionService._invalid()
        if any(
            HEADER_NAME_PATTERN.fullmatch(name) is None
            or name.casefold() in RESERVED_HEADERS
            or len(value) > MAX_HEADER_VALUE_LENGTH
            or "\r" in value
            or "\n" in value
            for name, value in input.headers.items()
        ):
            raise ProtoExecutionService._invalid()
        dummy_variables = {name: "value" for name in environment.variables}
        dummy_secrets = {name: "secret" for name in environment.secret_names}
        try:
            path = resolve_template(input.path, variables=dummy_variables, secrets=dummy_secrets)
            build_protobuf_url(environment.base_url, path)
            for value in input.headers.values():
                resolve_template(value, variables=dummy_variables, secrets=dummy_secrets)
        except (HttpTemplateError, ValueError) as exception:
            raise ProtoExecutionService._invalid() from exception
        return ProtoExecutionStartInput(
            environment.id,
            asset_id=input.asset_id,
            expected_sha256=input.expected_sha256,
            service_name=input.service_name,
            method_name=input.method_name,
            path=input.path,
            headers=dict(input.headers),
            request_payload=dict(input.request_payload),
            timeout_seconds=input.timeout_seconds,
            assertions=assertions,
        )

    @staticmethod
    def _invalid() -> AppError:
        return AppError(
            code="PROTO_EXECUTION_REQUEST_INVALID",
            message="Protobuf 请求、断言或超时配置不正确。",
            status_code=422,
        )

    def _ensure_recovered(self) -> None:
        if self._recovered:
            return
        self._worker.recover_interrupted()
        self._recovered = True
