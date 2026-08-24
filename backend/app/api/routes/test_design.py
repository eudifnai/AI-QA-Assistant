from fastapi import APIRouter, status

from backend.app.application.test_design import TestDesignUseCases
from backend.app.schemas.test_design import (
    IssueReviewRequest,
    IssueReviewResponse,
    TestCaseBatchStatusRequest,
    TestCaseResponse,
    TestCaseUpdateRequest,
    TestDesignSnapshotResponse,
    TestPointResponse,
    TestPointUpdateRequest,
)


def create_test_design_router(service: TestDesignUseCases) -> APIRouter:
    router = APIRouter(tags=["test-design"])

    @router.get(
        "/api/workspaces/{workspace_id}/analysis-runs/{run_id}/test-design",
        response_model=TestDesignSnapshotResponse,
    )
    def get_test_design(workspace_id: str, run_id: str) -> TestDesignSnapshotResponse:
        return TestDesignSnapshotResponse.from_domain(service.get_snapshot(workspace_id, run_id))

    @router.put(
        "/api/workspaces/{workspace_id}/analysis-runs/{run_id}/issues/{issue_id}/review",
        response_model=IssueReviewResponse,
    )
    def review_issue(
        workspace_id: str,
        run_id: str,
        issue_id: str,
        request: IssueReviewRequest,
    ) -> IssueReviewResponse:
        return IssueReviewResponse.from_domain(
            service.review_issue(workspace_id, run_id, issue_id, request.to_input())
        )

    @router.post(
        "/api/workspaces/{workspace_id}/analysis-runs/{run_id}/test-points/generate",
        response_model=list[TestPointResponse],
        status_code=status.HTTP_201_CREATED,
    )
    def generate_test_points(workspace_id: str, run_id: str) -> list[TestPointResponse]:
        return [
            TestPointResponse.from_domain(item)
            for item in service.generate_test_points(workspace_id, run_id)
        ]

    @router.put(
        "/api/workspaces/{workspace_id}/analysis-runs/{run_id}/test-points/{point_id}",
        response_model=TestPointResponse,
    )
    def update_test_point(
        workspace_id: str,
        run_id: str,
        point_id: str,
        request: TestPointUpdateRequest,
    ) -> TestPointResponse:
        return TestPointResponse.from_domain(
            service.update_test_point(workspace_id, run_id, point_id, request.to_input())
        )

    @router.post(
        "/api/workspaces/{workspace_id}/analysis-runs/{run_id}/test-cases/generate",
        response_model=list[TestCaseResponse],
        status_code=status.HTTP_201_CREATED,
    )
    def generate_test_cases(workspace_id: str, run_id: str) -> list[TestCaseResponse]:
        return [
            TestCaseResponse.from_domain(item)
            for item in service.generate_test_cases(workspace_id, run_id)
        ]

    @router.put(
        "/api/workspaces/{workspace_id}/analysis-runs/{run_id}/test-cases/batch-status",
        response_model=list[TestCaseResponse],
    )
    def batch_update_test_cases(
        workspace_id: str,
        run_id: str,
        request: TestCaseBatchStatusRequest,
    ) -> list[TestCaseResponse]:
        return [
            TestCaseResponse.from_domain(item)
            for item in service.batch_update_test_cases(workspace_id, run_id, request.to_input())
        ]

    @router.put(
        "/api/workspaces/{workspace_id}/analysis-runs/{run_id}/test-cases/{case_id}",
        response_model=TestCaseResponse,
    )
    def update_test_case(
        workspace_id: str,
        run_id: str,
        case_id: str,
        request: TestCaseUpdateRequest,
    ) -> TestCaseResponse:
        return TestCaseResponse.from_domain(
            service.update_test_case(workspace_id, run_id, case_id, request.to_input())
        )

    return router
