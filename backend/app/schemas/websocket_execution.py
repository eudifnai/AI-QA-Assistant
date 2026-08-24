from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain.websocket_execution import (
    WebSocketEventLevel,
    WebSocketExecution,
    WebSocketExecutionEvent,
    WebSocketExecutionStartInput,
    WebSocketExecutionStatus,
    WebSocketMessage,
    WebSocketMessageAssertion,
    WebSocketMessageAssertionResult,
)


class WebSocketMessageAssertionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_index: int = Field(ge=0, le=19)
    kind: Literal["encoding", "text_equals", "text_contains", "json_path_equals"]
    path: str | None = Field(default=None, max_length=512)
    expected: str = Field(min_length=1, max_length=4000)

    def to_domain(self) -> WebSocketMessageAssertion:
        return WebSocketMessageAssertion(self.message_index, self.kind, self.path, self.expected)


class WebSocketExecutionStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment_id: str = Field(min_length=1, max_length=36)
    path: str = Field(min_length=1, max_length=4096)
    headers: dict[str, str] = Field(default_factory=dict, max_length=50)
    message: str = Field(min_length=1, max_length=1024 * 1024)
    timeout_seconds: int = Field(default=30, ge=1, le=60)
    additional_messages: list[str] = Field(default_factory=list, max_length=9)
    receive_count: int = Field(default=1, ge=1, le=20)
    ping_interval_seconds: int | None = Field(default=None, ge=5, le=60)
    max_reconnect_attempts: int = Field(default=0, ge=0, le=1)
    assertions: list[WebSocketMessageAssertionRequest] = Field(default_factory=list, max_length=20)

    def to_input(self) -> WebSocketExecutionStartInput:
        return WebSocketExecutionStartInput(
            self.environment_id,
            self.path,
            dict(self.headers),
            self.message,
            self.timeout_seconds,
            tuple(self.additional_messages),
            self.receive_count,
            self.ping_interval_seconds,
            self.max_reconnect_attempts,
            tuple(item.to_domain() for item in self.assertions),
        )


class WebSocketMessageResponse(BaseModel):
    ordinal: int
    message: str
    encoding: Literal["text", "base64"]
    size_bytes: int

    @classmethod
    def from_domain(cls, item: WebSocketMessage) -> "WebSocketMessageResponse":
        return cls(**{field: getattr(item, field) for field in cls.model_fields})


class WebSocketMessageAssertionResponse(BaseModel):
    message_index: int
    kind: Literal["encoding", "text_equals", "text_contains", "json_path_equals"]
    path: str | None
    expected: str

    @classmethod
    def from_domain(cls, item: WebSocketMessageAssertion) -> "WebSocketMessageAssertionResponse":
        return cls(**{field: getattr(item, field) for field in cls.model_fields})


class WebSocketMessageAssertionResultResponse(WebSocketMessageAssertionResponse):
    actual: str | None
    passed: bool
    message: str

    @classmethod
    def from_result(
        cls, item: WebSocketMessageAssertionResult
    ) -> "WebSocketMessageAssertionResultResponse":
        return cls(**{field: getattr(item, field) for field in cls.model_fields})


class WebSocketExecutionEventResponse(BaseModel):
    id: str
    ordinal: int
    level: WebSocketEventLevel
    code: str
    message: str
    created_at: datetime

    @classmethod
    def from_domain(cls, event: WebSocketExecutionEvent) -> "WebSocketExecutionEventResponse":
        return cls(**{field: getattr(event, field) for field in cls.model_fields})


class WebSocketExecutionResponse(BaseModel):
    id: str
    workspace_id: str
    environment_id: str | None
    environment_name: str
    base_url: str
    path_template: str
    headers_template: dict[str, str]
    message_template: str
    additional_message_templates: list[str]
    receive_count: int
    ping_interval_seconds: int | None
    max_reconnect_attempts: int
    timeout_seconds: int
    status: WebSocketExecutionStatus
    progress: int
    response_message: str | None
    response_encoding: Literal["text", "base64"] | None
    response_size_bytes: int | None
    duration_ms: int | None
    responses: list[WebSocketMessageResponse]
    assertions: list[WebSocketMessageAssertionResponse]
    assertion_results: list[WebSocketMessageAssertionResultResponse]
    attempt_count: int
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    events: list[WebSocketExecutionEventResponse]

    @classmethod
    def from_domain(cls, run: WebSocketExecution) -> "WebSocketExecutionResponse":
        excluded = {
            "additional_message_templates",
            "responses",
            "assertions",
            "assertion_results",
            "events",
        }
        scalar_fields = {
            field: getattr(run, field) for field in cls.model_fields if field not in excluded
        }
        return cls(
            **scalar_fields,
            additional_message_templates=list(run.additional_message_templates),
            responses=[WebSocketMessageResponse.from_domain(item) for item in run.responses],
            assertions=[
                WebSocketMessageAssertionResponse.from_domain(item) for item in run.assertions
            ],
            assertion_results=[
                WebSocketMessageAssertionResultResponse.from_result(item)
                for item in run.assertion_results
            ],
            events=[WebSocketExecutionEventResponse.from_domain(item) for item in run.events],
        )
