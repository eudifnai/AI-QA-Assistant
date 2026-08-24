from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from backend.app.domain.analysis import (
    AnalysisCitation,
    AnalysisDimension,
    AnalysisSeverity,
)

IssueReviewStatus = Literal["accepted", "rejected"]
TestPointType = Literal[
    "positive",
    "negative",
    "boundary",
    "state",
    "permission",
    "compatibility",
    "performance",
]
TestPointPriority = Literal["P0", "P1", "P2", "P3"]
TestPointStatus = Literal["draft", "confirmed", "disabled"]
TestCaseAutomationType = Literal["manual", "api", "web", "mobile"]
TestCaseStatus = Literal["draft", "confirmed", "disabled"]
TestCaseBatchStatus = Literal["confirmed", "disabled"]
AutomationRuleId = Literal["repeatable_api", "performance_api", "manual_context"]
TraceabilityCoverageStatus = Literal[
    "unreviewed",
    "excluded",
    "accepted",
    "test_point",
    "case_draft",
    "covered",
    "disabled",
]


@dataclass(frozen=True, slots=True)
class IssueReview:
    id: str
    run_id: str
    issue_id: str
    status: IssueReviewStatus
    answer: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class TestPoint:
    id: str
    run_id: str
    source_issue_id: str
    title: str
    objective: str
    test_type: TestPointType
    priority: TestPointPriority
    status: TestPointStatus
    automation_candidate: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class TestCaseStep:
    id: str
    ordinal: int
    action: str
    expected_result: str


@dataclass(frozen=True, slots=True)
class TestCase:
    id: str
    run_id: str
    source_test_point_id: str
    title: str
    preconditions: tuple[str, ...]
    priority: TestPointPriority
    tags: tuple[str, ...]
    automation_type: TestCaseAutomationType
    status: TestCaseStatus
    steps: tuple[TestCaseStep, ...]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AutomationRecommendation:
    test_point_id: str
    recommended: bool
    suggested_type: TestCaseAutomationType
    rule_id: AutomationRuleId
    reason: str


@dataclass(frozen=True, slots=True)
class TraceabilityRow:
    issue_id: str
    issue_title: str
    dimension: AnalysisDimension
    severity: AnalysisSeverity
    citations: tuple[AnalysisCitation, ...]
    review_status: IssueReviewStatus | None
    review_answer: str | None
    test_point_id: str | None
    test_point_title: str | None
    test_point_status: TestPointStatus | None
    test_case_id: str | None
    test_case_title: str | None
    test_case_status: TestCaseStatus | None
    coverage_status: TraceabilityCoverageStatus


@dataclass(frozen=True, slots=True)
class TestDesignSnapshot:
    reviews: tuple[IssueReview, ...]
    test_points: tuple[TestPoint, ...]
    test_cases: tuple[TestCase, ...]
    traceability: tuple[TraceabilityRow, ...]
    automation_recommendations: tuple[AutomationRecommendation, ...]
