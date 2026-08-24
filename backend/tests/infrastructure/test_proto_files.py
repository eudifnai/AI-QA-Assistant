from pathlib import Path

import pytest

from backend.app.infrastructure.proto_files import LocalProtoFiles, ProtoFileError


def test_proto_file_inspection_hashes_a_workspace_file(tmp_path: Path) -> None:
    source = tmp_path / "contracts" / "echo.proto"
    source.parent.mkdir()
    source.write_text('syntax = "proto3";', encoding="utf-8")

    inspected = LocalProtoFiles(max_bytes=1024).inspect(str(tmp_path), str(source))

    assert inspected.relative_path == "contracts/echo.proto"
    assert inspected.size_bytes == source.stat().st_size
    assert len(inspected.sha256) == 64


@pytest.mark.parametrize(
    ("name", "content", "max_bytes", "reason"),
    [
        ("echo.txt", b"text", 1024, "unsupported_format"),
        ("echo.proto", b"x" * 1025, 1024, "file_too_large"),
    ],
)
def test_proto_file_inspection_rejects_unsupported_or_large_files(
    tmp_path: Path,
    name: str,
    content: bytes,
    max_bytes: int,
    reason: str,
) -> None:
    source = tmp_path / name
    source.write_bytes(content)

    with pytest.raises(ProtoFileError) as raised:
        LocalProtoFiles(max_bytes=max_bytes).inspect(str(tmp_path), str(source))

    assert raised.value.reason == reason


def test_proto_file_inspection_rejects_path_traversal(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.proto"
    outside.write_text('syntax = "proto3";', encoding="utf-8")

    with pytest.raises(ProtoFileError) as raised:
        LocalProtoFiles(max_bytes=1024).inspect(str(workspace), str(outside))

    assert raised.value.reason == "path_outside_workspace"
