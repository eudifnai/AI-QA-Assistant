from dataclasses import replace
from datetime import UTC, datetime

import pytest

from backend.app.application.test_design import (
    IssueReviewInput,
)
from backend.app.application.test_design import (
    TestCaseBatchStatusInput as CaseBatchStatusInput,
)
from backend.app.application.test_design import (
    TestCaseStepInput as CaseStepInput,
)
from backend.app.application.test_design import (
    TestCaseUpdateInput as CaseUpdateInput,
)
from backend.app.application.test_design import (
    TestDesignService as DesignService,
)
from backend.app.application.test_design import (
    TestPointUpdateInput as PointUpdateInput,
)
from backend.app.core.errors import AppError
from backend.app.domain.analysis import AnalysisCitation, AnalysisIssue, AnalysisRun
from backend.app.domain.settings import ModelProvider
from backend.app.domain.test_design import IssueReview
from backend.app.domain.test_design import TestCase as DesignCase
from backend.app.domain.test_design import TestCaseStep as DesignCaseStep
from backend.app.domain.test_design import TestPoint as DesignPoint

NOW = datetime(2026, 8, 14, 2, 0, tzinfo=UTC)
ISSUE = AnalysisIssue(
    "issue-1",
    1,
    "clarity",
    "high",
    "退款期限不清晰",
    "没有说明退款完成期限。",
    "无法设计时间边界测试。",
    "补充最长退款时间。",
    "退款应在多久内完成?",
    (AnalysisCitation("chunk-1", 1, "第 2 行", "必须支持退款。"),),
)
PASSED_RUN = AnalysisRun(
    "run-1",
    "workspace-1",
    "document-1",
    "version-1",
    ModelProvider.OLLAMA,
    "qwen3:8b",
    "http://127.0.0.1:11434",
    1,
    7,
    None,
    "passed",
    100,
    82,
    None,
    None,
    NOW,
    NOW,
    NOW,
    (),
    (ISSUE,),
)


class Analyses:
    def __init__(self, run: AnalysisRun = PASSED_RUN) -> None:
        self.run = run

    def get_run(self, workspace_id: str, run_id: str) -> AnalysisRun:
        if workspace_id != self.run.workspace_id or run_id != self.run.id:
            raise AppError(
                code="ANALYSIS_RUN_NOT_FOUND", message="未找到该分析任务。", status_code=404
            )
        return self.run


class Designs:
    def __init__(self) -> None:
        self.reviews: dict[str, IssueReview] = {}
        self.points: dict[str, DesignPoint] = {}
        self.cases: dict[str, DesignCase] = {}

    def list_reviews(self, run_id: str) -> list[IssueReview]:
        return [item for item in self.reviews.values() if item.run_id == run_id]

    def upsert_review(self, review: IssueReview) -> IssueReview:
        self.reviews[review.issue_id] = review
        return review

    def list_test_points(self, run_id: str) -> list[DesignPoint]:
        return [item for item in self.points.values() if item.run_id == run_id]

    def create_test_point(self, point: DesignPoint) -> DesignPoint:
        return self.points.setdefault(point.source_issue_id, point)

    def update_test_point(self, point: DesignPoint) -> DesignPoint:
        self.points[point.source_issue_id] = point
        return point

    def list_test_cases(self, run_id: str) -> list[DesignCase]:
        return [item for item in self.cases.values() if item.run_id == run_id]

    def create_test_case(self, case: DesignCase) -> DesignCase:
        return self.cases.setdefault(case.source_test_point_id, case)

    def update_test_case(self, case: DesignCase) -> DesignCase:
        self.cases[case.source_test_point_id] = case
        return case

    def update_test_case_statuses(
        self, run_id: str, case_ids: tuple[str, ...], status: str, updated_at: datetime
    ) -> list[DesignCase] | None:
        selected = [case for case in self.cases.values() if case.id in case_ids]
        if len(selected) != len(case_ids) or any(case.run_id != run_id for case in selected):
            return None
        for case in selected:
            self.cases[case.source_test_point_id] = DesignCase(
                case.id,
                case.run_id,
                case.source_test_point_id,
                case.title,
                case.preconditions,
                case.priority,
                case.tags,
                case.automation_type,
                status,  # type: ignore[arg-type]
                case.steps,
                case.created_at,
                updated_at,
            )
        return [self.cases[case.source_test_point_id] for case in selected]


def subject(*, analyses: Analyses | None = None, designs: Designs | None = None) -> DesignService:
    ids = iter(["review-1", "point-1", "case-1", "step-1", "step-2", "extra-1"])
    return DesignService(
        analyses or Analyses(),
        designs or Designs(),
        clock=lambda: NOW,
        id_factory=lambda: next(ids),
    )


def test_review_issue_and_generate_editable_point_idempotently() -> None:
    designs = Designs()
    service = subject(designs=designs)

    review = service.review_issue(
        "workspace-1",
        "run-1",
        "issue-1",
        IssueReviewInput(status="accepted", answer="  24 小时内完成  "),
    )
    first = service.generate_test_points("workspace-1", "run-1")
    second = service.generate_test_points("workspace-1", "run-1")

    assert review.answer == "24 小时内完成"
    assert len(first) == len(second) == 1
    assert first[0].id == second[0].id == "point-1"
    assert first[0].source_issue_id == ISSUE.id
    assert first[0].priority == "P1"
    assert first[0].test_type == "positive"
    assert "24 小时内完成" in first[0].objective

    updated = service.update_test_point(
        "workspace-1",
        "run-1",
        "point-1",
        PointUpdateInput(
            title="验证退款时限边界",
            objective="退款必须在 24 小时内完成。",
            test_type="boundary",
            priority="P0",
            status="confirmed",
            automation_candidate=True,
        ),
    )
    assert updated.title == "验证退款时限边界"
    assert updated.test_type == "boundary"
    assert updated.status == "confirmed"
    assert updated.automation_candidate is True

    first_cases = service.generate_test_cases("workspace-1", "run-1")
    second_cases = service.generate_test_cases("workspace-1", "run-1")
    assert len(first_cases) == len(second_cases) == 1
    assert first_cases[0].id == second_cases[0].id == "case-1"
    assert first_cases[0].source_test_point_id == "point-1"
    assert first_cases[0].priority == "P0"
    assert first_cases[0].tags == ("boundary",)
    assert first_cases[0].steps[0].id == "step-1"

    edited_case = service.update_test_case(
        "workspace-1",
        "run-1",
        "case-1",
        CaseUpdateInput(
            title="退款 24 小时边界用例",
            preconditions=("退款服务可用", "存在待退款订单"),
            priority="P0",
            tags=("退款", "边界"),
            automation_type="api",
            status="draft",
            steps=(
                CaseStepInput("提交退款申请", "申请被受理"),
                CaseStepInput("等待 24 小时", "退款完成"),
            ),
        ),
    )
    assert edited_case.steps[0].id == "step-1"
    assert edited_case.steps[1].id == "step-2"
    assert edited_case.automation_type == "api"

    confirmed = service.batch_update_test_cases(
        "workspace-1",
        "run-1",
        CaseBatchStatusInput(test_case_ids=("case-1",), status="confirmed"),
    )
    assert confirmed[0].status == "confirmed"

    with pytest.raises(AppError) as point_locked:
        service.update_test_point(
            "workspace-1",
            "run-1",
            "point-1",
            PointUpdateInput(
                title="不应改写",
                objective="不应改写",
                test_type="positive",
                priority="P3",
                status="disabled",
                automation_candidate=False,
            ),
        )
    assert point_locked.value.code == "TEST_POINT_LOCKED"


def test_generation_only_uses_accepted_reviews_and_locks_audited_decision() -> None:
    designs = Designs()
    service = subject(designs=designs)
    service.review_issue(
        "workspace-1",
        "run-1",
        "issue-1",
        IssueReviewInput(status="accepted", answer="24 小时内完成"),
    )
    service.generate_test_points("workspace-1", "run-1")

    with pytest.raises(AppError) as locked:
        service.review_issue(
            "workspace-1",
            "run-1",
            "issue-1",
            IssueReviewInput(status="rejected", answer="无需覆盖"),
        )

    assert locked.value.code == "ISSUE_REVIEW_LOCKED"
    assert locked.value.status_code == 409


def test_review_and_generation_require_passed_scoped_run_and_known_issue() -> None:
    not_passed = AnalysisRun(
        PASSED_RUN.id,
        PASSED_RUN.workspace_id,
        PASSED_RUN.document_id,
        PASSED_RUN.version_id,
        PASSED_RUN.provider,
        PASSED_RUN.model_name,
        PASSED_RUN.base_url,
        PASSED_RUN.input_chunk_count,
        PASSED_RUN.input_character_count,
        PASSED_RUN.cloud_data_confirmed_at,
        "running",
        60,
        None,
        None,
        None,
        PASSED_RUN.created_at,
        PASSED_RUN.started_at,
        None,
        (),
        (),
    )
    with pytest.raises(AppError) as state_error:
        subject(analyses=Analyses(not_passed)).generate_test_points("workspace-1", "run-1")
    assert state_error.value.code == "TEST_DESIGN_ANALYSIS_NOT_READY"

    with pytest.raises(AppError) as issue_error:
        subject().review_issue(
            "workspace-1",
            "run-1",
            "missing",
            IssueReviewInput(status="accepted", answer="确认"),
        )
    assert issue_error.value.code == "ANALYSIS_ISSUE_NOT_FOUND"

    with pytest.raises(AppError) as no_review:
        subject().generate_test_points("workspace-1", "run-1")
    assert no_review.value.code == "TEST_POINT_NO_ACCEPTED_ISSUES"


def test_case_generation_requires_confirmed_points_and_batch_update_is_atomic() -> None:
    designs = Designs()
    designs.points["issue-1"] = DesignPoint(
        "point-1",
        "run-1",
        "issue-1",
        "退款期限",
        "验证退款期限",
        "boundary",
        "P1",
        "draft",
        False,
        NOW,
        NOW,
    )
    service = subject(designs=designs)

    with pytest.raises(AppError) as no_confirmed:
        service.generate_test_cases("workspace-1", "run-1")
    assert no_confirmed.value.code == "TEST_CASE_NO_CONFIRMED_POINTS"

    designs.points["issue-1"] = DesignPoint(
        "point-1",
        "run-1",
        "issue-1",
        "退款期限",
        "验证退款期限",
        "boundary",
        "P1",
        "confirmed",
        False,
        NOW,
        NOW,
    )
    service.generate_test_cases("workspace-1", "run-1")

    with pytest.raises(AppError) as missing:
        service.batch_update_test_cases(
            "workspace-1",
            "run-1",
            CaseBatchStatusInput(test_case_ids=("case-1", "missing"), status="confirmed"),
        )
    assert missing.value.code == "TEST_CASE_NOT_FOUND"
    assert designs.list_test_cases("run-1")[0].status == "draft"


def test_snapshot_derives_auditable_traceability_coverage_states() -> None:
    designs = Designs()
    service = subject(designs=designs)

    row = service.get_snapshot("workspace-1", "run-1").traceability[0]
    assert row.issue_id == "issue-1"
    assert row.coverage_status == "unreviewed"
    assert row.citations == ISSUE.citations

    designs.reviews["issue-1"] = IssueReview(
        "review-1", "run-1", "issue-1", "rejected", "无需覆盖", NOW, NOW
    )
    assert (
        service.get_snapshot("workspace-1", "run-1").traceability[0].coverage_status == "excluded"
    )

    designs.reviews["issue-1"] = IssueReview(
        "review-1", "run-1", "issue-1", "accepted", "24 小时内完成", NOW, NOW
    )
    accepted = service.get_snapshot("workspace-1", "run-1").traceability[0]
    assert accepted.coverage_status == "accepted"
    assert accepted.review_answer == "24 小时内完成"

    point = DesignPoint(
        "point-1",
        "run-1",
        "issue-1",
        "验证退款期限",
        "退款必须在 24 小时内完成",
        "boundary",
        "P1",
        "confirmed",
        False,
        NOW,
        NOW,
    )
    designs.points["issue-1"] = point
    point_row = service.get_snapshot("workspace-1", "run-1").traceability[0]
    assert point_row.coverage_status == "test_point"
    assert point_row.test_point_id == "point-1"

    case = DesignCase(
        "case-1",
        "run-1",
        "point-1",
        "退款期限边界",
        (),
        "P1",
        ("boundary",),
        "manual",
        "draft",
        (DesignCaseStep("step-1", 1, "提交退款", "24 小时内完成"),),
        NOW,
        NOW,
    )
    designs.cases["point-1"] = case
    draft_case = service.get_snapshot("workspace-1", "run-1").traceability[0]
    assert draft_case.coverage_status == "case_draft"
    assert draft_case.test_case_id == "case-1"

    designs.cases["point-1"] = DesignCase(
        case.id,
        case.run_id,
        case.source_test_point_id,
        case.title,
        case.preconditions,
        case.priority,
        case.tags,
        case.automation_type,
        "confirmed",
        case.steps,
        case.created_at,
        case.updated_at,
    )
    assert service.get_snapshot("workspace-1", "run-1").traceability[0].coverage_status == "covered"

    designs.cases["point-1"] = DesignCase(
        case.id,
        case.run_id,
        case.source_test_point_id,
        case.title,
        case.preconditions,
        case.priority,
        case.tags,
        case.automation_type,
        "disabled",
        case.steps,
        case.created_at,
        case.updated_at,
    )
    assert (
        service.get_snapshot("workspace-1", "run-1").traceability[0].coverage_status == "disabled"
    )


@pytest.mark.parametrize(
    ("test_type", "recommended", "suggested_type", "rule_id"),
    [
        ("positive", False, "manual", "manual_context"),
        ("compatibility", False, "manual", "manual_context"),
        ("negative", True, "api", "repeatable_api"),
        ("boundary", True, "api", "repeatable_api"),
        ("state", True, "api", "repeatable_api"),
        ("permission", True, "api", "repeatable_api"),
        ("performance", True, "api", "performance_api"),
    ],
)
def test_snapshot_exposes_transparent_automation_recommendations(
    test_type: str,
    recommended: bool,
    suggested_type: str,
    rule_id: str,
) -> None:
    designs = Designs()
    designs.points["issue-1"] = DesignPoint(
        "point-1",
        "run-1",
        "issue-1",
        "退款期限",
        "验证退款期限",
        test_type,  # type: ignore[arg-type]
        "P1",
        "draft",
        False,
        NOW,
        NOW,
    )

    recommendation = (
        subject(designs=designs).get_snapshot("workspace-1", "run-1").automation_recommendations[0]
    )

    assert recommendation.test_point_id == "point-1"
    assert recommendation.recommended is recommended
    assert recommendation.suggested_type == suggested_type
    assert recommendation.rule_id == rule_id
    assert recommendation.reason


def test_generated_repeatable_point_and_case_inherit_automation_rule() -> None:
    repeatable_issue = replace(
        ISSUE,
        id="issue-state",
        dimension="consistency",
        title="退款状态流转不一致",
    )
    designs = Designs()
    service = subject(
        analyses=Analyses(replace(PASSED_RUN, issues=(repeatable_issue,))),
        designs=designs,
    )
    service.review_issue(
        "workspace-1",
        "run-1",
        "issue-state",
        IssueReviewInput(status="accepted", answer="按状态机验证"),
    )

    point = service.generate_test_points("workspace-1", "run-1")[0]
    assert point.test_type == "state"
    assert point.automation_candidate is True
    service.update_test_point(
        "workspace-1",
        "run-1",
        point.id,
        PointUpdateInput(
            title=point.title,
            objective=point.objective,
            test_type=point.test_type,
            priority=point.priority,
            status="confirmed",
            automation_candidate=point.automation_candidate,
        ),
    )

    case = service.generate_test_cases("workspace-1", "run-1")[0]
    assert case.automation_type == "api"
