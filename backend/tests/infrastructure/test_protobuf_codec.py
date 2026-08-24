from pathlib import Path

import pytest

from backend.app.infrastructure.protobuf_codec import (
    DynamicProtobufCodec,
    GrpcToolsProtoCompiler,
    ProtoCodecError,
    ProtoCompilerError,
    build_grpc_tools_command,
)


def test_grpc_tools_command_uses_frozen_sidecar_dispatch() -> None:
    assert build_grpc_tools_command(
        executable="C:/app/ai-qa-backend.exe",
        frozen=True,
        arguments=("--version",),
    ) == ["C:/app/ai-qa-backend.exe", "--grpc-tools-protoc", "--version"]


PROTO = """syntax = "proto3";
package qa.echo;

message EchoRequest {
  string text = 1;
  int32 count = 2;
}

enum EchoMode {
  ECHO_MODE_UNSPECIFIED = 0;
  ECHO_MODE_FAST = 1;
}

service EchoService {
  rpc Echo(EchoRequest) returns (EchoRequest);
}
"""


def test_compiler_summarizes_and_codec_round_trips(tmp_path: Path) -> None:
    proto = tmp_path / "contracts" / "echo.proto"
    proto.parent.mkdir()
    proto.write_text(PROTO, encoding="utf-8")

    compiled = GrpcToolsProtoCompiler(timeout_seconds=10).compile(
        str(tmp_path), "contracts/echo.proto"
    )
    encoded = DynamicProtobufCodec().encode(
        compiled.descriptor_set,
        "qa.echo.EchoRequest",
        {"text": "hello", "count": 2},
    )
    decoded = DynamicProtobufCodec().decode(
        compiled.descriptor_set,
        "qa.echo.EchoRequest",
        encoded,
    )

    assert compiled.packages == ("qa.echo",)
    assert compiled.messages[0].full_name == "qa.echo.EchoRequest"
    assert compiled.services[0].methods[0].input_type == "qa.echo.EchoRequest"
    assert compiled.enums[0].values[1].name == "ECHO_MODE_FAST"
    assert decoded == {"text": "hello", "count": 2}


def test_compiler_allows_bundled_google_well_known_types(tmp_path: Path) -> None:
    (tmp_path / "event.proto").write_text(
        """syntax = "proto3";
package qa.event;
import "google/protobuf/timestamp.proto";
message Event { google.protobuf.Timestamp created_at = 1; }
""",
        encoding="utf-8",
    )

    compiled = GrpcToolsProtoCompiler().compile(str(tmp_path), "event.proto")
    encoded = DynamicProtobufCodec().encode(
        compiled.descriptor_set,
        "qa.event.Event",
        {"created_at": "2026-08-16T08:00:00Z"},
    )

    assert DynamicProtobufCodec().decode(compiled.descriptor_set, "qa.event.Event", encoded) == {
        "created_at": "2026-08-16T08:00:00Z"
    }


def test_compiler_rejects_local_imports_before_invoking_protoc(tmp_path: Path) -> None:
    (tmp_path / "root.proto").write_text(
        'syntax = "proto3";\nimport "private/types.proto";\n', encoding="utf-8"
    )

    with pytest.raises(ProtoCompilerError) as raised:
        GrpcToolsProtoCompiler().compile(str(tmp_path), "root.proto")

    assert raised.value.code == "PROTO_LOCAL_IMPORT_UNSUPPORTED"


def test_compiler_rejects_a_malformed_proto_without_exposing_protoc_output(
    tmp_path: Path,
) -> None:
    (tmp_path / "broken.proto").write_text(
        'syntax = "proto3";\nmessage Broken { string value = ; }', encoding="utf-8"
    )

    with pytest.raises(ProtoCompilerError) as raised:
        GrpcToolsProtoCompiler().compile(str(tmp_path), "broken.proto")

    assert raised.value.code == "PROTO_DEFINITION_INVALID"
    assert str(tmp_path) not in raised.value.message


def test_codec_rejects_unknown_json_fields_and_invalid_binary(tmp_path: Path) -> None:
    (tmp_path / "echo.proto").write_text(PROTO, encoding="utf-8")
    compiled = GrpcToolsProtoCompiler().compile(str(tmp_path), "echo.proto")
    codec = DynamicProtobufCodec()

    with pytest.raises(ProtoCodecError) as unknown:
        codec.encode(compiled.descriptor_set, "qa.echo.EchoRequest", {"unknown": 1})
    with pytest.raises(ProtoCodecError) as malformed:
        codec.decode(compiled.descriptor_set, "qa.echo.EchoRequest", b"\x0a\xff")

    assert unknown.value.code == "PROTO_UNKNOWN_FIELD"
    assert malformed.value.code == "PROTO_DECODE_FAILED"
