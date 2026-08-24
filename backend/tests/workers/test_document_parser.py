import hashlib
import time
from datetime import UTC, datetime
from pathlib import Path

from docx import Document
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, select

from backend.app.domain.document import DocumentParseRequest, DocumentSource
from backend.app.infrastructure.database import create_database_engine
from backend.app.infrastructure.documents import (
    DocumentRecord,
    SqlModelDocumentRepository,
)
from backend.app.infrastructure.workspaces import WorkspaceRecord
from backend.app.workers.document_parser import DocumentParseWorkerManager

NOW = datetime(2026, 8, 10, 3, 0, tzinfo=UTC)


def setup_database(database_path: Path, workspace_path: Path) -> tuple[Engine, str]:
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_database_engine(database_url)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            WorkspaceRecord(
                id="workspace-1",
                name="支付",
                name_key="支付",
                path=str(workspace_path),
                path_key=str(workspace_path).casefold(),
                created_at=NOW,
                last_opened_at=NOW,
            )
        )
        session.commit()
    return engine, database_url


def create_job(
    repository: SqlModelDocumentRepository,
    *,
    suffix: str,
    sha256: str,
) -> str:
    imported = repository.create_import(
        document_id=f"document-{suffix}",
        version_id=f"version-{suffix}",
        job_id=f"job-{suffix}",
        workspace_id="workspace-1",
        source=DocumentSource(f"{suffix}.md", f"{suffix}.md", sha256, 20),
        created_at=NOW,
    )
    return imported.job.id


def create_file_job(
    repository: SqlModelDocumentRepository,
    *,
    file_name: str,
    sha256: str,
) -> str:
    key = file_name.replace(".", "-")
    imported = repository.create_import(
        document_id=f"document-{key}",
        version_id=f"version-{key}",
        job_id=f"job-{key}",
        workspace_id="workspace-1",
        source=DocumentSource(file_name, file_name, sha256, 20),
        created_at=NOW,
    )
    return imported.job.id


def wait_for_terminal(repository: SqlModelDocumentRepository, job_id: str) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        item = repository.get_by_job(job_id)
        if item is not None and item.job.status in {"passed", "failed", "error", "timeout"}:
            return
        time.sleep(0.05)


def test_independent_worker_process_parses_utf8_document(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = workspace / "requirements.md"
    source.write_bytes("# 需求\n必须支持退款".encode())
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    engine, database_url = setup_database(tmp_path / "worker.db", workspace)
    repository = SqlModelDocumentRepository(engine)
    job_id = create_job(repository, suffix="requirements", sha256=digest)
    manager = DocumentParseWorkerManager(
        repository,
        database_url=database_url,
        max_bytes=1024,
        timeout_seconds=10,
    )

    manager.launch(DocumentParseRequest(job_id, str(workspace), "requirements.md", digest))
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        item = repository.get_by_job(job_id)
        if item is not None and item.job.status == "passed":
            break
        time.sleep(0.05)

    item = repository.get_by_job(job_id)
    assert item is not None
    assert item.job.status == "passed"
    assert item.job.progress == 100
    assert item.latest_version.parsed_text == "# 需求\n必须支持退款"
    chunks = repository.list_chunks(item.latest_version.id)
    assert len(chunks) == 1
    assert chunks[0].source_type == "lines"
    assert chunks[0].source_start == 1
    assert chunks[0].source_end == 2
    assert chunks[0].text == "# 需求\n必须支持退款"


def test_independent_worker_process_parses_docx_and_reports_corrupt_pdf(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    docx_source = workspace / "requirements.docx"
    document = Document()
    document.add_paragraph("系统必须支持退款。")
    document.save(str(docx_source))
    corrupt_pdf = workspace / "damaged.pdf"
    corrupt_pdf.write_bytes(b"not-a-pdf")
    engine, database_url = setup_database(tmp_path / "binary-worker.db", workspace)
    repository = SqlModelDocumentRepository(engine)
    manager = DocumentParseWorkerManager(
        repository,
        database_url=database_url,
        max_bytes=1024 * 1024,
        timeout_seconds=10,
    )

    docx_digest = hashlib.sha256(docx_source.read_bytes()).hexdigest()
    docx_job = create_file_job(repository, file_name=docx_source.name, sha256=docx_digest)
    manager.launch(DocumentParseRequest(docx_job, str(workspace), docx_source.name, docx_digest))
    wait_for_terminal(repository, docx_job)

    pdf_digest = hashlib.sha256(corrupt_pdf.read_bytes()).hexdigest()
    pdf_job = create_file_job(repository, file_name=corrupt_pdf.name, sha256=pdf_digest)
    manager.launch(DocumentParseRequest(pdf_job, str(workspace), corrupt_pdf.name, pdf_digest))
    wait_for_terminal(repository, pdf_job)

    parsed = repository.get_by_job(docx_job)
    failed = repository.get_by_job(pdf_job)
    assert parsed is not None
    assert parsed.job.status == "passed"
    assert parsed.latest_version.parsed_text == "系统必须支持退款。"
    assert repository.list_chunks(parsed.latest_version.id)[0].source_type == "block"
    assert failed is not None
    assert failed.job.status == "failed"
    assert failed.job.error_code == "DOCUMENT_CORRUPT"


def test_repository_covers_failure_cancel_timeout_crash_and_recovery(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    engine, _ = setup_database(tmp_path / "states.db", workspace)
    repository = SqlModelDocumentRepository(engine)

    failed = create_job(repository, suffix="failed", sha256="1" * 64)
    cancelled = create_job(repository, suffix="cancelled", sha256="2" * 64)
    timed_out = create_job(repository, suffix="timeout", sha256="3" * 64)
    crashed = create_job(repository, suffix="crashed", sha256="4" * 64)
    interrupted = create_job(repository, suffix="interrupted", sha256="5" * 64)

    repository.mark_running(failed, pid=101, now=NOW)
    assert repository.get_by_job(failed).job.progress == 10  # type: ignore[union-attr]
    repository.mark_failed(failed, code="PARSE_FAILED", message="解析失败。", now=NOW)
    repository.mark_cancelled(cancelled, now=NOW)
    repository.mark_timeout(timed_out, now=NOW)
    repository.mark_error(crashed, code="WORKER_CRASHED", message="进程退出。", now=NOW)
    repository.mark_running(interrupted, pid=202, now=NOW)
    repository.recover_interrupted(now=NOW)

    expected = {
        failed: "failed",
        cancelled: "cancelled",
        timed_out: "timeout",
        crashed: "error",
        interrupted: "error",
    }
    for job_id, status in expected.items():
        item = repository.get_by_job(job_id)
        assert item is not None
        assert item.job.status == status
        assert item.job.finished_at is not None

    assert repository.get_by_job(interrupted).job.error_code == "DOCUMENT_WORKER_INTERRUPTED"  # type: ignore[union-attr]


def test_modified_source_creates_next_version(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    engine, _ = setup_database(tmp_path / "versions.db", workspace)
    repository = SqlModelDocumentRepository(engine)

    first = repository.create_import(
        document_id="document-1",
        version_id="version-1",
        job_id="job-1",
        workspace_id="workspace-1",
        source=DocumentSource("requirements.md", "requirements.md", "a" * 64, 10),
        created_at=NOW,
    )
    second = repository.create_import(
        document_id="unused-document-id",
        version_id="version-2",
        job_id="job-2",
        workspace_id="workspace-1",
        source=DocumentSource("requirements.md", "requirements.md", "b" * 64, 20),
        created_at=NOW,
    )

    assert second.document.id == first.document.id
    assert second.version.version_number == 2
    with Session(engine) as session:
        assert len(session.exec(select(DocumentRecord)).all()) == 1
