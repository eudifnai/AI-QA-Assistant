from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.application.test_design import (
    IssueReviewInput,
    TestCaseBatchStatusInput,
    TestCaseStepInput,
    TestCaseUpdateInput,
    TestPointUpdateInput,
)
from backend.app.domain.analysis import AnalysisDimension, AnalysisSeverity
from backend.app.domain.test_design import (
    AutomationRecommendation,
    AutomationRuleId,
    IssueReview,
    IssueReviewStatus,
    TestCase,
    TestCaseAutomationType,
    TestCaseBatchStatus,
    TestCaseStatus,
    TestCaseStep,
    TestDesignSnapshot,
    TestPoint,
    TestPointPriority,
    TestPointStatus,
    TestPointType,
    TraceabilityCoverageStatus,
    TraceabilityRow,
)
from backend.app.schemas.analysis import AnalysisCitationResponse


class IssueReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: IssueReviewStatus
    answer: str = Field(min_length=1, max_length=2000)

    @field_validator("answer")
    @classmethod
    def non_blank_answer(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("answer must not be blank")
        return value

    def to_input(self) -> IssueReviewInput:
        return IssueReviewInput(**self.model_dump())


class TestPointUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    objective: str = Field(min_length=1, max_length=4000)
    test_type: TestPointType
    priority: TestPointPriority
    status: TestPointStatus
    automation_candidate: bool

    @field_validator("title", "objective")
    @classmethod
    def non_blank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text must not be blank")
        return value

    def to_input(self) -> TestPointUpdateInput:
        return TestPointUpdateInput(**self.model_dump())


class TestCaseStepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str = Field(min_length=1, max_length=2000)
    expected_result: str = Field(min_length=1, max_length=2000)

    @field_validator("action", "expected_result")
    @classmethod
    def non_blank_step_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("step text must not be blank")
        return value

    def to_input(self) -> TestCaseStepInput:
        return TestCaseStepInput(self.action, self.expected_result)


class TestCaseUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    preconditions: list[str] = Field(max_length=20)
    priority: TestPointPriority
    tags: list[str] = Field(max_length=20)
    automation_type: TestCaseAutomationType
    status: TestCaseStatus
    steps: list[TestCaseStepRequest] = Field(min_length=1, max_length=50)

    @field_validator("title")
    @classmethod
    def non_blank_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value

    @field_validator("preconditions", "tags")
    @classmethod
    def normalized_short_lists(cls, values: list[str]) -> list[str]:
        normalized = [item.strip() for item in values]
        if any(not item or len(item) > 1000 for item in normalized):
            raise ValueError("list items must be non-blank and at most 1000 characters")
        return normalized

    @model_validator(mode="after")
    def unique_tags(self) -> "TestCaseUpdateRequest":
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("tags must be unique")
        return self

    def to_input(self) -> TestCaseUpdateInput:
        return TestCaseUpdateInput(
            title=self.title,
            preconditions=tuple(self.preconditions),
            priority=self.priority,
            tags=tuple(self.tags),
            automation_type=self.automation_type,
            status=self.status,
            steps=tuple(step.to_input() for step in self.steps),
        )


class TestCaseBatchStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_case_ids: list[str] = Field(min_length=1, max_length=100)
    status: TestCaseBatchStatus

    @model_validator(mode="after")
    def unique_ids(self) -> "TestCaseBatchStatusRequest":
        if len(self.test_case_ids) != len(set(self.test_case_ids)):
            raise ValueError("test case ids must be unique")
        return self

    def to_input(self) -> TestCaseBatchStatusInput:
        return TestCaseBatchStatusInput(tuple(self.test_case_ids), self.status)


class IssueReviewResponse(BaseModel):
    id: str
    run_id: str
    issue_id: str
    status: IssueReviewStatus
    answer: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, review: IssueReview) -> "IssueReviewResponse":
        return cls(**{field: getattr(review, field) for field in cls.model_fields})


class TestPointResponse(BaseModel):
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

    @classmethod
    def from_domain(cls, point: TestPoint) -> "TestPointResponse":
        return cls(**{field: getattr(point, field) for field in cls.model_fields})


class TestCaseStepResponse(BaseModel):
    id: str
    ordinal: int
    action: str
    expected_result: str

    @classmethod
    def from_domain(cls, step: TestCaseStep) -> "TestCaseStepResponse":
        return cls(**{field: getattr(step, field) for field in cls.model_fields})


class TestCaseResponse(BaseModel):
    id: str
    run_id: str
    source_test_point_id: str
    title: str
    preconditions: list[str]
    priority: TestPointPriority
    tags: list[str]
    automation_type: TestCaseAutomationType
    status: TestCaseStatus
    steps: list[TestCaseStepResponse]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, case: TestCase) -> "TestCaseResponse":
        return cls(
            id=case.id,
            run_id=case.run_id,
            source_test_point_id=case.source_test_point_id,
            title=case.title,
            preconditions=list(case.preconditions),
            priority=case.priority,
            tags=list(case.tags),
            automation_type=case.automation_type,
            status=case.status,
            steps=[TestCaseStepResponse.from_domain(step) for step in case.steps],
            created_at=case.created_at,
            updated_at=case.updated_at,
        )


class TraceabilityRowResponse(BaseModel):
    issue_id: str
    issue_title: str
    dimension: AnalysisDimension
    severity: AnalysisSeverity
    citations: list[AnalysisCitationResponse]
    review_status: IssueReviewStatus | None
    review_answer: str | None
    test_point_id: str | None
    test_point_title: str | None
    test_point_status: TestPointStatus | None
    test_case_id: str | None
    test_case_title: str | None
    test_case_status: TestCaseStatus | None
    coverage_status: TraceabilityCoverageStatus

    @classmethod
    def from_domain(cls, row: TraceabilityRow) -> "TraceabilityRowResponse":
        return cls(
            issue_id=row.issue_id,
            issue_title=row.issue_title,
            dimension=row.dimension,
            severity=row.severity,
            citations=[AnalysisCitationResponse.from_domain(item) for item in row.citations],
            review_status=row.review_status,
            review_answer=row.review_answer,
            test_point_id=row.test_point_id,
            test_point_title=row.test_point_title,
            test_point_status=row.test_point_status,
            test_case_id=row.test_case_id,
            test_case_title=row.test_case_title,
            test_case_status=row.test_case_status,
            coverage_status=row.coverage_status,
        )


class AutomationRecommendationResponse(BaseModel):
    test_point_id: str
    recommended: bool
    suggested_type: TestCaseAutomationType
    rule_id: AutomationRuleId
    reason: str

    @classmethod
    def from_domain(
        cls, recommendation: AutomationRecommendation
    ) -> "AutomationRecommendationResponse":
        return cls(**{field: getattr(recommendation, field) for field in cls.model_fields})


class TestDesignSnapshotResponse(BaseModel):
    reviews: list[IssueReviewResponse]
    test_points: list[TestPointResponse]
    test_cases: list[TestCaseResponse]
    traceability: list[TraceabilityRowResponse]
    automation_recommendations: list[AutomationRecommendationResponse]

    @classmethod
    def from_domain(cls, snapshot: TestDesignSnapshot) -> "TestDesignSnapshotResponse":
        return cls(
            reviews=[IssueReviewResponse.from_domain(item) for item in snapshot.reviews],
            test_points=[TestPointResponse.from_domain(item) for item in snapshot.test_points],
            test_cases=[TestCaseResponse.from_domain(item) for item in snapshot.test_cases],
            traceability=[
                TraceabilityRowResponse.from_domain(item) for item in snapshot.traceability
            ],
            automation_recommendations=[
                AutomationRecommendationResponse.from_domain(item)
                for item in snapshot.automation_recommendations
            ],
        )
