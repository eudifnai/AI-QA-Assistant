from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain.protobuf_execution import (
    ProtoEventLevel,
    ProtoExecution,
    ProtoExecutionEvent,
    ProtoExecutionStartInput,
    ProtoExecutionStatus,
    ProtoFieldAssertion,
    ProtoFieldAssertionResult,
)
from backend.app.schemas.proto_assets import MESSAGE_TYPE_PATTERN, SHA256_PATTERN


class ProtoFieldAssertionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=3, max_length=512)
    expected_json: str = Field(min_length=1, max_length=4000)

    def to_domain(self) -> ProtoFieldAssertion:
        return ProtoFieldAssertion(self.path, self.expected_json)


class ProtoExecutionStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment_id: str = Field(min_length=1, max_length=36)
    asset_id: str = Field(min_length=1, max_length=36)
    expected_sha256: str = Field(pattern=SHA256_PATTERN)
    service_name: str = Field(min_length=1, max_length=255, pattern=MESSAGE_TYPE_PATTERN)
    method_name: str = Field(min_length=1, max_length=255, pattern=MESSAGE_TYPE_PATTERN)
    path: str = Field(min_length=1, max_length=4096)
    headers: dict[str, str] = Field(default_factory=dict, max_length=50)
    request_payload: dict[str, Any]
    timeout_seconds: int = Field(default=30, ge=1, le=60)
    assertions: list[ProtoFieldAssertionRequest] = Field(default_factory=list, max_length=20)

    def to_input(self) -> ProtoExecutionStartInput:
        return ProtoExecutionStartInput(
            self.environment_id,
            self.asset_id,
            self.expected_sha256,
            self.service_name,
            self.method_name,
            self.path,
            dict(self.headers),
            dict(self.request_payload),
            self.timeout_seconds,
            tuple(item.to_domain() for item in self.assertions),
        )


class ProtoFieldAssertionResponse(BaseModel):
    path: str
    expected_json: str

    @classmethod
    def from_domain(cls, item: ProtoFieldAssertion) -> "ProtoFieldAssertionResponse":
        return cls(path=item.path, expected_json=item.expected_json)


class ProtoFieldAssertionResultResponse(ProtoFieldAssertionResponse):
    actual: str | None
    passed: bool
    message: str

    @classmethod
    def from_result(cls, item: ProtoFieldAssertionResult) -> "ProtoFieldAssertionResultResponse":
        return cls(**{name: getattr(item, name) for name in cls.model_fields})


class ProtoExecutionEventResponse(BaseModel):
    id: str
    ordinal: int
    level: ProtoEventLevel
    code: str
    message: str
    created_at: datetime

    @classmethod
    def from_domain(cls, item: ProtoExecutionEvent) -> "ProtoExecutionEventResponse":
        return cls(**{name: getattr(item, name) for name in cls.model_fields})


class ProtoExecutionResponse(BaseModel):
    id: str
    workspace_id: str
    environment_id: str | None
    environment_name: str
    asset_id: str | None
    asset_name: str
    asset_sha256: str
    service_name: str
    method_name: str
    base_url: str
    path_template: str
    headers_template: dict[str, str]
    request_message_type: str
    response_message_type: str
    request_payload: dict[str, Any]
    timeout_seconds: int
    assertions: list[ProtoFieldAssertionResponse]
    assertion_results: list[ProtoFieldAssertionResultResponse]
    status: ProtoExecutionStatus
    progress: int
    response_status_code: int | None
    response_headers: dict[str, str]
    response_payload: dict[str, Any] | None
    response_size_bytes: int | None
    duration_ms: int | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    events: list[ProtoExecutionEventResponse]

    @classmethod
    def from_domain(cls, run: ProtoExecution) -> "ProtoExecutionResponse":
        excluded = {"assertions", "assertion_results", "events"}
        scalar_fields = {
            name: getattr(run, name) for name in cls.model_fields if name not in excluded
        }
        return cls(
            **scalar_fields,
            assertions=[ProtoFieldAssertionResponse.from_domain(item) for item in run.assertions],
            assertion_results=[
                ProtoFieldAssertionResultResponse.from_result(item)
                for item in run.assertion_results
            ],
            events=[ProtoExecutionEventResponse.from_domain(item) for item in run.events],
        )
