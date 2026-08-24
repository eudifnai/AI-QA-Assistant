from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from backend.app.domain.reports import ReportArtifact, ReportFormat, ReportSnapshot


class ReportEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    level: str
    code: str
    message: str
    created_at: datetime


class ReportExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    execution_type: str
    id: str
    name: str
    status: str
    duration_ms: int | None
    request_summary: str
    response_summary: str | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    finished_at: datetime | None
    events: list[ReportEventResponse]


class ReportExecutionSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total: int
    passed: int
    failed: int
    error: int
    cancelled: int
    timeout: int
    active: int
    terminal: int
    evaluated: int
    pass_rate: float
    average_duration_ms: int | None


class ReportTrendPointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    passed: int
    failed: int
    error: int
    cancelled: int
    timeout: int
    terminal: int
    evaluated: int
    pass_rate: float
    average_duration_ms: int | None


class FailureAttributionSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total: int
    product: int
    environment: int
    data: int
    script: int
    unknown: int


class FailureAttributionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    execution_type: Literal["http", "websocket", "protobuf"]
    execution_id: str
    execution_name: str
    status: str
    error_code: str | None
    category: Literal["product", "environment", "data", "script", "unknown"]
    rule_id: str
    reason: str


class ReportAnalysisSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total: int
    passed: int
    failed_or_error: int
    latest_overall_score: int | None
    issue_count: int


class ReportDesignSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    test_point_total: int
    test_point_confirmed: int
    test_case_total: int
    test_case_confirmed: int


class ReportSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    schema_version: Literal[2]
    workspace_id: str
    workspace_name: str
    generated_at: datetime
    execution_summary: ReportExecutionSummaryResponse
    analysis_summary: ReportAnalysisSummaryResponse
    design_summary: ReportDesignSummaryResponse
    trend: list[ReportTrendPointResponse]
    failure_attribution_summary: FailureAttributionSummaryResponse
    failure_attributions: list[FailureAttributionResponse]
    slow_executions: list[ReportExecutionResponse]
    executions: list[ReportExecutionResponse]

    @classmethod
    def from_domain(cls, snapshot: ReportSnapshot) -> "ReportSnapshotResponse":
        return cls.model_validate(snapshot)


class ReportRenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: ReportFormat


class ReportArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    format: ReportFormat
    file_name: str
    media_type: str
    content: str
    generated_at: datetime

    @classmethod
    def from_domain(cls, artifact: ReportArtifact) -> "ReportArtifactResponse":
        return cls.model_validate(artifact)
