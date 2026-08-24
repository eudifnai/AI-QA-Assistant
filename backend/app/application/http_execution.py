from __future__ import annotations

import re
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from typing import Protocol
from uuid import uuid4

from backend.app.application.credentials import CredentialStoreUnavailableError
from backend.app.core.errors import AppError
from backend.app.domain.http_execution import (
    HTTP_METHODS,
    HttpAssertion,
    HttpEnvironment,
    HttpEnvironmentInput,
    HttpExecution,
    HttpExecutionStartInput,
    HttpExecutionTaskRequest,
    HttpTemplateError,
    resolve_template,
    validate_and_normalize_base_url,
    validate_variable_name,
)
from backend.app.domain.workspace import Workspace

MAX_ENVIRONMENT_NAME_LENGTH = 120
MAX_VARIABLES = 100
MAX_VARIABLE_VALUE_LENGTH = 8192
MAX_SECRET_LENGTH = 8192
MAX_REQUEST_PATH_LENGTH = 4096
MAX_REQUEST_HEADERS = 50
MAX_HEADER_VALUE_LENGTH = 8192
MAX_REQUEST_BODY_BYTES = 1024 * 1024
MAX_ASSERTIONS = 20
RETRYABLE_HTTP_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
HEADER_NAME_PATTERN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]{1,128}$")


class WorkspaceReader(Protocol):
    def get(self, workspace_id: str) -> Workspace | None: ...


class HttpExecutionRepository(Protocol):
    def list_environments(self, workspace_id: str) -> list[HttpEnvironment]: ...

    def get_environment(self, workspace_id: str, environment_id: str) -> HttpEnvironment | None: ...

    def find_environment_by_name(
        self, workspace_id: str, name_key: str
    ) -> HttpEnvironment | None: ...

    def create_environment(
        self,
        environment_id: str,
        workspace_id: str,
        input: HttpEnvironmentInput,
        *,
        now: datetime,
    ) -> HttpEnvironment: ...

    def update_environment(
        self,
        environment_id: str,
        input: HttpEnvironmentInput,
        *,
        now: datetime,
    ) -> HttpEnvironment: ...

    def delete_environment(self, environment_id: str) -> None: ...

    def add_secret_name(
        self, environment_id: str, name: str, *, now: datetime
    ) -> HttpEnvironment: ...

    def remove_secret_name(
        self, environment_id: str, name: str, *, now: datetime
    ) -> HttpEnvironment: ...

    def create_run(
        self,
        *,
        run_id: str,
        workspace_id: str,
        environment: HttpEnvironment,
        input: HttpExecutionStartInput,
        created_at: datetime,
    ) -> HttpExecution: ...

    def list_runs(self, workspace_id: str) -> list[HttpExecution]: ...

    def get_run(self, workspace_id: str, run_id: str) -> HttpExecution | None: ...

    def recreate_run(
        self, source_run_id: str, new_run_id: str, *, created_at: datetime
    ) -> HttpExecution: ...


class HttpSecretStore(Protocol):
    def get(self, environment_id: str, name: str) -> str | None: ...

    def set(self, environment_id: str, name: str, secret: str) -> None: ...

    def delete(self, environment_id: str, name: str) -> None: ...


class HttpWorker(Protocol):
    def launch(self, request: HttpExecutionTaskRequest) -> None: ...

    def cancel(self, run_id: str) -> None: ...

    def recover_interrupted(self) -> None: ...


class HttpExecutionUseCases(Protocol):
    def list_environments(self, workspace_id: str) -> list[HttpEnvironment]: ...

    def create_environment(
        self, workspace_id: str, input: HttpEnvironmentInput
    ) -> HttpEnvironment: ...

    def update_environment(
        self, workspace_id: str, environment_id: str, input: HttpEnvironmentInput
    ) -> HttpEnvironment: ...

    def delete_environment(self, workspace_id: str, environment_id: str) -> None: ...

    def set_secret(
        self, workspace_id: str, environment_id: str, name: str, secret: str
    ) -> HttpEnvironment: ...

    def delete_secret(
        self, workspace_id: str, environment_id: str, name: str
    ) -> HttpEnvironment: ...

    def start(self, workspace_id: str, input: HttpExecutionStartInput) -> HttpExecution: ...

    def list_runs(self, workspace_id: str) -> list[HttpExecution]: ...

    def get_run(self, workspace_id: str, run_id: str) -> HttpExecution: ...

    def cancel(self, workspace_id: str, run_id: str) -> HttpExecution: ...

    def rerun(self, workspace_id: str, run_id: str) -> HttpExecution: ...


class HttpExecutionService:
    def __init__(
        self,
        workspaces: WorkspaceReader,
        repository: HttpExecutionRepository,
        secret_store: HttpSecretStore,
        worker: HttpWorker,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._workspaces = workspaces
        self._repository = repository
        self._secret_store = secret_store
        self._worker = worker
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))
        self._recovered = False
        self._recovery_lock = threading.Lock()

    def list_environments(self, workspace_id: str) -> list[HttpEnvironment]:
        self._workspace(workspace_id)
        return self._repository.list_environments(workspace_id)

    def create_environment(self, workspace_id: str, input: HttpEnvironmentInput) -> HttpEnvironment:
        self._workspace(workspace_id)
        normalized = self._validate_environment_input(input)
        if self._repository.find_environment_by_name(workspace_id, normalized.name.casefold()):
            raise AppError(
                code="HTTP_ENVIRONMENT_NAME_CONFLICT",
                message="该 HTTP 环境名称已存在。",
                status_code=409,
            )
        return self._repository.create_environment(
            self._id_factory(), workspace_id, normalized, now=self._clock()
        )

    def update_environment(
        self, workspace_id: str, environment_id: str, input: HttpEnvironmentInput
    ) -> HttpEnvironment:
        current = self._environment(workspace_id, environment_id)
        normalized = self._validate_environment_input(input)
        conflict = self._repository.find_environment_by_name(
            workspace_id, normalized.name.casefold()
        )
        if conflict is not None and conflict.id != current.id:
            raise AppError(
                code="HTTP_ENVIRONMENT_NAME_CONFLICT",
                message="该 HTTP 环境名称已存在。",
                status_code=409,
            )
        return self._repository.update_environment(environment_id, normalized, now=self._clock())

    def delete_environment(self, workspace_id: str, environment_id: str) -> None:
        environment = self._environment(workspace_id, environment_id)
        for name in environment.secret_names:
            self._with_secret_store_error(partial(self._secret_store.delete, environment.id, name))
        self._repository.delete_environment(environment.id)

    def set_secret(
        self, workspace_id: str, environment_id: str, name: str, secret: str
    ) -> HttpEnvironment:
        environment = self._environment(workspace_id, environment_id)
        try:
            normalized_name = validate_variable_name(name)
        except ValueError as exception:
            raise AppError(
                code="HTTP_SECRET_NAME_INVALID",
                message="安全变量名称只能使用大写字母、数字和下划线。",
                status_code=422,
            ) from exception
        if not secret or len(secret) > MAX_SECRET_LENGTH or secret != secret.strip():
            raise AppError(
                code="HTTP_SECRET_INVALID",
                message="安全变量值格式不正确。",
                status_code=422,
            )
        self._with_secret_store_error(
            lambda: self._secret_store.set(environment.id, normalized_name, secret)
        )
        try:
            return self._repository.add_secret_name(
                environment.id, normalized_name, now=self._clock()
            )
        except Exception:
            self._with_secret_store_error(
                lambda: self._secret_store.delete(environment.id, normalized_name)
            )
            raise

    def delete_secret(self, workspace_id: str, environment_id: str, name: str) -> HttpEnvironment:
        environment = self._environment(workspace_id, environment_id)
        try:
            normalized_name = validate_variable_name(name)
        except ValueError as exception:
            raise AppError(
                code="HTTP_SECRET_NAME_INVALID",
                message="安全变量名称格式不正确。",
                status_code=422,
            ) from exception
        self._with_secret_store_error(
            lambda: self._secret_store.delete(environment.id, normalized_name)
        )
        return self._repository.remove_secret_name(
            environment.id, normalized_name, now=self._clock()
        )

    def start(self, workspace_id: str, input: HttpExecutionStartInput) -> HttpExecution:
        self._workspace(workspace_id)
        self._ensure_recovered()
        environment = self._environment(workspace_id, input.environment_id)
        normalized = self._validate_execution_input(input, environment)
        run = self._repository.create_run(
            run_id=self._id_factory(),
            workspace_id=workspace_id,
            environment=environment,
            input=normalized,
            created_at=self._clock(),
        )
        self._worker.launch(HttpExecutionTaskRequest(run.id))
        return run

    def list_runs(self, workspace_id: str) -> list[HttpExecution]:
        self._workspace(workspace_id)
        self._ensure_recovered()
        return self._repository.list_runs(workspace_id)

    def get_run(self, workspace_id: str, run_id: str) -> HttpExecution:
        self._workspace(workspace_id)
        self._ensure_recovered()
        run = self._repository.get_run(workspace_id, run_id)
        if run is None:
            raise AppError(
                code="HTTP_EXECUTION_NOT_FOUND",
                message="未找到该 HTTP 执行任务。",
                status_code=404,
            )
        return run

    def cancel(self, workspace_id: str, run_id: str) -> HttpExecution:
        run = self.get_run(workspace_id, run_id)
        if not run.can_cancel:
            raise AppError(
                code="HTTP_EXECUTION_FINISHED",
                message="该 HTTP 执行任务已经结束。",
                status_code=409,
            )
        self._worker.cancel(run.id)
        return self._repository.get_run(workspace_id, run.id) or run

    def rerun(self, workspace_id: str, run_id: str) -> HttpExecution:
        source = self.get_run(workspace_id, run_id)
        if source.can_cancel:
            raise AppError(
                code="HTTP_EXECUTION_ACTIVE",
                message="当前 HTTP 执行任务尚未结束。",
                status_code=409,
            )
        if (
            source.environment_id is None
            or self._repository.get_environment(workspace_id, source.environment_id) is None
        ):
            raise AppError(
                code="HTTP_ENVIRONMENT_NOT_FOUND",
                message="原 HTTP 环境已删除。无法重跑。",
                status_code=409,
            )
        run = self._repository.recreate_run(
            source.id,
            self._id_factory(),
            created_at=self._clock(),
        )
        self._worker.launch(HttpExecutionTaskRequest(run.id))
        return run

    def _workspace(self, workspace_id: str) -> Workspace:
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise AppError(
                code="WORKSPACE_NOT_FOUND", message="未找到该工作空间。", status_code=404
            )
        return workspace

    def _environment(self, workspace_id: str, environment_id: str) -> HttpEnvironment:
        environment = self._repository.get_environment(workspace_id, environment_id)
        if environment is None:
            raise AppError(
                code="HTTP_ENVIRONMENT_NOT_FOUND",
                message="未找到该 HTTP 环境。",
                status_code=404,
            )
        return environment

    @staticmethod
    def _validate_environment_input(input: HttpEnvironmentInput) -> HttpEnvironmentInput:
        name = input.name.strip()
        if not name or len(name) > MAX_ENVIRONMENT_NAME_LENGTH:
            raise AppError(
                code="HTTP_ENVIRONMENT_NAME_INVALID",
                message="HTTP 环境名称格式不正确。",
                status_code=422,
            )
        try:
            base_url = validate_and_normalize_base_url(input.base_url)
        except ValueError as exception:
            raise AppError(
                code="HTTP_ENVIRONMENT_URL_INVALID",
                message="HTTP 环境地址必须是无凭据、查询参数和片段的 HTTP/HTTPS 地址。",
                status_code=422,
            ) from exception
        if len(input.variables) > MAX_VARIABLES:
            raise AppError(
                code="HTTP_ENVIRONMENT_VARIABLES_INVALID",
                message="HTTP 环境普通变量过多。",
                status_code=422,
            )
        variables: dict[str, str] = {}
        try:
            for key, value in input.variables.items():
                validate_variable_name(key)
                if len(value) > MAX_VARIABLE_VALUE_LENGTH:
                    raise ValueError("variable value too long")
                variables[key] = value
        except ValueError as exception:
            raise AppError(
                code="HTTP_ENVIRONMENT_VARIABLES_INVALID",
                message="普通变量名称或值格式不正确。",
                status_code=422,
            ) from exception
        return HttpEnvironmentInput(name, base_url, variables)

    @staticmethod
    def _validate_execution_input(
        input: HttpExecutionStartInput,
        environment: HttpEnvironment,
    ) -> HttpExecutionStartInput:
        if input.method not in HTTP_METHODS:
            raise AppError(
                code="HTTP_METHOD_INVALID", message="HTTP 请求方法不受支持。", status_code=422
            )
        if (
            not input.path.startswith("/")
            or input.path.startswith("//")
            or len(input.path) > MAX_REQUEST_PATH_LENGTH
            or "#" in input.path
            or "\r" in input.path
            or "\n" in input.path
        ):
            raise AppError(
                code="HTTP_REQUEST_PATH_INVALID",
                message="HTTP 请求路径必须是以单个 / 开头的相对路径。",
                status_code=422,
            )
        if len(input.headers) > MAX_REQUEST_HEADERS:
            raise AppError(
                code="HTTP_REQUEST_HEADERS_INVALID",
                message="HTTP 请求头数量超过限制。",
                status_code=422,
            )
        for key, value in input.headers.items():
            if (
                HEADER_NAME_PATTERN.fullmatch(key) is None
                or len(value) > MAX_HEADER_VALUE_LENGTH
                or "\r" in value
                or "\n" in value
            ):
                raise AppError(
                    code="HTTP_REQUEST_HEADERS_INVALID",
                    message="HTTP 请求头格式不正确。",
                    status_code=422,
                )
        if input.body is not None and len(input.body.encode("utf-8")) > MAX_REQUEST_BODY_BYTES:
            raise AppError(
                code="HTTP_REQUEST_BODY_TOO_LARGE",
                message="HTTP 请求体超过 1 MiB 限制。",
                status_code=413,
            )
        if not 1 <= input.timeout_seconds <= 60:
            raise AppError(
                code="HTTP_REQUEST_TIMEOUT_INVALID",
                message="HTTP 请求超时必须在 1 到 60 秒之间。",
                status_code=422,
            )
        if not 1 <= input.max_attempts <= 3:
            raise AppError(
                code="HTTP_RETRY_INVALID",
                message="HTTP 请求尝试次数必须在 1 到 3 次之间。",
                status_code=422,
            )
        if input.max_attempts > 1 and input.method not in RETRYABLE_HTTP_METHODS:
            raise AppError(
                code="HTTP_RETRY_METHOD_UNSAFE",
                message="只有 GET、HEAD 和 OPTIONS 请求可自动重试。",
                status_code=422,
            )
        assertions = HttpExecutionService._validate_assertions(input.assertions)
        dummy_variables = {name: "value" for name in environment.variables}
        dummy_secrets = {name: "secret" for name in environment.secret_names}
        try:
            resolve_template(input.path, variables=dummy_variables, secrets=dummy_secrets)
            for value in input.headers.values():
                resolve_template(value, variables=dummy_variables, secrets=dummy_secrets)
            if input.body is not None:
                resolve_template(input.body, variables=dummy_variables, secrets=dummy_secrets)
        except HttpTemplateError as exception:
            raise AppError(
                code="HTTP_TEMPLATE_INVALID",
                message="请求模板引用了未配置或格式错误的变量。",
                status_code=422,
            ) from exception
        return HttpExecutionStartInput(
            environment_id=input.environment_id,
            method=input.method,
            path=input.path,
            headers=dict(input.headers),
            body=input.body,
            timeout_seconds=input.timeout_seconds,
            max_attempts=input.max_attempts,
            assertions=assertions,
        )

    @staticmethod
    def _validate_assertions(assertions: tuple[HttpAssertion, ...]) -> tuple[HttpAssertion, ...]:
        if len(assertions) > MAX_ASSERTIONS:
            raise AppError(
                code="HTTP_ASSERTIONS_INVALID",
                message="单次 HTTP 执行最多配置 20 条断言。",
                status_code=422,
            )
        try:
            for assertion in assertions:
                assertion.validate()
                if assertion.kind == "header_equals" and (
                    assertion.target is None
                    or HEADER_NAME_PATTERN.fullmatch(assertion.target) is None
                ):
                    raise ValueError("invalid assertion header")
        except (ValueError, TypeError) as exception:
            raise AppError(
                code="HTTP_ASSERTIONS_INVALID",
                message="HTTP 断言配置格式不正确。",
                status_code=422,
            ) from exception
        return assertions

    @staticmethod
    def _with_secret_store_error(operation: Callable[[], None]) -> None:
        try:
            operation()
        except CredentialStoreUnavailableError as exception:
            raise AppError(
                code="CREDENTIAL_STORE_UNAVAILABLE",
                message="操作系统凭据库当前不可用。",
                status_code=503,
            ) from exception

    def _ensure_recovered(self) -> None:
        if self._recovered:
            return
        with self._recovery_lock:
            if not self._recovered:
                self._worker.recover_interrupted()
                self._recovered = True
