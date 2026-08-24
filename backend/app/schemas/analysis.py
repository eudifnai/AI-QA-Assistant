from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.app.application.analysis import AnalysisStartInput
from backend.app.domain.analysis import (
    AnalysisCitation,
    AnalysisDimension,
    AnalysisIssue,
    AnalysisRun,
    AnalysisScore,
    AnalysisSeverity,
    AnalysisStatus,
)
from backend.app.domain.settings import MAX_BASE_URL_LENGTH, MAX_MODEL_NAME_LENGTH, ModelProvider


class AnalysisStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version_id: str = Field(min_length=1, max_length=36)
    expected_provider: ModelProvider
    expected_model_name: str = Field(min_length=1, max_length=MAX_MODEL_NAME_LENGTH)
    expected_base_url: str = Field(min_length=1, max_length=MAX_BASE_URL_LENGTH)
    expected_input_chunk_count: int = Field(ge=1)
    expected_input_character_count: int = Field(ge=1)
    cloud_data_confirmed: bool

    def to_input(self) -> AnalysisStartInput:
        return AnalysisStartInput(**self.model_dump())


class AnalysisCitationResponse(BaseModel):
    chunk_id: str
    ordinal: int
    locator: str
    text: str

    @classmethod
    def from_domain(cls, citation: AnalysisCitation) -> "AnalysisCitationResponse":
        return cls(**{field: getattr(citation, field) for field in cls.model_fields})


class AnalysisScoreResponse(BaseModel):
    dimension: AnalysisDimension
    score: int
    summary: str

    @classmethod
    def from_domain(cls, score: AnalysisScore) -> "AnalysisScoreResponse":
        return cls(**{field: getattr(score, field) for field in cls.model_fields})


class AnalysisIssueResponse(BaseModel):
    id: str
    ordinal: int
    dimension: AnalysisDimension
    severity: AnalysisSeverity
    title: str
    description: str
    impact: str
    suggestion: str
    question: str
    citations: list[AnalysisCitationResponse]

    @classmethod
    def from_domain(cls, issue: AnalysisIssue) -> "AnalysisIssueResponse":
        return cls(
            id=issue.id,
            ordinal=issue.ordinal,
            dimension=issue.dimension,
            severity=issue.severity,
            title=issue.title,
            description=issue.description,
            impact=issue.impact,
            suggestion=issue.suggestion,
            question=issue.question,
            citations=[AnalysisCitationResponse.from_domain(item) for item in issue.citations],
        )


class AnalysisRunResponse(BaseModel):
    id: str
    workspace_id: str
    document_id: str
    version_id: str
    provider: ModelProvider
    model_name: str
    base_url: str
    input_chunk_count: int
    input_character_count: int
    cloud_data_confirmed_at: datetime | None
    status: AnalysisStatus
    progress: int
    overall_score: int | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    scores: list[AnalysisScoreResponse]
    issues: list[AnalysisIssueResponse]

    @classmethod
    def from_domain(cls, run: AnalysisRun) -> "AnalysisRunResponse":
        return cls(
            id=run.id,
            workspace_id=run.workspace_id,
            document_id=run.document_id,
            version_id=run.version_id,
            provider=run.provider,
            model_name=run.model_name,
            base_url=run.base_url,
            input_chunk_count=run.input_chunk_count,
            input_character_count=run.input_character_count,
            cloud_data_confirmed_at=run.cloud_data_confirmed_at,
            status=run.status,
            progress=run.progress,
            overall_score=run.overall_score,
            error_code=run.error_code,
            error_message=run.error_message,
            created_at=run.created_at,
            started_at=run.started_at,
            finished_at=run.finished_at,
            scores=[AnalysisScoreResponse.from_domain(item) for item in run.scores],
            issues=[AnalysisIssueResponse.from_domain(item) for item in run.issues],
        )
