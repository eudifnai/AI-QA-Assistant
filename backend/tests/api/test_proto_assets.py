from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from backend.app.application.proto_assets import ProtoAssetUseCases
from backend.app.domain.proto_asset import (
    ProtoAsset,
    ProtoDecodeResult,
    ProtoEncodeResult,
    ProtoField,
    ProtoMessage,
)
from backend.app.main import create_app

NOW = datetime(2026, 8, 16, 8, 0, tzinfo=UTC)
ASSET = ProtoAsset(
    "asset-1",
    "workspace-1",
    "echo.proto",
    "contracts/echo.proto",
    "a" * 64,
    128,
    b"not returned",
    ("qa.echo",),
    (
        ProtoMessage(
            "EchoRequest",
            "qa.echo.EchoRequest",
            (ProtoField("text", 1, "TYPE_STRING", "LABEL_OPTIONAL", None),),
        ),
    ),
    (),
    (),
    NOW,
    NOW,
)


class StubProtoAssets(ProtoAssetUseCases):
    imported_path: str | None = None
    encode_payload: dict[str, Any] | None = None

    def list_assets(self, workspace_id: str) -> list[ProtoAsset]:
        return [ASSET]

    def get_asset(self, workspace_id: str, asset_id: str) -> ProtoAsset:
        return ASSET

    def import_asset(self, workspace_id: str, source_path: str) -> ProtoAsset:
        self.imported_path = source_path
        return ASSET

    def encode(
        self,
        workspace_id: str,
        asset_id: str,
        *,
        expected_sha256: str,
        message_type: str,
        payload: dict[str, Any],
    ) -> ProtoEncodeResult:
        self.encode_payload = payload
        return ProtoEncodeResult("CgJoaQ==", 4)

    def decode(
        self,
        workspace_id: str,
        asset_id: str,
        *,
        expected_sha256: str,
        message_type: str,
        data_base64: str,
    ) -> ProtoDecodeResult:
        return ProtoDecodeResult({"text": "hi"}, 4)


def test_proto_asset_api_imports_lists_and_round_trips_without_descriptor_bytes() -> None:
    service = StubProtoAssets()
    app = create_app(proto_asset_service=service)

    with TestClient(app) as client:
        imported = client.post(
            "/api/workspaces/workspace-1/proto-assets",
            json={"source_path": "C:/qa/contracts/echo.proto"},
        )
        listed = client.get("/api/workspaces/workspace-1/proto-assets")
        encoded = client.post(
            "/api/workspaces/workspace-1/proto-assets/asset-1/encode",
            json={
                "expected_sha256": "a" * 64,
                "message_type": "qa.echo.EchoRequest",
                "payload": {"text": "hi"},
            },
        )
        decoded = client.post(
            "/api/workspaces/workspace-1/proto-assets/asset-1/decode",
            json={
                "expected_sha256": "a" * 64,
                "message_type": "qa.echo.EchoRequest",
                "data_base64": "CgJoaQ==",
            },
        )

    assert imported.status_code == 201
    assert listed.status_code == 200
    assert encoded.json() == {"data_base64": "CgJoaQ==", "size_bytes": 4}
    assert decoded.json() == {"payload": {"text": "hi"}, "size_bytes": 4}
    assert "descriptor" not in imported.text
    assert service.imported_path == "C:/qa/contracts/echo.proto"
    assert service.encode_payload == {"text": "hi"}


def test_proto_asset_api_rejects_unknown_request_fields() -> None:
    app = create_app(proto_asset_service=StubProtoAssets())

    with TestClient(app) as client:
        response = client.post(
            "/api/workspaces/workspace-1/proto-assets",
            json={"source_path": "C:/qa/contracts/echo.proto", "descriptor_set": "secret"},
        )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
