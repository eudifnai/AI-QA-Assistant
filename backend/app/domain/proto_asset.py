from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class ProtoSource:
    name: str
    relative_path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class ProtoField:
    name: str
    number: int
    type: str
    label: str
    type_name: str | None


@dataclass(frozen=True, slots=True)
class ProtoMessage:
    name: str
    full_name: str
    fields: tuple[ProtoField, ...]


@dataclass(frozen=True, slots=True)
class ProtoEnumValue:
    name: str
    number: int


@dataclass(frozen=True, slots=True)
class ProtoEnum:
    name: str
    full_name: str
    values: tuple[ProtoEnumValue, ...]


@dataclass(frozen=True, slots=True)
class ProtoMethod:
    name: str
    input_type: str
    output_type: str
    client_streaming: bool
    server_streaming: bool


@dataclass(frozen=True, slots=True)
class ProtoService:
    name: str
    full_name: str
    methods: tuple[ProtoMethod, ...]


@dataclass(frozen=True, slots=True)
class ProtoCompileResult:
    descriptor_set: bytes
    packages: tuple[str, ...]
    messages: tuple[ProtoMessage, ...]
    enums: tuple[ProtoEnum, ...]
    services: tuple[ProtoService, ...]


@dataclass(frozen=True, slots=True)
class ProtoAsset:
    id: str
    workspace_id: str
    name: str
    relative_path: str
    sha256: str
    size_bytes: int
    descriptor_set: bytes
    packages: tuple[str, ...]
    messages: tuple[ProtoMessage, ...]
    enums: tuple[ProtoEnum, ...]
    services: tuple[ProtoService, ...]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ProtoEncodeResult:
    data_base64: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class ProtoDecodeResult:
    payload: dict[str, Any]
    size_bytes: int


class ProtoAssetConflictError(Exception):
    pass
