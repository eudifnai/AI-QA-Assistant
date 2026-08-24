from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar, Protocol
from uuid import uuid4

from backend.app.core.errors import AppError
from backend.app.domain.analysis import AnalysisIssue, AnalysisRun
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


class AnalysisRunReader(Protocol):
    def get_run(self, workspace_id: str, run_id: str) -> AnalysisRun: ...


class TestDesignRepository(Protocol):
    def list_reviews(self, run_id: str) -> list[IssueReview]: ...

    def upsert_review(self, review: IssueReview) -> IssueReview: ...

    def list_test_points(self, run_id: str) -> list[TestPoint]: ...

    def create_test_point(self, point: TestPoint) -> TestPoint: ...

    def update_test_point(self, point: TestPoint) -> TestPoint: ...

    def list_test_cases(self, run_id: str) -> list[TestCase]: ...

    def create_test_case(self, case: TestCase) -> TestCase: ...

    def update_test_case(self, case: TestCase) -> TestCase: ...

    def update_test_case_statuses(
        self,
        run_id: str,
        case_ids: tuple[str, ...],
        status: TestCaseBatchStatus,
        updated_at: datetime,
    ) -> list[TestCase] | None: ...


@dataclass(frozen=True, slots=True)
class IssueReviewInput:
    status: IssueReviewStatus
    answer: str


@dataclass(frozen=True, slots=True)
class TestPointUpdateInput:
    title: str
    objective: str
    test_type: TestPointType
    priority: TestPointPriority
    status: TestPointStatus
    automation_candidate: bool


@dataclass(frozen=True, slots=True)
class TestCaseStepInput:
    action: str
    expected_result: str


@dataclass(frozen=True, slots=True)
class TestCaseUpdateInput:
    title: str
    preconditions: tuple[str, ...]
    priority: TestPointPriority
    tags: tuple[str, ...]
    automation_type: TestCaseAutomationType
    status: TestCaseStatus
    steps: tuple[TestCaseStepInput, ...]


@dataclass(frozen=True, slots=True)
class TestCaseBatchStatusInput:
    test_case_ids: tuple[str, ...]
    status: TestCaseBatchStatus


class TestDesignUseCases(Protocol):
    def get_snapshot(self, workspace_id: str, run_id: str) -> TestDesignSnapshot: ...

    def review_issue(
        self, workspace_id: str, run_id: str, issue_id: str, input: IssueReviewInput
    ) -> IssueReview: ...

    def generate_test_points(self, workspace_id: str, run_id: str) -> list[TestPoint]: ...

    def update_test_point(
        self,
        workspace_id: str,
        run_id: str,
        point_id: str,
        input: TestPointUpdateInput,
    ) -> TestPoint: ...

    def generate_test_cases(self, workspace_id: str, run_id: str) -> list[TestCase]: ...

    def update_test_case(
        self,
        workspace_id: str,
        run_id: str,
        case_id: str,
        input: TestCaseUpdateInput,
    ) -> TestCase: ...

    def batch_update_test_cases(
        self,
        workspace_id: str,
        run_id: str,
        input: TestCaseBatchStatusInput,
    ) -> list[TestCase]: ...


class TestDesignService:
    _priority_by_severity: ClassVar[dict[str, TestPointPriority]] = {
        "critical": "P0",
        "high": "P1",
        "medium": "P2",
        "low": "P3",
    }
    _type_by_dimension: ClassVar[dict[str, TestPointType]] = {
        "completeness": "positive",
        "consistency": "state",
        "clarity": "positive",
        "testability": "positive",
        "feasibility": "performance",
    }

    def __init__(
        self,
        analyses: AnalysisRunReader,
        designs: TestDesignRepository,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._analyses = analyses
        self._designs = designs
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))

    def get_snapshot(self, workspace_id: str, run_id: str) -> TestDesignSnapshot:
        run = self._passed_run(workspace_id, run_id)
        reviews = self._designs.list_reviews(run_id)
        points = self._designs.list_test_points(run_id)
        cases = self._designs.list_test_cases(run_id)
        return TestDesignSnapshot(
            tuple(reviews),
            tuple(points),
            tuple(cases),
            tuple(self._traceability(run, reviews, points, cases)),
            tuple(self._automation_recommendation(point) for point in points),
        )

    def review_issue(
        self, workspace_id: str, run_id: str, issue_id: str, input: IssueReviewInput
    ) -> IssueReview:
        run = self._passed_run(workspace_id, run_id)
        self._issue(run, issue_id)
        answer = input.answer.strip()
        if input.status not in {"accepted", "rejected"} or not answer:
            raise AppError(
                code="ISSUE_REVIEW_INVALID",
                message="请选择确认结论并填写说明。",
                status_code=422,
            )
        if any(
            point.source_issue_id == issue_id for point in self._designs.list_test_points(run_id)
        ):
            raise AppError(
                code="ISSUE_REVIEW_LOCKED",
                message="该确认结论已生成测试点, 请直接编辑或禁用测试点。",
                status_code=409,
            )
        now = self._clock()
        existing = next(
            (
                review
                for review in self._designs.list_reviews(run_id)
                if review.issue_id == issue_id
            ),
            None,
        )
        return self._designs.upsert_review(
            IssueReview(
                existing.id if existing else self._id_factory(),
                run_id,
                issue_id,
                input.status,
                answer,
                existing.created_at if existing else now,
                now,
            )
        )

    def generate_test_points(self, workspace_id: str, run_id: str) -> list[TestPoint]:
        run = self._passed_run(workspace_id, run_id)
        reviews = {
            review.issue_id: review
            for review in self._designs.list_reviews(run_id)
            if review.status == "accepted"
        }
        if not reviews:
            raise AppError(
                code="TEST_POINT_NO_ACCEPTED_ISSUES",
                message="请先至少确认一个需要覆盖的问题。",
                status_code=409,
            )
        existing = {
            point.source_issue_id: point for point in self._designs.list_test_points(run_id)
        }
        for issue in run.issues:
            review = reviews.get(issue.id)
            if review is None or issue.id in existing:
                continue
            now = self._clock()
            point = self._designs.create_test_point(self._new_point(run, issue, review, now))
            existing[issue.id] = point
        return self._designs.list_test_points(run_id)

    def update_test_point(
        self,
        workspace_id: str,
        run_id: str,
        point_id: str,
        input: TestPointUpdateInput,
    ) -> TestPoint:
        self._passed_run(workspace_id, run_id)
        current = next(
            (point for point in self._designs.list_test_points(run_id) if point.id == point_id),
            None,
        )
        if current is None:
            raise AppError(code="TEST_POINT_NOT_FOUND", message="未找到该测试点。", status_code=404)
        if any(
            case.source_test_point_id == point_id for case in self._designs.list_test_cases(run_id)
        ):
            raise AppError(
                code="TEST_POINT_LOCKED",
                message="该测试点已生成测试用例, 请直接编辑或禁用测试用例。",
                status_code=409,
            )
        title = input.title.strip()
        objective = input.objective.strip()
        if not title or not objective:
            raise AppError(
                code="TEST_POINT_INVALID", message="测试点标题和目标不能为空。", status_code=422
            )
        return self._designs.update_test_point(
            TestPoint(
                current.id,
                current.run_id,
                current.source_issue_id,
                title,
                objective,
                input.test_type,
                input.priority,
                input.status,
                input.automation_candidate,
                current.created_at,
                self._clock(),
            )
        )

    def generate_test_cases(self, workspace_id: str, run_id: str) -> list[TestCase]:
        self._passed_run(workspace_id, run_id)
        points = [
            point for point in self._designs.list_test_points(run_id) if point.status == "confirmed"
        ]
        if not points:
            raise AppError(
                code="TEST_CASE_NO_CONFIRMED_POINTS",
                message="请先至少确认一个测试点。",
                status_code=409,
            )
        existing = {
            case.source_test_point_id: case for case in self._designs.list_test_cases(run_id)
        }
        for point in points:
            if point.id in existing:
                continue
            now = self._clock()
            case = self._designs.create_test_case(self._new_case(point, now))
            existing[point.id] = case
        return self._designs.list_test_cases(run_id)

    def update_test_case(
        self,
        workspace_id: str,
        run_id: str,
        case_id: str,
        input: TestCaseUpdateInput,
    ) -> TestCase:
        self._passed_run(workspace_id, run_id)
        current = next(
            (case for case in self._designs.list_test_cases(run_id) if case.id == case_id),
            None,
        )
        if current is None:
            raise AppError(
                code="TEST_CASE_NOT_FOUND", message="未找到该测试用例。", status_code=404
            )
        title, preconditions, tags, steps = self._validate_case_input(input)
        domain_steps = tuple(
            TestCaseStep(
                current.steps[index].id if index < len(current.steps) else self._id_factory(),
                index + 1,
                step.action,
                step.expected_result,
            )
            for index, step in enumerate(steps)
        )
        return self._designs.update_test_case(
            TestCase(
                current.id,
                current.run_id,
                current.source_test_point_id,
                title,
                preconditions,
                input.priority,
                tags,
                input.automation_type,
                input.status,
                domain_steps,
                current.created_at,
                self._clock(),
            )
        )

    def batch_update_test_cases(
        self,
        workspace_id: str,
        run_id: str,
        input: TestCaseBatchStatusInput,
    ) -> list[TestCase]:
        self._passed_run(workspace_id, run_id)
        if (
            not input.test_case_ids
            or len(input.test_case_ids) != len(set(input.test_case_ids))
            or input.status not in {"confirmed", "disabled"}
        ):
            raise AppError(
                code="TEST_CASE_BATCH_INVALID",
                message="请选择不重复的测试用例和有效目标状态。",
                status_code=422,
            )
        updated = self._designs.update_test_case_statuses(
            run_id, input.test_case_ids, input.status, self._clock()
        )
        if updated is None:
            raise AppError(
                code="TEST_CASE_NOT_FOUND",
                message="部分测试用例不存在或不属于当前分析运行。",
                status_code=404,
            )
        return updated

    def _passed_run(self, workspace_id: str, run_id: str) -> AnalysisRun:
        run = self._analyses.get_run(workspace_id, run_id)
        if run.status != "passed":
            raise AppError(
                code="TEST_DESIGN_ANALYSIS_NOT_READY",
                message="需求分析完成后才能确认问题并生成测试点。",
                status_code=409,
            )
        return run

    @staticmethod
    def _issue(run: AnalysisRun, issue_id: str) -> AnalysisIssue:
        issue = next((item for item in run.issues if item.id == issue_id), None)
        if issue is None:
            raise AppError(
                code="ANALYSIS_ISSUE_NOT_FOUND", message="未找到该分析问题。", status_code=404
            )
        return issue

    def _new_point(
        self, run: AnalysisRun, issue: AnalysisIssue, review: IssueReview, now: datetime
    ) -> TestPoint:
        objective = f"确认结论: {review.answer}\n验证目标: {issue.suggestion}"[:4000]
        test_type = self._type_by_dimension[issue.dimension]
        recommended, _, _, _ = self._automation_rule(test_type)
        return TestPoint(
            self._id_factory(),
            run.id,
            issue.id,
            f"验证: {issue.title}"[:500],
            objective,
            test_type,
            self._priority_by_severity[issue.severity],
            "draft",
            recommended,
            now,
            now,
        )

    def _new_case(self, point: TestPoint, now: datetime) -> TestCase:
        recommendation = self._automation_recommendation(point)
        return TestCase(
            self._id_factory(),
            point.run_id,
            point.id,
            point.title,
            ("已准备测试环境和符合要求的测试数据。",),
            point.priority,
            (point.test_type,),
            recommendation.suggested_type if point.automation_candidate else "manual",
            "draft",
            (
                TestCaseStep(
                    self._id_factory(),
                    1,
                    point.objective,
                    "实际结果满足该测试点的验证目标。",
                ),
            ),
            now,
            now,
        )

    @staticmethod
    def _automation_recommendation(point: TestPoint) -> AutomationRecommendation:
        recommended, suggested_type, rule_id, reason = TestDesignService._automation_rule(
            point.test_type
        )
        return AutomationRecommendation(
            point.id,
            recommended,
            suggested_type,
            rule_id,
            reason,
        )

    @staticmethod
    def _automation_rule(
        test_type: TestPointType,
    ) -> tuple[bool, TestCaseAutomationType, AutomationRuleId, str]:
        if test_type == "performance":
            return (
                True,
                "api",
                "performance_api",
                "性能验证需要可重复采样和量化指标。建议优先采用 API 自动化。",
            )
        if test_type in {"negative", "boundary", "state", "permission"}:
            return (
                True,
                "api",
                "repeatable_api",
                "该类型输入输出明确且可重复。建议优先采用 API 自动化。",
            )
        return (
            False,
            "manual",
            "manual_context",
            "正向或兼容性场景通常依赖业务流程、设备或环境上下文。建议先人工评审。",
        )

    @staticmethod
    def _traceability(
        run: AnalysisRun,
        reviews: list[IssueReview],
        points: list[TestPoint],
        cases: list[TestCase],
    ) -> list[TraceabilityRow]:
        reviews_by_issue = {review.issue_id: review for review in reviews}
        points_by_issue = {point.source_issue_id: point for point in points}
        cases_by_point = {case.source_test_point_id: case for case in cases}
        rows: list[TraceabilityRow] = []
        for issue in run.issues:
            review = reviews_by_issue.get(issue.id)
            point = points_by_issue.get(issue.id)
            case = cases_by_point.get(point.id) if point is not None else None
            rows.append(
                TraceabilityRow(
                    issue.id,
                    issue.title,
                    issue.dimension,
                    issue.severity,
                    issue.citations,
                    review.status if review else None,
                    review.answer if review else None,
                    point.id if point else None,
                    point.title if point else None,
                    point.status if point else None,
                    case.id if case else None,
                    case.title if case else None,
                    case.status if case else None,
                    TestDesignService._coverage_status(review, point, case),
                )
            )
        return rows

    @staticmethod
    def _coverage_status(
        review: IssueReview | None,
        point: TestPoint | None,
        case: TestCase | None,
    ) -> TraceabilityCoverageStatus:
        if case is not None:
            if case.status == "confirmed":
                return "covered"
            if case.status == "disabled":
                return "disabled"
            return "case_draft"
        if point is not None:
            if point.status == "disabled":
                return "disabled"
            return "test_point"
        if review is None:
            return "unreviewed"
        if review.status == "rejected":
            return "excluded"
        return "accepted"

    @staticmethod
    def _validate_case_input(
        input: TestCaseUpdateInput,
    ) -> tuple[str, tuple[str, ...], tuple[str, ...], tuple[TestCaseStepInput, ...]]:
        title = input.title.strip()
        preconditions = tuple(item.strip() for item in input.preconditions if item.strip())
        tags = tuple(item.strip() for item in input.tags if item.strip())
        steps = tuple(
            TestCaseStepInput(step.action.strip(), step.expected_result.strip())
            for step in input.steps
        )
        if (
            not title
            or not steps
            or any(not step.action or not step.expected_result for step in steps)
            or len(tags) != len(set(tags))
        ):
            raise AppError(
                code="TEST_CASE_INVALID",
                message="测试用例标题、步骤和期望不能为空, 标签不得重复。",
                status_code=422,
            )
        return title, preconditions, tags, steps
