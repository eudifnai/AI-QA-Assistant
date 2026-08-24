from __future__ import annotations

import builtins
from collections.abc import Callable
from datetime import UTC, datetime
from threading import Lock
from typing import Protocol
from uuid import uuid4

from backend.app.core.errors import AppError
from backend.app.domain.document import (
    DocumentChunk,
    DocumentConflictError,
    DocumentImport,
    DocumentImportResult,
    DocumentItem,
    DocumentParseRequest,
    DocumentSource,
    DocumentVersion,
)
from backend.app.domain.workspace import Workspace
from backend.app.infrastructure.document_files import DocumentFileError


class WorkspaceReader(Protocol):
    def get(self, workspace_id: str) -> Workspace | None: ...


class DocumentRepository(Protocol):
    def list(self, workspace_id: str) -> list[DocumentItem]: ...

    def get(self, workspace_id: str, document_id: str) -> DocumentItem | None: ...

    def find_version_by_hash(self, workspace_id: str, sha256: str) -> DocumentVersion | None: ...

    def create_import(
        self,
        *,
        document_id: str,
        version_id: str,
        job_id: str,
        workspace_id: str,
        source: DocumentSource,
        created_at: datetime,
    ) -> DocumentImport: ...

    def get_by_job(self, job_id: str) -> DocumentItem | None: ...

    def list_chunks(self, version_id: str) -> builtins.list[DocumentChunk]: ...


class DocumentFiles(Protocol):
    def inspect(self, workspace_path: str, source_path: str) -> DocumentSource: ...


class DocumentWorker(Protocol):
    def recover_interrupted(self) -> None: ...

    def launch(self, request: DocumentParseRequest) -> None: ...

    def cancel(self, job_id: str) -> None: ...


class DocumentUseCases(Protocol):
    def list_documents(self, workspace_id: str) -> list[DocumentItem]: ...

    def get_document(self, workspace_id: str, document_id: str) -> DocumentItem: ...

    def list_document_chunks(self, workspace_id: str, document_id: str) -> list[DocumentChunk]: ...

    def import_document(self, workspace_id: str, source_path: str) -> DocumentImport: ...

    def import_documents(
        self, workspace_id: str, source_paths: list[str]
    ) -> list[DocumentImportResult]: ...

    def cancel_job(self, job_id: str) -> DocumentItem: ...


class DocumentService:
    def __init__(
        self,
        workspaces: WorkspaceReader,
        documents: DocumentRepository,
        files: DocumentFiles,
        worker: DocumentWorker,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._workspaces = workspaces
        self._documents = documents
        self._files = files
        self._worker = worker
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))
        self._recovered = False
        self._recovery_lock = Lock()

    def list_documents(self, workspace_id: str) -> list[DocumentItem]:
        self._workspace(workspace_id)
        self._ensure_recovered()
        return self._documents.list(workspace_id)

    def get_document(self, workspace_id: str, document_id: str) -> DocumentItem:
        self._workspace(workspace_id)
        self._ensure_recovered()
        document = self._documents.get(workspace_id, document_id)
        if document is None:
            raise AppError(code="DOCUMENT_NOT_FOUND", message="未找到该文档。", status_code=404)
        return document

    def list_document_chunks(self, workspace_id: str, document_id: str) -> list[DocumentChunk]:
        document = self.get_document(workspace_id, document_id)
        return self._documents.list_chunks(document.latest_version.id)

    def import_document(self, workspace_id: str, source_path: str) -> DocumentImport:
        workspace = self._workspace(workspace_id)
        self._ensure_recovered()
        return self._import_document(workspace, source_path)

    def import_documents(
        self, workspace_id: str, source_paths: list[str]
    ) -> list[DocumentImportResult]:
        workspace = self._workspace(workspace_id)
        self._ensure_recovered()
        results: list[DocumentImportResult] = []
        for source_path in source_paths:
            try:
                imported = self._import_document(workspace, source_path)
            except AppError as exception:
                results.append(
                    DocumentImportResult(
                        source_path,
                        None,
                        exception.code,
                        exception.message,
                    )
                )
            else:
                results.append(
                    DocumentImportResult(
                        source_path,
                        imported.document,
                        None,
                        None,
                    )
                )
        return results

    def _import_document(self, workspace: Workspace, source_path: str) -> DocumentImport:
        try:
            source = self._files.inspect(workspace.path, source_path)
        except DocumentFileError as exception:
            raise self._file_error(exception.reason) from exception
        if self._documents.find_version_by_hash(workspace.id, source.sha256) is not None:
            raise AppError(
                code="DOCUMENT_DUPLICATE",
                message="该文件内容已导入当前工作空间。",
                status_code=409,
            )
        try:
            imported = self._documents.create_import(
                document_id=self._id_factory(),
                version_id=self._id_factory(),
                job_id=self._id_factory(),
                workspace_id=workspace.id,
                source=source,
                created_at=self._clock(),
            )
        except DocumentConflictError as exception:
            raise AppError(
                code="DOCUMENT_DUPLICATE",
                message="该文件内容已导入当前工作空间。",
                status_code=409,
            ) from exception
        self._worker.launch(
            DocumentParseRequest(
                job_id=imported.job.id,
                workspace_path=workspace.path,
                relative_path=source.relative_path,
                expected_sha256=source.sha256,
            )
        )
        return imported

    def cancel_job(self, job_id: str) -> DocumentItem:
        self._ensure_recovered()
        document = self._documents.get_by_job(job_id)
        if document is None:
            raise AppError(
                code="DOCUMENT_JOB_NOT_FOUND", message="未找到该解析任务。", status_code=404
            )
        if not document.job.can_cancel:
            raise AppError(
                code="DOCUMENT_JOB_FINISHED",
                message="该解析任务已经结束。",
                status_code=409,
            )
        self._worker.cancel(job_id)
        return self._documents.get_by_job(job_id) or document

    def _ensure_recovered(self) -> None:
        if self._recovered:
            return
        with self._recovery_lock:
            if not self._recovered:
                self._worker.recover_interrupted()
                self._recovered = True

    def _workspace(self, workspace_id: str) -> Workspace:
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise AppError(
                code="WORKSPACE_NOT_FOUND", message="未找到该工作空间。", status_code=404
            )
        return workspace

    @staticmethod
    def _file_error(reason: str) -> AppError:
        errors = {
            "unsupported_format": (
                "DOCUMENT_FORMAT_UNSUPPORTED",
                "当前仅支持 Markdown、TXT、DOCX 和 PDF 文件。",
                415,
            ),
            "file_too_large": ("DOCUMENT_TOO_LARGE", "文档超过允许的大小。", 413),
            "path_outside_workspace": (
                "DOCUMENT_PATH_OUTSIDE_WORKSPACE",
                "只能导入当前工作空间内的文件。",
                400,
            ),
            "file_not_found": ("DOCUMENT_FILE_NOT_FOUND", "未找到要导入的文件。", 404),
            "path_invalid": ("DOCUMENT_PATH_INVALID", "文档路径必须是本机绝对路径。", 400),
        }
        code, message, status = errors.get(
            reason,
            ("DOCUMENT_FILE_UNAVAILABLE", "无法读取要导入的文件。", 400),
        )
        return AppError(code=code, message=message, status_code=status)
