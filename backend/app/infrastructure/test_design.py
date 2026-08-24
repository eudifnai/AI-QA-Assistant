import json
from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, delete
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Field, Session, SQLModel, col, select

from backend.app.domain.test_design import (
    IssueReview,
    TestCase,
    TestCaseBatchStatus,
    TestCaseStep,
    TestPoint,
)
from backend.app.infrastructure.analysis import (
    AnalysisIssueRecord,  # noqa: F401
    AnalysisRunRecord,  # noqa: F401
)


class IssueReviewRecord(SQLModel, table=True):
    __tablename__ = "analysis_issue_reviews"
    __table_args__ = (
        Index("ix_analysis_issue_reviews_run", "run_id"),
        Index("uq_analysis_issue_reviews_issue", "issue_id", unique=True),
    )

    id: str = Field(sa_column=Column(String(36), primary_key=True))
    run_id: str = Field(
        sa_column=Column(
            String(36), ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False
        )
    )
    issue_id: str = Field(
        sa_column=Column(
            String(36), ForeignKey("analysis_issues.id", ondelete="CASCADE"), nullable=False
        )
    )
    status: str = Field(sa_column=Column(String(16), nullable=False))
    answer: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class TestPointRecord(SQLModel, table=True):
    __tablename__ = "test_points"
    __table_args__ = (
        Index("ix_test_points_run_created", "run_id", "created_at"),
        Index("uq_test_points_source_issue", "source_issue_id", unique=True),
    )

    id: str = Field(sa_column=Column(String(36), primary_key=True))
    run_id: str = Field(
        sa_column=Column(
            String(36), ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False
        )
    )
    source_issue_id: str = Field(
        sa_column=Column(
            String(36), ForeignKey("analysis_issues.id", ondelete="CASCADE"), nullable=False
        )
    )
    title: str = Field(sa_column=Column(String(500), nullable=False))
    objective: str = Field(sa_column=Column(Text, nullable=False))
    test_type: str = Field(sa_column=Column(String(24), nullable=False))
    priority: str = Field(sa_column=Column(String(2), nullable=False))
    status: str = Field(sa_column=Column(String(16), nullable=False))
    automation_candidate: bool = Field(sa_column=Column(Boolean, nullable=False, default=False))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class TestCaseRecord(SQLModel, table=True):
    __tablename__ = "test_cases"
    __table_args__ = (
        Index("ix_test_cases_run_created", "run_id", "created_at"),
        Index("uq_test_cases_source_point", "source_test_point_id", unique=True),
    )

    id: str = Field(sa_column=Column(String(36), primary_key=True))
    run_id: str = Field(
        sa_column=Column(
            String(36), ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False
        )
    )
    source_test_point_id: str = Field(
        sa_column=Column(
            String(36), ForeignKey("test_points.id", ondelete="CASCADE"), nullable=False
        )
    )
    title: str = Field(sa_column=Column(String(500), nullable=False))
    preconditions_json: str = Field(sa_column=Column(Text, nullable=False))
    priority: str = Field(sa_column=Column(String(2), nullable=False))
    tags_json: str = Field(sa_column=Column(Text, nullable=False))
    automation_type: str = Field(sa_column=Column(String(16), nullable=False))
    status: str = Field(sa_column=Column(String(16), nullable=False))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class TestCaseStepRecord(SQLModel, table=True):
    __tablename__ = "test_case_steps"
    __table_args__ = (
        Index("uq_test_case_steps_case_ordinal", "test_case_id", "ordinal", unique=True),
    )

    id: str = Field(sa_column=Column(String(36), primary_key=True))
    test_case_id: str = Field(
        sa_column=Column(
            String(36), ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False
        )
    )
    ordinal: int = Field(sa_column=Column(Integer, nullable=False))
    action: str = Field(sa_column=Column(Text, nullable=False))
    expected_result: str = Field(sa_column=Column(Text, nullable=False))


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class SqlModelTestDesignRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_reviews(self, run_id: str) -> list[IssueReview]:
        with Session(self._engine) as session:
            rows = session.exec(
                select(IssueReviewRecord)
                .where(IssueReviewRecord.run_id == run_id)
                .order_by(col(IssueReviewRecord.created_at), col(IssueReviewRecord.id))
            ).all()
            return [self._review(row) for row in rows]

    def upsert_review(self, review: IssueReview) -> IssueReview:
        with Session(self._engine) as session:
            record = session.exec(
                select(IssueReviewRecord).where(IssueReviewRecord.issue_id == review.issue_id)
            ).first()
            if record is None:
                record = IssueReviewRecord(
                    id=review.id,
                    run_id=review.run_id,
                    issue_id=review.issue_id,
                    status=review.status,
                    answer=review.answer,
                    created_at=review.created_at,
                    updated_at=review.updated_at,
                )
            else:
                record.status = review.status
                record.answer = review.answer
                record.updated_at = review.updated_at
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._review(record)

    def list_test_points(self, run_id: str) -> list[TestPoint]:
        with Session(self._engine) as session:
            rows = session.exec(
                select(TestPointRecord)
                .where(TestPointRecord.run_id == run_id)
                .order_by(col(TestPointRecord.created_at), col(TestPointRecord.id))
            ).all()
            return [self._point(row) for row in rows]

    def create_test_point(self, point: TestPoint) -> TestPoint:
        with Session(self._engine) as session:
            existing = session.exec(
                select(TestPointRecord).where(
                    TestPointRecord.source_issue_id == point.source_issue_id
                )
            ).first()
            if existing is not None:
                return self._point(existing)
            session.add(self._point_record(point))
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
            existing = session.exec(
                select(TestPointRecord).where(
                    TestPointRecord.source_issue_id == point.source_issue_id
                )
            ).first()
            if existing is None:
                raise RuntimeError("test point was not persisted")
            return self._point(existing)

    def update_test_point(self, point: TestPoint) -> TestPoint:
        with Session(self._engine) as session:
            record = session.get(TestPointRecord, point.id)
            if (
                record is None
                or record.run_id != point.run_id
                or record.source_issue_id != point.source_issue_id
            ):
                raise RuntimeError("test point was not found for update")
            record.title = point.title
            record.objective = point.objective
            record.test_type = point.test_type
            record.priority = point.priority
            record.status = point.status
            record.automation_candidate = point.automation_candidate
            record.updated_at = point.updated_at
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._point(record)

    def list_test_cases(self, run_id: str) -> list[TestCase]:
        with Session(self._engine) as session:
            rows = session.exec(
                select(TestCaseRecord)
                .where(TestCaseRecord.run_id == run_id)
                .order_by(col(TestCaseRecord.created_at), col(TestCaseRecord.id))
            ).all()
            return [self._case(session, row) for row in rows]

    def create_test_case(self, case: TestCase) -> TestCase:
        with Session(self._engine) as session:
            existing = session.exec(
                select(TestCaseRecord).where(
                    TestCaseRecord.source_test_point_id == case.source_test_point_id
                )
            ).first()
            if existing is not None:
                return self._case(session, existing)
            session.add(self._case_record(case))
            for step in case.steps:
                session.add(self._step_record(case.id, step))
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
            existing = session.exec(
                select(TestCaseRecord).where(
                    TestCaseRecord.source_test_point_id == case.source_test_point_id
                )
            ).first()
            if existing is None:
                raise RuntimeError("test case was not persisted")
            return self._case(session, existing)

    def update_test_case(self, case: TestCase) -> TestCase:
        with Session(self._engine) as session:
            record = session.get(TestCaseRecord, case.id)
            if (
                record is None
                or record.run_id != case.run_id
                or record.source_test_point_id != case.source_test_point_id
            ):
                raise RuntimeError("test case was not found for update")
            record.title = case.title
            record.preconditions_json = json.dumps(
                case.preconditions, ensure_ascii=False, separators=(",", ":")
            )
            record.priority = case.priority
            record.tags_json = json.dumps(case.tags, ensure_ascii=False, separators=(",", ":"))
            record.automation_type = case.automation_type
            record.status = case.status
            record.updated_at = case.updated_at
            session.exec(
                delete(TestCaseStepRecord).where(col(TestCaseStepRecord.test_case_id) == case.id)
            )
            session.add(record)
            for step in case.steps:
                session.add(self._step_record(case.id, step))
            session.commit()
            session.refresh(record)
            return self._case(session, record)

    def update_test_case_statuses(
        self,
        run_id: str,
        case_ids: tuple[str, ...],
        status: TestCaseBatchStatus,
        updated_at: datetime,
    ) -> list[TestCase] | None:
        with Session(self._engine) as session:
            records = session.exec(
                select(TestCaseRecord).where(
                    TestCaseRecord.run_id == run_id,
                    col(TestCaseRecord.id).in_(case_ids),
                )
            ).all()
            if len(records) != len(case_ids):
                return None
            for record in records:
                record.status = status
                record.updated_at = updated_at
                session.add(record)
            session.commit()
            return [self._case(session, record) for record in records]

    @staticmethod
    def _review(record: IssueReviewRecord) -> IssueReview:
        return IssueReview(
            record.id,
            record.run_id,
            record.issue_id,
            record.status,  # type: ignore[arg-type]
            record.answer,
            _utc(record.created_at),
            _utc(record.updated_at),
        )

    @staticmethod
    def _point(record: TestPointRecord) -> TestPoint:
        return TestPoint(
            record.id,
            record.run_id,
            record.source_issue_id,
            record.title,
            record.objective,
            record.test_type,  # type: ignore[arg-type]
            record.priority,  # type: ignore[arg-type]
            record.status,  # type: ignore[arg-type]
            record.automation_candidate,
            _utc(record.created_at),
            _utc(record.updated_at),
        )

    @staticmethod
    def _point_record(point: TestPoint) -> TestPointRecord:
        return TestPointRecord(
            id=point.id,
            run_id=point.run_id,
            source_issue_id=point.source_issue_id,
            title=point.title,
            objective=point.objective,
            test_type=point.test_type,
            priority=point.priority,
            status=point.status,
            automation_candidate=point.automation_candidate,
            created_at=point.created_at,
            updated_at=point.updated_at,
        )

    @staticmethod
    def _case(session: Session, record: TestCaseRecord) -> TestCase:
        step_rows = session.exec(
            select(TestCaseStepRecord)
            .where(TestCaseStepRecord.test_case_id == record.id)
            .order_by(col(TestCaseStepRecord.ordinal))
        ).all()
        return TestCase(
            record.id,
            record.run_id,
            record.source_test_point_id,
            record.title,
            tuple(str(item) for item in json.loads(record.preconditions_json)),
            record.priority,  # type: ignore[arg-type]
            tuple(str(item) for item in json.loads(record.tags_json)),
            record.automation_type,  # type: ignore[arg-type]
            record.status,  # type: ignore[arg-type]
            tuple(
                TestCaseStep(row.id, row.ordinal, row.action, row.expected_result)
                for row in step_rows
            ),
            _utc(record.created_at),
            _utc(record.updated_at),
        )

    @staticmethod
    def _case_record(case: TestCase) -> TestCaseRecord:
        return TestCaseRecord(
            id=case.id,
            run_id=case.run_id,
            source_test_point_id=case.source_test_point_id,
            title=case.title,
            preconditions_json=json.dumps(
                case.preconditions, ensure_ascii=False, separators=(",", ":")
            ),
            priority=case.priority,
            tags_json=json.dumps(case.tags, ensure_ascii=False, separators=(",", ":")),
            automation_type=case.automation_type,
            status=case.status,
            created_at=case.created_at,
            updated_at=case.updated_at,
        )

    @staticmethod
    def _step_record(case_id: str, step: TestCaseStep) -> TestCaseStepRecord:
        return TestCaseStepRecord(
            id=step.id,
            test_case_id=case_id,
            ordinal=step.ordinal,
            action=step.action,
            expected_result=step.expected_result,
        )
