from fastapi import APIRouter, status

from backend.app.application.proto_assets import ProtoAssetUseCases
from backend.app.schemas.proto_assets import (
    ProtoAssetResponse,
    ProtoDecodeRequest,
    ProtoDecodeResponse,
    ProtoEncodeRequest,
    ProtoEncodeResponse,
    ProtoImportRequest,
)


def create_proto_asset_router(service: ProtoAssetUseCases) -> APIRouter:
    router = APIRouter(tags=["proto-assets"])

    @router.get(
        "/api/workspaces/{workspace_id}/proto-assets",
        response_model=list[ProtoAssetResponse],
    )
    def list_assets(workspace_id: str) -> list[ProtoAssetResponse]:
        return [ProtoAssetResponse.from_domain(item) for item in service.list_assets(workspace_id)]

    @router.post(
        "/api/workspaces/{workspace_id}/proto-assets",
        response_model=ProtoAssetResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def import_asset(workspace_id: str, payload: ProtoImportRequest) -> ProtoAssetResponse:
        return ProtoAssetResponse.from_domain(
            service.import_asset(workspace_id, payload.source_path)
        )

    @router.post(
        "/api/workspaces/{workspace_id}/proto-assets/{asset_id}/encode",
        response_model=ProtoEncodeResponse,
    )
    def encode(
        workspace_id: str, asset_id: str, payload: ProtoEncodeRequest
    ) -> ProtoEncodeResponse:
        return ProtoEncodeResponse.from_domain(
            service.encode(
                workspace_id,
                asset_id,
                expected_sha256=payload.expected_sha256,
                message_type=payload.message_type,
                payload=payload.payload,
            )
        )

    @router.post(
        "/api/workspaces/{workspace_id}/proto-assets/{asset_id}/decode",
        response_model=ProtoDecodeResponse,
    )
    def decode(
        workspace_id: str, asset_id: str, payload: ProtoDecodeRequest
    ) -> ProtoDecodeResponse:
        return ProtoDecodeResponse.from_domain(
            service.decode(
                workspace_id,
                asset_id,
                expected_sha256=payload.expected_sha256,
                message_type=payload.message_type,
                data_base64=payload.data_base64,
            )
        )

    return router
