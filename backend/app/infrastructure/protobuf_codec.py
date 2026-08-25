from __future__ import annotations

import os
import re
import subprocess
import sys
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from google.protobuf import descriptor_pb2, descriptor_pool, json_format, message
from google.protobuf.message_factory import GetMessageClass

from backend.app.domain.proto_asset import (
    ProtoCompileResult,
    ProtoEnum,
    ProtoEnumValue,
    ProtoField,
    ProtoMessage,
    ProtoMethod,
    ProtoService,
)

MAX_DESCRIPTOR_BYTES = 2 * 1024 * 1024
MAX_DECLARATIONS = 2000
IMPORT_PATTERN = re.compile(r'\bimport\s+(?:(?:public|weak)\s+)?"([^"]+)"\s*;')


class ProtoCompilerError(Exception):
    def __init__(self, code: str, message_text: str) -> None:
        super().__init__(message_text)
        self.code = code
        self.message = message_text


class ProtoCodecError(Exception):
    def __init__(self, code: str, message_text: str) -> None:
        super().__init__(message_text)
        self.code = code
        self.message = message_text


def _strip_comments(source: str) -> str:
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(source):
        current = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if in_string:
            output.append(current)
            if escaped:
                escaped = False
            elif current == "\\":
                escaped = True
            elif current == '"':
                in_string = False
            index += 1
            continue
        if current == '"':
            in_string = True
            output.append(current)
            index += 1
            continue
        if current == "/" and following == "/":
            newline = source.find("\n", index + 2)
            if newline < 0:
                break
            output.append("\n")
            index = newline + 1
            continue
        if current == "/" and following == "*":
            end = source.find("*/", index + 2)
            if end < 0:
                raise ProtoCompilerError("PROTO_DEFINITION_INVALID", "Proto 注释未闭合。")
            output.append("\n" * source[index : end + 2].count("\n"))
            index = end + 2
            continue
        output.append(current)
        index += 1
    return "".join(output)


def _join_name(prefix: str, name: str) -> str:
    return f"{prefix}.{name}" if prefix else name


def _messages(
    declarations: list[descriptor_pb2.DescriptorProto], prefix: str
) -> list[ProtoMessage]:
    result: list[ProtoMessage] = []
    for declaration in declarations:
        full_name = _join_name(prefix, declaration.name)
        fields = tuple(
            ProtoField(
                field.name,
                field.number,
                descriptor_pb2.FieldDescriptorProto.Type.Name(field.type),
                descriptor_pb2.FieldDescriptorProto.Label.Name(field.label),
                field.type_name.lstrip(".") or None,
            )
            for field in declaration.field
        )
        result.append(ProtoMessage(declaration.name, full_name, fields))
        result.extend(_messages(list(declaration.nested_type), full_name))
    return result


def _enums(declarations: list[descriptor_pb2.EnumDescriptorProto], prefix: str) -> list[ProtoEnum]:
    return [
        ProtoEnum(
            declaration.name,
            _join_name(prefix, declaration.name),
            tuple(ProtoEnumValue(value.name, value.number) for value in declaration.value),
        )
        for declaration in declarations
    ]


def summarize_descriptor_set(descriptor_bytes: bytes, target_name: str) -> ProtoCompileResult:
    descriptor_set = descriptor_pb2.FileDescriptorSet()
    try:
        descriptor_set.ParseFromString(descriptor_bytes)
    except message.DecodeError as exception:
        raise ProtoCompilerError("PROTO_DESCRIPTOR_INVALID", "Proto 描述符无效。") from exception
    target = next((item for item in descriptor_set.file if item.name == target_name), None)
    if target is None:
        raise ProtoCompilerError("PROTO_DESCRIPTOR_INVALID", "Proto 描述符缺少目标文件。")
    package = target.package
    messages = _messages(list(target.message_type), package)
    enums = _enums(list(target.enum_type), package)
    for declaration in target.message_type:
        enums.extend(_enums(list(declaration.enum_type), _join_name(package, declaration.name)))
    services = tuple(
        ProtoService(
            service.name,
            _join_name(package, service.name),
            tuple(
                ProtoMethod(
                    method.name,
                    method.input_type.lstrip("."),
                    method.output_type.lstrip("."),
                    method.client_streaming,
                    method.server_streaming,
                )
                for method in service.method
            ),
        )
        for service in target.service
    )
    declaration_count = (
        len(messages) + len(enums) + len(services) + sum(len(item.fields) for item in messages)
    )
    if declaration_count > MAX_DECLARATIONS:
        raise ProtoCompilerError("PROTO_TOO_COMPLEX", "Proto 定义包含过多声明。")
    return ProtoCompileResult(
        descriptor_bytes,
        (package,) if package else (),
        tuple(messages),
        tuple(enums),
        services,
    )


class GrpcToolsProtoCompiler:
    def __init__(self, *, timeout_seconds: int = 10) -> None:
        self._timeout_seconds = timeout_seconds

    def compile(self, workspace_path: str, relative_path: str) -> ProtoCompileResult:
        workspace = Path(workspace_path).resolve(strict=False)
        source = (workspace / relative_path).resolve(strict=False)
        try:
            source.relative_to(workspace)
            source_text = source.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError, ValueError) as exception:
            raise ProtoCompilerError(
                "PROTO_FILE_UNAVAILABLE", "无法读取 Proto 文件。"
            ) from exception
        imports = IMPORT_PATTERN.findall(_strip_comments(source_text))
        if any(not item.startswith("google/protobuf/") for item in imports):
            raise ProtoCompilerError(
                "PROTO_LOCAL_IMPORT_UNSUPPORTED",
                "当前切片暂不支持本地 Proto 文件之间的 import。",
            )

        with TemporaryDirectory(prefix="ai-qa-proto-") as temporary_directory:
            output_path = Path(temporary_directory) / "descriptor.pb"
            standard_include = str(files("grpc_tools").joinpath("_proto"))
            command = build_grpc_tools_command(
                executable=sys.executable,
                frozen=bool(getattr(sys, "frozen", False)),
                arguments=(
                    f"-I{workspace}",
                    f"-I{standard_include}",
                    f"--descriptor_set_out={output_path}",
                    "--include_imports",
                    relative_path.replace("\\", "/"),
                ),
            )
            try:
                result = subprocess.run(
                    command,
                    cwd=workspace,
                    check=False,
                    capture_output=True,
                    timeout=self._timeout_seconds,
                    shell=False,
                    creationflags=(
                        getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
                    ),
                )
            except subprocess.TimeoutExpired as exception:
                raise ProtoCompilerError("PROTO_COMPILE_TIMEOUT", "Proto 编译超时。") from exception
            except OSError as exception:
                raise ProtoCompilerError(
                    "PROTO_COMPILER_UNAVAILABLE", "Proto 编译器不可用。"
                ) from exception
            if result.returncode != 0 or not output_path.is_file():
                raise ProtoCompilerError("PROTO_DEFINITION_INVALID", "Proto 定义无法解析。")
            descriptor_bytes = output_path.read_bytes()
        if len(descriptor_bytes) > MAX_DESCRIPTOR_BYTES:
            raise ProtoCompilerError("PROTO_DESCRIPTOR_TOO_LARGE", "Proto 描述符超过大小限制。")
        return summarize_descriptor_set(descriptor_bytes, relative_path.replace("\\", "/"))


def build_grpc_tools_command(
    *,
    executable: str,
    frozen: bool,
    arguments: tuple[str, ...],
) -> list[str]:
    dispatch = ["--grpc-tools-protoc"] if frozen else ["-m", "grpc_tools.protoc"]
    return [executable, *dispatch, *arguments]


def _pool(descriptor_bytes: bytes) -> descriptor_pool.DescriptorPool:
    descriptor_set = descriptor_pb2.FileDescriptorSet()
    try:
        descriptor_set.ParseFromString(descriptor_bytes)
    except message.DecodeError as exception:
        raise ProtoCodecError("PROTO_DESCRIPTOR_INVALID", "Proto 描述符无效。") from exception
    pool = descriptor_pool.DescriptorPool()
    pending = list(descriptor_set.file)
    while pending:
        deferred: list[descriptor_pb2.FileDescriptorProto] = []
        for item in pending:
            try:
                pool.Add(item)  # type: ignore[no-untyped-call]
            except TypeError:
                deferred.append(item)
        if len(deferred) == len(pending):
            raise ProtoCodecError("PROTO_DESCRIPTOR_INVALID", "Proto 描述符依赖不完整。")
        pending = deferred
    return pool


class DynamicProtobufCodec:
    def encode(self, descriptor_set: bytes, message_type: str, payload: dict[str, Any]) -> bytes:
        pool = _pool(descriptor_set)
        try:
            descriptor = pool.FindMessageTypeByName(message_type)  # type: ignore[no-untyped-call]
        except KeyError as exception:
            raise ProtoCodecError(
                "PROTO_MESSAGE_NOT_FOUND", "未找到指定的 Proto message。"
            ) from exception
        instance = GetMessageClass(descriptor)()
        try:
            json_format.ParseDict(payload, instance, ignore_unknown_fields=False)
        except json_format.ParseError as exception:
            code = (
                "PROTO_UNKNOWN_FIELD"
                if "has no field named" in str(exception)
                else "PROTO_JSON_INVALID"
            )
            raise ProtoCodecError(code, "JSON 数据与 Proto message 不匹配。") from exception
        return bytes(instance.SerializeToString(deterministic=True))

    def decode(self, descriptor_set: bytes, message_type: str, payload: bytes) -> dict[str, Any]:
        pool = _pool(descriptor_set)
        try:
            descriptor = pool.FindMessageTypeByName(message_type)  # type: ignore[no-untyped-call]
        except KeyError as exception:
            raise ProtoCodecError(
                "PROTO_MESSAGE_NOT_FOUND", "未找到指定的 Proto message。"
            ) from exception
        instance = GetMessageClass(descriptor)()
        try:
            instance.ParseFromString(payload)
        except message.DecodeError as exception:
            raise ProtoCodecError("PROTO_DECODE_FAILED", "Protobuf 二进制无法解码。") from exception
        result = json_format.MessageToDict(
            instance,
            preserving_proto_field_name=True,
            use_integers_for_enums=False,
        )
        if not isinstance(result, dict):
            raise ProtoCodecError("PROTO_DECODE_FAILED", "Protobuf 解码结果无效。")
        return result
