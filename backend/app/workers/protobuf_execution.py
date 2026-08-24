from __future__ import annotations

import logging
import multiprocessing
import os
import threading
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from multiprocessing.process import BaseProcess
from typing import Any, Protocol

from backend.app.application.credentials import CredentialStoreUnavailableError
from backend.app.domain.http_execution import HttpTemplateError, redact_secrets, resolve_template
from backend.app.domain.protobuf_execution import (
    ProtoExecutionInput,
    ProtoExecutionResult,
    ProtoExecutionTaskRequest,
    build_protobuf_url,
    evaluate_proto_assertions,
)
from backend.app.infrastructure.credentials import KeyringHttpSecretStore
from backend.app.infrastructure.database import create_database_engine
from backend.app.infrastructure.protobuf_codec import DynamicProtobufCodec, ProtoCodecError
from backend.app.infrastructure.protobuf_execution import SqlModelProtoExecutionRepository
from backend.app.infrastructure.protobuf_runner import ProtoRunnerError, StdlibProtobufRunner

logger = logging.getLogger(__name__)


class HttpSecretReader(Protocol):
    def get(self, environment_id: str, name: str) -> str | None: ...


def _now() -> datetime:
    return datetime.now(UTC)


def _redact_payload(value: Any, secrets: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        return redact_secrets(value, secrets)
    if isinstance(value, list):
        return [_redact_payload(item, secrets) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _redact_payload(item, secrets) for key, item in value.items()}
    return value


def _run_request(
    execution: ProtoExecutionInput,
    *,
    store_factory: Callable[[], HttpSecretReader] = KeyringHttpSecretStore,
    runner: StdlibProtobufRunner | None = None,
    codec: DynamicProtobufCodec | None = None,
) -> ProtoExecutionResult:
    store = store_factory()
    secrets: dict[str, str] = {}
    try:
        for name in execution.secret_names:
            value = store.get(execution.environment_id, name)
            if value is None:
                raise ProtoRunnerError("secret_missing")
            secrets[name] = value
    except CredentialStoreUnavailableError as exception:
        raise ProtoRunnerError("credential_store_unavailable") from exception
    try:
        path = resolve_template(
            execution.path_template, variables=execution.variables, secrets=secrets
        )
        headers = {
            name: resolve_template(value, variables=execution.variables, secrets=secrets)
            for name, value in execution.headers_template.items()
        }
        url = build_protobuf_url(execution.base_url, path)
    except (HttpTemplateError, ValueError) as exception:
        raise ProtoRunnerError("template_invalid") from exception
    active_codec = codec or DynamicProtobufCodec()
    request_payload = active_codec.encode(
        execution.descriptor_set,
        execution.request_message_type,
        execution.request_payload,
    )
    transport = (runner or StdlibProtobufRunner()).execute(
        url=url,
        headers=headers,
        payload=request_payload,
        timeout_seconds=execution.timeout_seconds,
        secrets=tuple(secrets.values()),
    )
    decoded = active_codec.decode(
        execution.descriptor_set,
        execution.response_message_type,
        transport.payload,
    )
    safe_payload = _redact_payload(decoded, tuple(secrets.values()))
    if not isinstance(safe_payload, dict):
        raise ProtoCodecError("PROTO_DECODE_FAILED", "Protobuf 解码结果无效。")
    assertion_results = evaluate_proto_assertions(execution.assertions, safe_payload)
    return ProtoExecutionResult(
        transport.status_code,
        transport.headers,
        safe_payload,
        len(transport.payload),
        transport.duration_ms,
        assertion_results,
    )


def _failure(reason: str) -> tuple[str, str]:
    failures = {
        "credential_store_unavailable": (
            "PROTO_CREDENTIAL_STORE_UNAVAILABLE",
            "操作系统凭据库当前不可用。",
        ),
        "secret_missing": ("PROTO_SECRET_MISSING", "请求引用的安全变量未配置。"),
        "template_invalid": ("PROTO_TEMPLATE_INVALID", "Protobuf 请求模板变量无法解析。"),
        "timeout": ("PROTO_REQUEST_TIMEOUT", "Protobuf 请求超时。"),
        "unavailable": ("PROTO_TARGET_UNAVAILABLE", "无法连接目标 Protobuf 服务。"),
        "response_too_large": ("PROTO_RESPONSE_TOO_LARGE", "Protobuf 响应超过 2 MiB 限制。"),
    }
    return failures.get(reason, ("PROTO_REQUEST_FAILED", "Protobuf 请求执行失败。"))


def run_protobuf_execution_job(database_url: str, request: ProtoExecutionTaskRequest) -> None:
    repository = SqlModelProtoExecutionRepository(create_database_engine(database_url))
    execution = repository.load_execution_input(request.run_id)
    if execution is None:
        repository.mark_failed(
            request.run_id,
            code="PROTO_INPUT_UNAVAILABLE",
            message="无法读取本次 Protobuf 执行输入。",
            now=_now(),
        )
        return
    repository.mark_running(request.run_id, pid=os.getpid(), now=_now())
    try:
        result = _run_request(execution)
    except ProtoRunnerError as exception:
        code, message = _failure(exception.reason)
        repository.mark_failed(request.run_id, code=code, message=message, now=_now())
        return
    except ProtoCodecError as exception:
        repository.mark_failed(
            request.run_id, code=exception.code, message=exception.message, now=_now()
        )
        return
    except Exception as exception:
        logger.error(
            "Protobuf execution worker failed",
            extra={"run_id": request.run_id, "error_type": type(exception).__name__},
        )
        repository.mark_error(
            request.run_id,
            code="PROTO_WORKER_ERROR",
            message="Protobuf 执行进程发生错误。",
            now=_now(),
        )
        return
    repository.mark_completed(request.run_id, result=result, now=_now())


class ProtoExecutionWorkerManager:
    def __init__(
        self,
        repository: SqlModelProtoExecutionRepository,
        *,
        database_url: str,
        timeout_seconds: int,
    ) -> None:
        self._repository = repository
        self._database_url = database_url
        self._timeout_seconds = timeout_seconds
        self._context = multiprocessing.get_context("spawn")
        self._processes: dict[str, BaseProcess] = {}
        self._lock = threading.Lock()

    def recover_interrupted(self) -> None:
        self._repository.recover_interrupted(now=_now())

    def launch(self, request: ProtoExecutionTaskRequest) -> None:
        process = self._context.Process(
            target=run_protobuf_execution_job,
            args=(self._database_url, request),
            daemon=True,
            name=f"protobuf-execution-{request.run_id[:8]}",
        )
        try:
            process.start()
        except Exception as exception:
            logger.error(
                "Protobuf execution worker start failed",
                extra={"run_id": request.run_id, "error_type": type(exception).__name__},
            )
            self._repository.mark_error(
                request.run_id,
                code="PROTO_WORKER_START_FAILED",
                message="无法启动 Protobuf 执行进程。",
                now=_now(),
            )
            raise
        with self._lock:
            self._processes[request.run_id] = process
        threading.Thread(
            target=self._supervise,
            args=(request.run_id, process),
            daemon=True,
            name=f"protobuf-execution-supervisor-{request.run_id[:8]}",
        ).start()

    def cancel(self, run_id: str) -> None:
        with self._lock:
            process = self._processes.pop(run_id, None)
        self._repository.mark_cancelled(run_id, now=_now())
        if process is not None and process.is_alive():
            process.terminate()
            process.join(timeout=5)

    def _supervise(self, run_id: str, process: BaseProcess) -> None:
        process.join(timeout=self._timeout_seconds)
        with self._lock:
            if self._processes.get(run_id) is not process:
                return
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
            self._repository.mark_timeout(run_id, now=_now())
        elif process.exitcode not in (0, None):
            self._repository.mark_error(
                run_id,
                code="PROTO_WORKER_CRASHED",
                message="Protobuf 执行进程意外退出。",
                now=_now(),
            )
        with self._lock:
            if self._processes.get(run_id) is process:
                self._processes.pop(run_id, None)
