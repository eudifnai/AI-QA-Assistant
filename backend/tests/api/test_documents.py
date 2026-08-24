from datetime import UTC, datetime
from typing import NoReturn

from fastapi.testclient import TestClient

from backend.app.application.documents import DocumentUseCases
from backend.app.domain.document import (
    DocumentChunk,
    DocumentImport,
    DocumentImportResult,
    DocumentItem,
    DocumentJob,
    DocumentVersion,
)
from backend.app.main import create_app

NOW = datetime(2026, 8, 10, 3, 0, tzinfo=UTC)
JOB = DocumentJob("job-1", "version-1", "queued", 0, None, None, NOW, None, None)
VERSION = DocumentVersion(
    "version-1", "document-1", 1, "a" * 64, 120, "queued", None, None, None, NOW
)
DOCUMENT = DocumentItem(
    "document-1", "workspace-1", "requirements.md", "requirements.md", NOW, NOW, VERSION, JOB
)
CHUNK = DocumentChunk("chunk-1", "version-1", 1, "lines", 1, 2, 0, 12, "# 需求\n必须退款")


class StubDocuments(DocumentUseCases):
    def list_documents(self, workspace_id: str) -> list[DocumentItem]:
        return [DOCUMENT]

    def get_document(self, workspace_id: str, document_id: str) -> DocumentItem:
        return DOCUMENT

    def import_document(self, workspace_id: str, source_path: str) -> DocumentImport:
        return DocumentImport(DOCUMENT, VERSION, JOB)

    def import_documents(
        self, workspace_id: str, source_paths: list[str]
    ) -> list[DocumentImportResult]:
        return [
            DocumentImportResult(source_paths[0], DOCUMENT, None, None),
            DocumentImportResult(
                source_paths[1],
                None,
                "DOCUMENT_FORMAT_UNSUPPORTED",
                "当前仅支持 Markdown、TXT、DOCX 和 PDF 文件。",
            ),
        ]

    def cancel_job(self, job_id: str) -> DocumentItem:
        return DOCUMENT

    def list_document_chunks(self, workspace_id: str, document_id: str) -> list[DocumentChunk]:
        return [CHUNK]


class CrashingDocuments(StubDocuments):
    def list_documents(self, workspace_id: str) -> NoReturn:
        raise RuntimeError("sensitive worker detail")

    def import_documents(self, workspace_id: str, source_paths: list[str]) -> NoReturn:
        raise RuntimeError("sensitive batch detail")


def test_document_import_list_preview_and_cancel_api() -> None:
    app = create_app(document_service=StubDocuments())
    with TestClient(app) as client:
        created = client.post(
            "/api/workspaces/workspace-1/documents",
            json={"source_path": "C:/qa/pay/requirements.md"},
        )
        listed = client.get("/api/workspaces/workspace-1/documents")
        preview = client.get("/api/workspaces/workspace-1/documents/document-1")
        chunks = client.get("/api/workspaces/workspace-1/documents/document-1/chunks")
        cancelled = client.post("/api/document-jobs/job-1/cancel")

    assert created.status_code == 202
    assert created.json()["job"]["status"] == "queued"
    assert listed.json()[0]["latest_version"]["sha256"] == "a" * 64
    assert preview.status_code == 200
    assert chunks.status_code == 200
    assert chunks.json() == [
        {
            "id": "chunk-1",
            "ordinal": 1,
            "source_type": "lines",
            "source_start": 1,
            "source_end": 2,
            "start_offset": 0,
            "end_offset": 12,
            "text": "# 需求\n必须退款",
            "locator": "第 1-2 行",
        }
    ]
    assert cancelled.status_code == 200


def test_document_import_validates_request_and_redacts_unexpected_failure() -> None:
    app = create_app(document_service=CrashingDocuments())
    with TestClient(app, raise_server_exceptions=False) as client:
        invalid = client.post("/api/workspaces/workspace-1/documents", json={"source_path": ""})
        crashed = client.get("/api/workspaces/workspace-1/documents")

    assert invalid.status_code == 422
    assert crashed.status_code == 500
    assert "sensitive worker detail" not in crashed.text


def test_batch_document_import_returns_per_file_results() -> None:
    app = create_app(document_service=StubDocuments())
    with TestClient(app) as client:
        response = client.post(
            "/api/workspaces/workspace-1/documents/batch",
            json={"source_paths": ["C:/qa/pay/requirements.md", "C:/qa/pay/unsupported.rtf"]},
        )

    assert response.status_code == 207
    payload = response.json()
    assert payload[0]["status"] == "accepted"
    assert payload[0]["document"]["job"]["status"] == "queued"
    assert payload[1] == {
        "source_path": "C:/qa/pay/unsupported.rtf",
        "status": "rejected",
        "document": None,
        "error_code": "DOCUMENT_FORMAT_UNSUPPORTED",
        "error_message": "当前仅支持 Markdown、TXT、DOCX 和 PDF 文件。",
    }


def test_batch_document_import_validates_size_and_redacts_crash() -> None:
    app = create_app(document_service=CrashingDocuments())
    with TestClient(app, raise_server_exceptions=False) as client:
        empty = client.post(
            "/api/workspaces/workspace-1/documents/batch", json={"source_paths": []}
        )
        too_many = client.post(
            "/api/workspaces/workspace-1/documents/batch",
            json={"source_paths": [f"C:/qa/pay/{index}.md" for index in range(51)]},
        )
        crashed = client.post(
            "/api/workspaces/workspace-1/documents/batch",
            json={"source_paths": ["C:/qa/pay/requirements.md"]},
        )

    assert empty.status_code == 422
    assert too_many.status_code == 422
    assert crashed.status_code == 500
    assert "sensitive batch detail" not in crashed.text
