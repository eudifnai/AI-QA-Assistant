from fastapi import APIRouter, status

from backend.app.application.documents import DocumentUseCases
from backend.app.schemas.documents import (
    DocumentBatchImportRequest,
    DocumentChunkResponse,
    DocumentImportRequest,
    DocumentImportResultResponse,
    DocumentResponse,
)


def create_document_router(service: DocumentUseCases) -> APIRouter:
    router = APIRouter(tags=["documents"])

    @router.get(
        "/api/workspaces/{workspace_id}/documents",
        response_model=list[DocumentResponse],
    )
    def list_documents(workspace_id: str) -> list[DocumentResponse]:
        return [DocumentResponse.from_domain(item) for item in service.list_documents(workspace_id)]

    @router.post(
        "/api/workspaces/{workspace_id}/documents",
        response_model=DocumentResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def import_document(workspace_id: str, payload: DocumentImportRequest) -> DocumentResponse:
        return DocumentResponse.from_domain(
            service.import_document(workspace_id, payload.source_path).document
        )

    @router.post(
        "/api/workspaces/{workspace_id}/documents/batch",
        response_model=list[DocumentImportResultResponse],
        status_code=status.HTTP_207_MULTI_STATUS,
    )
    def import_documents(
        workspace_id: str, payload: DocumentBatchImportRequest
    ) -> list[DocumentImportResultResponse]:
        return [
            DocumentImportResultResponse.from_domain(result)
            for result in service.import_documents(workspace_id, payload.source_paths)
        ]

    @router.get(
        "/api/workspaces/{workspace_id}/documents/{document_id}",
        response_model=DocumentResponse,
    )
    def get_document(workspace_id: str, document_id: str) -> DocumentResponse:
        return DocumentResponse.from_domain(service.get_document(workspace_id, document_id))

    @router.get(
        "/api/workspaces/{workspace_id}/documents/{document_id}/chunks",
        response_model=list[DocumentChunkResponse],
    )
    def list_document_chunks(workspace_id: str, document_id: str) -> list[DocumentChunkResponse]:
        return [
            DocumentChunkResponse.from_domain(chunk)
            for chunk in service.list_document_chunks(workspace_id, document_id)
        ]

    @router.post("/api/document-jobs/{job_id}/cancel", response_model=DocumentResponse)
    def cancel_document_job(job_id: str) -> DocumentResponse:
        return DocumentResponse.from_domain(service.cancel_job(job_id))

    return router
