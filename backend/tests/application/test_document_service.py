from __future__ import annotations

import builtins
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.app.application.documents import DocumentService
from backend.app.core.errors import AppError
from backend.app.domain.document import (
    DocumentChunk,
    DocumentImport,
    DocumentImportResult,
    DocumentItem,
    DocumentJob,
    DocumentSource,
    DocumentStatus,
    DocumentVersion,
)
from backend.app.domain.workspace import Workspace
from backend.app.infrastructure.document_files import DocumentFileError

NOW = datetime(2026, 8, 10, 3, 0, tzinfo=UTC)
WORKSPACE = Workspace("workspace-1", "支付", "C:/qa/pay", NOW, NOW)
SOURCE = DocumentSource("requirements.md", "requirements.md", "a" * 64, 120)


def imported(status: DocumentStatus = "queued") -> DocumentImport:
    job = DocumentJob("job-1", "version-1", status, 0, None, None, NOW, None, None)
    version = DocumentVersion(
        "version-1", "document-1", 1, "a" * 64, 120, status, None, None, None, NOW
    )
    document = DocumentItem(
        "document-1",
        "workspace-1",
        "requirements.md",
        "requirements.md",
        NOW,
        NOW,
        version,
        job,
    )
    return DocumentImport(document, version, job)


class WorkspaceRepository:
    def get(self, workspace_id: str) -> Workspace | None:
        return WORKSPACE if workspace_id == WORKSPACE.id else None


class DocumentRepository:
    duplicate: DocumentVersion | None = None
    value = imported()

    def list(self, workspace_id: str) -> list[DocumentItem]:
        return [self.value.document]

    def get(self, workspace_id: str, document_id: str) -> DocumentItem | None:
        return self.value.document if document_id == "document-1" else None

    def find_version_by_hash(self, workspace_id: str, sha256: str) -> DocumentVersion | None:
        return self.duplicate

    def create_import(self, **_kwargs: object) -> DocumentImport:
        return self.value

    def get_by_job(self, job_id: str) -> DocumentItem | None:
        return self.value.document if job_id == "job-1" else None

    def list_chunks(self, version_id: str) -> builtins.list[DocumentChunk]:
        return [DocumentChunk("chunk-1", version_id, 1, "lines", 1, 2, 0, 10, "需求文本")]


class Files:
    def inspect(self, workspace_path: str, source_path: str) -> DocumentSource:
        return SOURCE


class Worker:
    recovered = False
    launched = None
    cancelled = None

    def recover_interrupted(self) -> None:
        self.recovered = True

    def launch(self, request: object) -> None:
        self.launched = request

    def cancel(self, job_id: str) -> None:
        self.cancelled = job_id


def service(
    repository: DocumentRepository | None = None, files: Files | None = None
) -> DocumentService:
    return DocumentService(
        WorkspaceRepository(),
        repository or DocumentRepository(),
        files or Files(),
        Worker(),
        clock=lambda: NOW,
        id_factory=iter(["document-1", "version-1", "job-1"]).__next__,
    )


def test_import_creates_version_and_launches_worker_after_recovery() -> None:
    worker = Worker()
    documents = DocumentRepository()
    subject = DocumentService(
        WorkspaceRepository(),
        documents,
        Files(),
        worker,
        clock=lambda: NOW,
        id_factory=iter(["document-1", "version-1", "job-1"]).__next__,
    )

    result = subject.import_document("workspace-1", str(Path("C:/qa/pay/requirements.md")))

    assert result.job.status == "queued"
    assert worker.recovered is True
    assert worker.launched is not None


def test_import_rejects_duplicate_hash() -> None:
    repository = DocumentRepository()
    repository.duplicate = imported().version

    with pytest.raises(AppError) as raised:
        service(repository).import_document("workspace-1", "C:/qa/pay/requirements.md")

    assert raised.value.code == "DOCUMENT_DUPLICATE"
    assert raised.value.status_code == 409


def test_batch_import_continues_after_a_business_failure() -> None:
    class BatchFiles(Files):
        def inspect(self, workspace_path: str, source_path: str) -> DocumentSource:
            if source_path.endswith("unsupported.rtf"):
                raise DocumentFileError("unsupported_format")
            return SOURCE

    worker = Worker()
    subject = DocumentService(
        WorkspaceRepository(),
        DocumentRepository(),
        BatchFiles(),
        worker,
        clock=lambda: NOW,
        id_factory=iter(["document-1", "version-1", "job-1"]).__next__,
    )

    results = subject.import_documents(
        "workspace-1",
        ["C:/qa/pay/requirements.md", "C:/qa/pay/unsupported.rtf"],
    )

    assert all(isinstance(result, DocumentImportResult) for result in results)
    assert results[0].document is not None
    assert results[0].error_code is None
    assert results[1].document is None
    assert results[1].error_code == "DOCUMENT_FORMAT_UNSUPPORTED"
    assert worker.launched is not None


def test_batch_import_validates_workspace_before_processing_files() -> None:
    with pytest.raises(AppError) as raised:
        service().import_documents("missing", ["C:/qa/pay/requirements.md"])

    assert raised.value.code == "WORKSPACE_NOT_FOUND"


@pytest.mark.parametrize(
    ("reason", "code", "status"),
    [
        ("unsupported_format", "DOCUMENT_FORMAT_UNSUPPORTED", 415),
        ("file_too_large", "DOCUMENT_TOO_LARGE", 413),
        ("path_outside_workspace", "DOCUMENT_PATH_OUTSIDE_WORKSPACE", 400),
        ("file_not_found", "DOCUMENT_FILE_NOT_FOUND", 404),
    ],
)
def test_import_maps_file_failures(reason: str, code: str, status: int) -> None:
    class FailingFiles(Files):
        def inspect(self, workspace_path: str, source_path: str) -> DocumentSource:
            raise DocumentFileError(reason)

    with pytest.raises(AppError) as raised:
        service(files=FailingFiles()).import_document("workspace-1", "C:/qa/pay/input.md")

    assert raised.value.code == code
    assert raised.value.status_code == status


def test_cancel_rejects_terminal_job() -> None:
    repository = DocumentRepository()
    repository.value = imported("passed")

    with pytest.raises(AppError) as raised:
        service(repository).cancel_job("job-1")

    assert raised.value.code == "DOCUMENT_JOB_FINISHED"


def test_lists_chunks_only_after_document_scope_check() -> None:
    subject = service()

    chunks = subject.list_document_chunks("workspace-1", "document-1")

    assert chunks[0].id == "chunk-1"
    with pytest.raises(AppError) as raised:
        subject.list_document_chunks("workspace-1", "missing")
    assert raised.value.code == "DOCUMENT_NOT_FOUND"


def test_interrupted_job_recovery_runs_once_under_concurrent_requests() -> None:
    class CountingWorker(Worker):
        calls = 0

        def recover_interrupted(self) -> None:
            time.sleep(0.02)
            self.calls += 1

    worker = CountingWorker()
    subject = DocumentService(WorkspaceRepository(), DocumentRepository(), Files(), worker)

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(subject.list_documents, ["workspace-1"] * 4))

    assert all(len(items) == 1 for items in results)
    assert worker.calls == 1
