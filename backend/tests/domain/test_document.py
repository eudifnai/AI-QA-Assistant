from datetime import UTC, datetime

from backend.app.domain.document import TERMINAL_DOCUMENT_STATUSES, DocumentJob


def test_document_job_only_allows_cancellation_before_terminal_state() -> None:
    now = datetime(2026, 8, 10, tzinfo=UTC)
    queued = DocumentJob(
        id="job-1",
        version_id="version-1",
        status="queued",
        progress=0,
        error_code=None,
        error_message=None,
        created_at=now,
        started_at=None,
        finished_at=None,
    )

    assert queued.can_cancel is True
    assert queued.status not in TERMINAL_DOCUMENT_STATUSES
    assert all(
        DocumentJob(
            id="job-1",
            version_id="version-1",
            status=status,
            progress=100,
            error_code=None,
            error_message=None,
            created_at=now,
            started_at=now,
            finished_at=now,
        ).can_cancel
        is False
        for status in TERMINAL_DOCUMENT_STATUSES
    )
