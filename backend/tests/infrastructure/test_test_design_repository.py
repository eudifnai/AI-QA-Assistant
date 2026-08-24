from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import Session, SQLModel

from backend.app.domain.test_design import IssueReview
from backend.app.domain.test_design import TestCase as DesignCase
from backend.app.domain.test_design import TestCaseStep as DesignCaseStep
from backend.app.domain.test_design import TestPoint as DesignPoint
from backend.app.infrastructure.analysis import AnalysisIssueRecord, AnalysisRunRecord
from backend.app.infrastructure.database import create_database_engine
from backend.app.infrastructure.documents import DocumentRecord, DocumentVersionRecord
from backend.app.infrastructure.test_design import SqlModelTestDesignRepository
from backend.app.infrastructure.workspaces import WorkspaceRecord

NOW = datetime(2026, 8, 14, 4, 0, tzinfo=UTC)


def repository(tmp_path: Path) -> SqlModelTestDesignRepository:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'test-design.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            WorkspaceRecord(
                id="workspace-1",
                name="支付",
                name_key="支付",
                path_key=str(tmp_path).casefold(),
                path=str(tmp_path),
                created_at=NOW,
                last_opened_at=NOW,
            )
        )
        session.add(
            DocumentRecord(
                id="document-1",
                workspace_id="workspace-1",
                name="requirements.md",
                relative_path="requirements.md",
                path_key="requirements.md",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.add(
            DocumentVersionRecord(
                id="version-1",
                document_id="document-1",
                workspace_id="workspace-1",
                version_number=1,
                sha256="a" * 64,
                size_bytes=7,
                status="passed",
                parsed_text="必须退款",
                created_at=NOW,
            )
        )
        session.add(
            AnalysisRunRecord(
                id="run-1",
                workspace_id="workspace-1",
                document_id="document-1",
                version_id="version-1",
                provider="ollama",
                model_name="qwen3:8b",
                base_url="http://127.0.0.1:11434",
                input_chunk_count=1,
                input_character_count=4,
                status="passed",
                progress=100,
                created_at=NOW,
            )
        )
        session.add(
            AnalysisIssueRecord(
                id="issue-1",
                run_id="run-1",
                ordinal=1,
                dimension="clarity",
                severity="high",
                title="退款期限不清晰",
                description="没有说明期限。",
                impact="无法测试。",
                suggestion="补充期限。",
                question="多久退款?",
            )
        )
        session.commit()
    return SqlModelTestDesignRepository(engine)


def test_repository_upserts_reviews_and_creates_points_idempotently(tmp_path: Path) -> None:
    designs = repository(tmp_path)
    first_review = IssueReview("review-1", "run-1", "issue-1", "accepted", "24 小时", NOW, NOW)
    updated_review = IssueReview("review-1", "run-1", "issue-1", "rejected", "无需覆盖", NOW, NOW)
    point = DesignPoint(
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
    duplicate = DesignPoint(
        "point-duplicate",
        "run-1",
        "issue-1",
        "不应覆盖",
        "不应覆盖",
        "positive",
        "P3",
        "draft",
        False,
        NOW,
        NOW,
    )

    designs.upsert_review(first_review)
    designs.upsert_review(updated_review)
    created = designs.create_test_point(point)
    repeated = designs.create_test_point(duplicate)

    assert designs.list_reviews("run-1") == [updated_review]
    assert created.id == repeated.id == "point-1"
    assert designs.list_test_points("missing") == []

    saved = designs.update_test_point(
        DesignPoint(
            point.id,
            point.run_id,
            point.source_issue_id,
            "验证退款期限边界",
            point.objective,
            "boundary",
            "P0",
            "confirmed",
            True,
            point.created_at,
            NOW,
        )
    )
    assert saved.priority == "P0"
    assert designs.list_test_points("run-1")[0].automation_candidate is True

    case = DesignCase(
        "case-1",
        "run-1",
        "point-1",
        "验证退款期限",
        ("退款服务可用",),
        "P0",
        ("退款", "边界"),
        "manual",
        "draft",
        (DesignCaseStep("step-1", 1, "提交退款", "退款完成"),),
        NOW,
        NOW,
    )
    created_case = designs.create_test_case(case)
    repeated_case = designs.create_test_case(
        DesignCase(
            "case-duplicate",
            "run-1",
            "point-1",
            "不应覆盖",
            (),
            "P3",
            (),
            "manual",
            "draft",
            (DesignCaseStep("step-x", 1, "不应覆盖", "不应覆盖"),),
            NOW,
            NOW,
        )
    )
    assert created_case.id == repeated_case.id == "case-1"

    updated_case = designs.update_test_case(
        DesignCase(
            case.id,
            case.run_id,
            case.source_test_point_id,
            "退款 API 用例",
            ("存在订单",),
            "P0",
            ("api",),
            "api",
            "draft",
            (
                DesignCaseStep("step-1", 1, "提交退款", "申请成功"),
                DesignCaseStep("step-2", 2, "查询退款", "退款完成"),
            ),
            case.created_at,
            NOW,
        )
    )
    assert len(updated_case.steps) == 2
    assert updated_case.steps[1].ordinal == 2

    assert (
        designs.update_test_case_statuses("run-1", ("case-1", "missing"), "confirmed", NOW) is None
    )
    assert designs.list_test_cases("run-1")[0].status == "draft"
    confirmed = designs.update_test_case_statuses("run-1", ("case-1",), "confirmed", NOW)
    assert confirmed is not None
    assert confirmed[0].status == "confirmed"
