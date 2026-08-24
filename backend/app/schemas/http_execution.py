from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain.http_execution import (
    HttpAssertion,
    HttpAssertionKind,
    HttpAssertionResult,
    HttpEnvironment,
    HttpEnvironmentInput,
    HttpEventLevel,
    HttpExecution,
    HttpExecutionEvent,
    HttpExecutionStartInput,
    HttpExecutionStatus,
    HttpMethod,
)


class HttpEnvironmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    base_url: str = Field(min_length=1, max_length=2048)
    variables: dict[str, str] = Field(default_factory=dict, max_length=100)

    def to_input(self) -> HttpEnvironmentInput:
        return HttpEnvironmentInput(**self.model_dump())


class HttpEnvironmentResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    base_url: str
    variables: dict[str, str]
    secret_names: list[str]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, environment: HttpEnvironment) -> "HttpEnvironmentResponse":
        return cls(
            id=environment.id,
            workspace_id=environment.workspace_id,
            name=environment.name,
            base_url=environment.base_url,
            variables=environment.variables,
            secret_names=list(environment.secret_names),
            created_at=environment.created_at,
            updated_at=environment.updated_at,
        )


class HttpSecretRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    secret: str = Field(min_length=1, max_length=8192)


class HttpExecutionStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment_id: str = Field(min_length=1, max_length=36)
    method: HttpMethod
    path: str = Field(min_length=1, max_length=4096)
    headers: dict[str, str] = Field(default_factory=dict, max_length=50)
    body: str | None = Field(default=None, max_length=1024 * 1024)
    timeout_seconds: int = Field(default=30, ge=1, le=60)
    max_attempts: int = Field(default=1, ge=1, le=3)
    assertions: list["HttpAssertionRequest"] = Field(default_factory=list, max_length=20)

    def to_input(self) -> HttpExecutionStartInput:
        values = self.model_dump(exclude={"assertions"})
        return HttpExecutionStartInput(
            **values,
            assertions=tuple(item.to_domain() for item in self.assertions),
        )


class HttpAssertionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: HttpAssertionKind
    target: str | None = Field(default=None, max_length=128)
    expected: str = Field(min_length=1, max_length=4000)

    def to_domain(self) -> HttpAssertion:
        return HttpAssertion(self.kind, self.target, self.expected)


class HttpAssertionResponse(BaseModel):
    kind: HttpAssertionKind
    target: str | None
    expected: str

    @classmethod
    def from_domain(cls, assertion: HttpAssertion) -> "HttpAssertionResponse":
        return cls(**{field: getattr(assertion, field) for field in cls.model_fields})


class HttpAssertionResultResponse(HttpAssertionResponse):
    actual: str | None
    passed: bool
    message: str

    @classmethod
    def from_result(cls, result: HttpAssertionResult) -> "HttpAssertionResultResponse":
        return cls(**{field: getattr(result, field) for field in cls.model_fields})


class HttpExecutionEventResponse(BaseModel):
    id: str
    ordinal: int
    level: HttpEventLevel
    code: str
    message: str
    attempt: int | None
    created_at: datetime

    @classmethod
    def from_domain(cls, event: HttpExecutionEvent) -> "HttpExecutionEventResponse":
        return cls(**{field: getattr(event, field) for field in cls.model_fields})


class HttpExecutionResponse(BaseModel):
    id: str
    workspace_id: str
    environment_id: str | None
    environment_name: str
    method: HttpMethod
    base_url: str
    path_template: str
    headers_template: dict[str, str]
    body_template: str | None
    timeout_seconds: int
    max_attempts: int
    assertions: list[HttpAssertionResponse]
    assertion_results: list[HttpAssertionResultResponse]
    events: list[HttpExecutionEventResponse]
    status: HttpExecutionStatus
    progress: int
    response_status_code: int | None
    response_headers: dict[str, str]
    response_body: str | None
    response_body_encoding: str | None
    response_size_bytes: int | None
    duration_ms: int | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def from_domain(cls, run: HttpExecution) -> "HttpExecutionResponse":
        scalar_fields = {
            field: getattr(run, field)
            for field in cls.model_fields
            if field not in {"assertions", "assertion_results", "events"}
        }
        return cls(
            **scalar_fields,
            assertions=[HttpAssertionResponse.from_domain(item) for item in run.assertions],
            assertion_results=[
                HttpAssertionResultResponse.from_result(item) for item in run.assertion_results
            ],
            events=[HttpExecutionEventResponse.from_domain(item) for item in run.events],
        )
