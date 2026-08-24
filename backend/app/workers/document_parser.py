import logging
import multiprocessing
import os
import threading
from datetime import UTC, datetime
from multiprocessing.process import BaseProcess

from backend.app.domain.document import DocumentParseRequest
from backend.app.infrastructure.database import create_database_engine
from backend.app.infrastructure.document_files import DocumentFileError, LocalDocumentFiles
from backend.app.infrastructure.document_parsers import DocumentParseError, DocumentTextParser
from backend.app.infrastructure.documents import SqlModelDocumentRepository

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


def parse_document_job(
    database_url: str,
    request: DocumentParseRequest,
    max_bytes: int,
) -> None:
    repository = SqlModelDocumentRepository(create_database_engine(database_url))
    repository.mark_running(request.job_id, pid=os.getpid(), now=_now())
    try:
        content = LocalDocumentFiles(max_bytes=max_bytes).read_bytes(
            request.workspace_path,
            request.relative_path,
            expected_sha256=request.expected_sha256,
        )
        result = DocumentTextParser().parse_document(content, request.relative_path)
    except DocumentFileError as exception:
        failures = {
            "invalid_encoding": ("DOCUMENT_ENCODING_INVALID", "文档不是有效的 UTF-8 文本。"),
            "file_changed": ("DOCUMENT_FILE_CHANGED", "文档在排队后发生变化。请重新导入。"),
        }
        code, message = failures.get(
            exception.reason,
            ("DOCUMENT_PARSE_SOURCE_UNAVAILABLE", "解析时无法读取源文件。"),
        )
        repository.mark_failed(request.job_id, code=code, message=message, now=_now())
        return
    except DocumentParseError as exception:
        failures = {
            "invalid_encoding": ("DOCUMENT_ENCODING_INVALID", "文档不是有效的 UTF-8 文本。"),
            "corrupt_document": ("DOCUMENT_CORRUPT", "文档已损坏或结构无效。"),
            "encrypted_pdf": ("DOCUMENT_PDF_ENCRYPTED", "当前不支持解析加密 PDF。"),
            "empty_text": ("DOCUMENT_TEXT_EMPTY", "文档中没有可提取文本。当前不支持 OCR。"),
            "document_too_complex": ("DOCUMENT_TOO_COMPLEX", "文档结构超过当前解析限制。"),
            "extracted_text_too_large": (
                "DOCUMENT_TEXT_TOO_LARGE",
                "文档提取文本超过当前限制。",
            ),
        }
        code, message = failures.get(
            exception.reason,
            ("DOCUMENT_PARSE_FAILED", "无法解析该文档。"),
        )
        repository.mark_failed(request.job_id, code=code, message=message, now=_now())
        return
    except Exception:
        logger.exception("Document worker failed", extra={"job_id": request.job_id})
        repository.mark_error(
            request.job_id,
            code="DOCUMENT_WORKER_ERROR",
            message="文档解析进程发生错误。",
            now=_now(),
        )
        return
    repository.mark_passed(request.job_id, result=result, now=_now())


class DocumentParseWorkerManager:
    def __init__(
        self,
        repository: SqlModelDocumentRepository,
        *,
        database_url: str,
        max_bytes: int,
        timeout_seconds: int,
    ) -> None:
        self._repository = repository
        self._database_url = database_url
        self._max_bytes = max_bytes
        self._timeout_seconds = timeout_seconds
        self._context = multiprocessing.get_context("spawn")
        self._processes: dict[str, BaseProcess] = {}
        self._lock = threading.Lock()

    def recover_interrupted(self) -> None:
        self._repository.recover_interrupted(now=_now())

    def launch(self, request: DocumentParseRequest) -> None:
        process = self._context.Process(
            target=parse_document_job,
            args=(self._database_url, request, self._max_bytes),
            daemon=True,
            name=f"document-parser-{request.job_id[:8]}",
        )
        process.start()
        with self._lock:
            self._processes[request.job_id] = process
        threading.Thread(
            target=self._supervise,
            args=(request.job_id, process),
            daemon=True,
            name=f"document-supervisor-{request.job_id[:8]}",
        ).start()

    def cancel(self, job_id: str) -> None:
        with self._lock:
            process = self._processes.pop(job_id, None)
        if process is not None and process.is_alive():
            process.terminate()
            process.join(timeout=5)
        self._repository.mark_cancelled(job_id, now=_now())

    def _supervise(self, job_id: str, process: BaseProcess) -> None:
        process.join(timeout=self._timeout_seconds)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
            self._repository.mark_timeout(job_id, now=_now())
        elif process.exitcode not in (0, None):
            self._repository.mark_error(
                job_id,
                code="DOCUMENT_WORKER_CRASHED",
                message="文档解析进程意外退出。",
                now=_now(),
            )
        with self._lock:
            if self._processes.get(job_id) is process:
                self._processes.pop(job_id, None)
