from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain.proto_asset import (
    ProtoAsset,
    ProtoDecodeResult,
    ProtoEncodeResult,
    ProtoEnum,
    ProtoEnumValue,
    ProtoField,
    ProtoMessage,
    ProtoMethod,
    ProtoService,
)

SHA256_PATTERN = r"^[0-9a-f]{64}$"
MESSAGE_TYPE_PATTERN = r"^[A-Za-z_][A-Za-z0-9_.]{0,254}$"


class ProtoImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_path: str = Field(min_length=1, max_length=32767)


class ProtoFieldResponse(BaseModel):
    name: str
    number: int
    type: str
    label: str
    type_name: str | None

    @classmethod
    def from_domain(cls, field: ProtoField) -> "ProtoFieldResponse":
        return cls(**{name: getattr(field, name) for name in cls.model_fields})


class ProtoMessageResponse(BaseModel):
    name: str
    full_name: str
    fields: list[ProtoFieldResponse]

    @classmethod
    def from_domain(cls, item: ProtoMessage) -> "ProtoMessageResponse":
        return cls(
            name=item.name,
            full_name=item.full_name,
            fields=[ProtoFieldResponse.from_domain(field) for field in item.fields],
        )


class ProtoEnumValueResponse(BaseModel):
    name: str
    number: int

    @classmethod
    def from_domain(cls, item: ProtoEnumValue) -> "ProtoEnumValueResponse":
        return cls(name=item.name, number=item.number)


class ProtoEnumResponse(BaseModel):
    name: str
    full_name: str
    values: list[ProtoEnumValueResponse]

    @classmethod
    def from_domain(cls, item: ProtoEnum) -> "ProtoEnumResponse":
        return cls(
            name=item.name,
            full_name=item.full_name,
            values=[ProtoEnumValueResponse.from_domain(value) for value in item.values],
        )


class ProtoMethodResponse(BaseModel):
    name: str
    input_type: str
    output_type: str
    client_streaming: bool
    server_streaming: bool

    @classmethod
    def from_domain(cls, item: ProtoMethod) -> "ProtoMethodResponse":
        return cls(**{name: getattr(item, name) for name in cls.model_fields})


class ProtoServiceResponse(BaseModel):
    name: str
    full_name: str
    methods: list[ProtoMethodResponse]

    @classmethod
    def from_domain(cls, item: ProtoService) -> "ProtoServiceResponse":
        return cls(
            name=item.name,
            full_name=item.full_name,
            methods=[ProtoMethodResponse.from_domain(method) for method in item.methods],
        )


class ProtoAssetResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    relative_path: str
    sha256: str
    size_bytes: int
    packages: list[str]
    messages: list[ProtoMessageResponse]
    enums: list[ProtoEnumResponse]
    services: list[ProtoServiceResponse]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, asset: ProtoAsset) -> "ProtoAssetResponse":
        return cls(
            id=asset.id,
            workspace_id=asset.workspace_id,
            name=asset.name,
            relative_path=asset.relative_path,
            sha256=asset.sha256,
            size_bytes=asset.size_bytes,
            packages=list(asset.packages),
            messages=[ProtoMessageResponse.from_domain(item) for item in asset.messages],
            enums=[ProtoEnumResponse.from_domain(item) for item in asset.enums],
            services=[ProtoServiceResponse.from_domain(item) for item in asset.services],
            created_at=asset.created_at,
            updated_at=asset.updated_at,
        )


class ProtoEncodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_sha256: str = Field(pattern=SHA256_PATTERN)
    message_type: str = Field(min_length=1, max_length=255, pattern=MESSAGE_TYPE_PATTERN)
    payload: dict[str, Any]


class ProtoDecodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_sha256: str = Field(pattern=SHA256_PATTERN)
    message_type: str = Field(min_length=1, max_length=255, pattern=MESSAGE_TYPE_PATTERN)
    data_base64: str = Field(max_length=2_796_212)


class ProtoEncodeResponse(BaseModel):
    data_base64: str
    size_bytes: int

    @classmethod
    def from_domain(cls, result: ProtoEncodeResult) -> "ProtoEncodeResponse":
        return cls(data_base64=result.data_base64, size_bytes=result.size_bytes)


class ProtoDecodeResponse(BaseModel):
    payload: dict[str, Any]
    size_bytes: int

    @classmethod
    def from_domain(cls, result: ProtoDecodeResult) -> "ProtoDecodeResponse":
        return cls(payload=result.payload, size_bytes=result.size_bytes)
