from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.domain.settings import ModelProvider

AnalysisStatus = Literal[
    "pending", "queued", "running", "passed", "failed", "error", "cancelled", "timeout"
]
AnalysisDimension = Literal["completeness", "consistency", "clarity", "testability", "feasibility"]
AnalysisSeverity = Literal["low", "medium", "high", "critical"]
ANALYSIS_DIMENSIONS: tuple[AnalysisDimension, ...] = (
    "completeness",
    "consistency",
    "clarity",
    "testability",
    "feasibility",
)
TERMINAL_ANALYSIS_STATUSES: frozenset[AnalysisStatus] = frozenset(
    {"passed", "failed", "error", "cancelled", "timeout"}
)

ShortText = Annotated[str, Field(min_length=1, max_length=500)]
LongText = Annotated[str, Field(min_length=1, max_length=4000)]


class AnalysisDimensionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: AnalysisDimension
    score: int = Field(ge=0, le=100)
    summary: LongText


class AnalysisIssueOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: AnalysisDimension
    severity: AnalysisSeverity
    title: ShortText
    description: LongText
    impact: LongText
    suggestion: LongText
    question: LongText
    citation_chunk_ids: list[str] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def unique_citations(self) -> "AnalysisIssueOutput":
        if len(self.citation_chunk_ids) != len(set(self.citation_chunk_ids)):
            raise ValueError("duplicate citation")
        return self


class AnalysisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_score: int = Field(ge=0, le=100)
    dimension_scores: list[AnalysisDimensionOutput] = Field(min_length=5, max_length=5)
    issues: list[AnalysisIssueOutput] = Field(max_length=100)

    @model_validator(mode="after")
    def complete_dimensions(self) -> "AnalysisOutput":
        dimensions = [score.dimension for score in self.dimension_scores]
        if len(dimensions) != len(set(dimensions)) or set(dimensions) != set(ANALYSIS_DIMENSIONS):
            raise ValueError("all analysis dimensions are required exactly once")
        return self


def validate_analysis_citations(output: AnalysisOutput, allowed_chunk_ids: set[str]) -> None:
    for issue in output.issues:
        if not set(issue.citation_chunk_ids) <= allowed_chunk_ids:
            raise ValueError("unknown citation")


@dataclass(frozen=True, slots=True)
class AnalysisCitation:
    chunk_id: str
    ordinal: int
    locator: str
    text: str


@dataclass(frozen=True, slots=True)
class AnalysisScore:
    dimension: AnalysisDimension
    score: int
    summary: str


@dataclass(frozen=True, slots=True)
class AnalysisIssue:
    id: str
    ordinal: int
    dimension: AnalysisDimension
    severity: AnalysisSeverity
    title: str
    description: str
    impact: str
    suggestion: str
    question: str
    citations: tuple[AnalysisCitation, ...]


@dataclass(frozen=True, slots=True)
class AnalysisRun:
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
    scores: tuple[AnalysisScore, ...]
    issues: tuple[AnalysisIssue, ...]

    @property
    def can_cancel(self) -> bool:
        return self.status not in TERMINAL_ANALYSIS_STATUSES


@dataclass(frozen=True, slots=True)
class AnalysisTaskRequest:
    run_id: str


@dataclass(frozen=True, slots=True)
class AnalysisExecutionInput:
    run_id: str
    provider: ModelProvider
    base_url: str
    model_name: str
    chunks: tuple[AnalysisCitation, ...]
