from datetime import UTC, datetime

from fastapi.testclient import TestClient

from backend.app.application.test_design import (
    IssueReviewInput,
)
from backend.app.application.test_design import (
    TestCaseBatchStatusInput as CaseBatchStatusInput,
)
from backend.app.application.test_design import (
    TestCaseUpdateInput as CaseUpdateInput,
)
from backend.app.application.test_design import (
    TestDesignUseCases as DesignUseCases,
)
from backend.app.application.test_design import (
    TestPointUpdateInput as PointUpdateInput,
)
from backend.app.domain.test_design import (
    AutomationRecommendation,
    IssueReview,
    TraceabilityRow,
)
from backend.app.domain.test_design import TestCase as DesignCase
from backend.app.domain.test_design import TestCaseStep as DesignCaseStep
from backend.app.domain.test_design import (
    TestDesignSnapshot as DesignSnapshot,
)
from backend.app.domain.test_design import (
    TestPoint as DesignPoint,
)
from backend.app.main import create_app

NOW = datetime(2026, 8, 14, 3, 0, tzinfo=UTC)
REVIEW = IssueReview("review-1", "run-1", "issue-1", "accepted", "24 小时", NOW, NOW)
POINT = DesignPoint(
    "point-1",
    "run-1",
    "issue-1",
    "验证退款期限",
    "确认结论: 24 小时",
    "boundary",
    "P1",
    "draft",
    False,
    NOW,
    NOW,
)
CASE = DesignCase(
    "case-1",
    "run-1",
    "point-1",
    "验证退款期限",
    ("退款服务可用",),
    "P1",
    ("boundary",),
    "manual",
    "draft",
    (DesignCaseStep("step-1", 1, "提交退款申请", "退款在 24 小时内完成"),),
    NOW,
    NOW,
)
TRACEABILITY = TraceabilityRow(
    "issue-1",
    "退款期限不清晰",
    "clarity",
    "high",
    (),
    "accepted",
    "24 小时",
    "point-1",
    "验证退款期限",
    "draft",
    "case-1",
    "验证退款期限",
    "draft",
    "case_draft",
)
AUTOMATION_RECOMMENDATION = AutomationRecommendation(
    "point-1",
    True,
    "api",
    "repeatable_api",
    "边界验证输入输出明确且可重复。建议优先采用 API 自动化。",
)


class StubDesign(DesignUseCases):
    review_input: IssueReviewInput | None = None
    point_input: PointUpdateInput | None = None
    case_input: CaseUpdateInput | None = None
    batch_input: CaseBatchStatusInput | None = None

    def get_snapshot(self, workspace_id: str, run_id: str) -> DesignSnapshot:
        return DesignSnapshot(
            (REVIEW,),
            (POINT,),
            (CASE,),
            (TRACEABILITY,),
            (AUTOMATION_RECOMMENDATION,),
        )

    def review_issue(
        self, workspace_id: str, run_id: str, issue_id: str, input: IssueReviewInput
    ) -> IssueReview:
        self.review_input = input
        return REVIEW

    def generate_test_points(self, workspace_id: str, run_id: str) -> list[DesignPoint]:
        return [POINT]

    def update_test_point(
        self,
        workspace_id: str,
        run_id: str,
        point_id: str,
        input: PointUpdateInput,
    ) -> DesignPoint:
        self.point_input = input
        return POINT

    def generate_test_cases(self, workspace_id: str, run_id: str) -> list[DesignCase]:
        return [CASE]

    def update_test_case(
        self,
        workspace_id: str,
        run_id: str,
        case_id: str,
        input: CaseUpdateInput,
    ) -> DesignCase:
        self.case_input = input
        return CASE

    def batch_update_test_cases(
        self,
        workspace_id: str,
        run_id: str,
        input: CaseBatchStatusInput,
    ) -> list[DesignCase]:
        self.batch_input = input
        return [CASE]


def test_test_design_snapshot_review_generation_and_update_api() -> None:
    service = StubDesign()
    app = create_app(test_design_service=service)
    with TestClient(app) as client:
        snapshot = client.get("/api/workspaces/workspace-1/analysis-runs/run-1/test-design")
        reviewed = client.put(
            "/api/workspaces/workspace-1/analysis-runs/run-1/issues/issue-1/review",
            json={"status": "accepted", "answer": "24 小时"},
        )
        generated = client.post(
            "/api/workspaces/workspace-1/analysis-runs/run-1/test-points/generate"
        )
        updated = client.put(
            "/api/workspaces/workspace-1/analysis-runs/run-1/test-points/point-1",
            json={
                "title": "验证退款期限",
                "objective": "退款必须在 24 小时内完成。",
                "test_type": "boundary",
                "priority": "P0",
                "status": "confirmed",
                "automation_candidate": True,
            },
        )
        cases = client.post("/api/workspaces/workspace-1/analysis-runs/run-1/test-cases/generate")
        updated_case = client.put(
            "/api/workspaces/workspace-1/analysis-runs/run-1/test-cases/case-1",
            json={
                "title": "验证退款期限",
                "preconditions": ["退款服务可用"],
                "priority": "P1",
                "tags": ["退款", "边界"],
                "automation_type": "api",
                "status": "draft",
                "steps": [{"action": "提交退款申请", "expected_result": "退款在 24 小时内完成"}],
            },
        )
        batched = client.put(
            "/api/workspaces/workspace-1/analysis-runs/run-1/test-cases/batch-status",
            json={"test_case_ids": ["case-1"], "status": "confirmed"},
        )

    assert snapshot.status_code == 200
    assert snapshot.json()["reviews"][0]["issue_id"] == "issue-1"
    assert snapshot.json()["test_cases"][0]["steps"][0]["ordinal"] == 1
    assert snapshot.json()["traceability"][0]["coverage_status"] == "case_draft"
    assert snapshot.json()["traceability"][0]["test_case_id"] == "case-1"
    assert snapshot.json()["automation_recommendations"][0]["suggested_type"] == "api"
    assert snapshot.json()["automation_recommendations"][0]["rule_id"] == "repeatable_api"
    assert reviewed.status_code == 200
    assert service.review_input == IssueReviewInput(status="accepted", answer="24 小时")
    assert generated.status_code == 201
    assert generated.json()[0]["source_issue_id"] == "issue-1"
    assert updated.status_code == 200
    assert service.point_input is not None
    assert service.point_input.status == "confirmed"
    assert cases.status_code == 201
    assert updated_case.status_code == 200
    assert service.case_input is not None
    assert service.case_input.automation_type == "api"
    assert batched.status_code == 200
    assert service.batch_input == CaseBatchStatusInput(
        test_case_ids=("case-1",), status="confirmed"
    )


def test_test_design_rejects_empty_review_and_extra_point_fields() -> None:
    app = create_app(test_design_service=StubDesign())
    with TestClient(app) as client:
        empty = client.put(
            "/api/workspaces/workspace-1/analysis-runs/run-1/issues/issue-1/review",
            json={"status": "accepted", "answer": "   "},
        )
        extra = client.put(
            "/api/workspaces/workspace-1/analysis-runs/run-1/test-points/point-1",
            json={
                "title": "验证退款期限",
                "objective": "退款必须在 24 小时内完成。",
                "test_type": "boundary",
                "priority": "P0",
                "status": "confirmed",
                "automation_candidate": True,
                "secret": "must-not-be-accepted",
            },
        )

    assert empty.status_code == 422
    assert empty.json()["code"] == "VALIDATION_ERROR"
    assert extra.status_code == 422
    assert extra.json()["code"] == "VALIDATION_ERROR"


def test_test_case_api_rejects_empty_steps_and_duplicate_batch_ids() -> None:
    app = create_app(test_design_service=StubDesign())
    with TestClient(app) as client:
        no_steps = client.put(
            "/api/workspaces/workspace-1/analysis-runs/run-1/test-cases/case-1",
            json={
                "title": "验证退款期限",
                "preconditions": [],
                "priority": "P1",
                "tags": [],
                "automation_type": "manual",
                "status": "draft",
                "steps": [],
            },
        )
        duplicates = client.put(
            "/api/workspaces/workspace-1/analysis-runs/run-1/test-cases/batch-status",
            json={"test_case_ids": ["case-1", "case-1"], "status": "confirmed"},
        )

    assert no_steps.status_code == 422
    assert duplicates.status_code == 422
