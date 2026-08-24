from pathlib import Path

import pytest

from backend.app.infrastructure.document_files import DocumentFileError, LocalDocumentFiles


def test_document_file_is_hashed_and_read_relative_to_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = workspace / "requirements.md"
    source.write_text("# 支付需求\n\n必须支持退款。", encoding="utf-8")
    files = LocalDocumentFiles(max_bytes=1024)

    inspected = files.inspect(str(workspace), str(source))
    text = files.read_text(
        str(workspace),
        inspected.relative_path,
        expected_sha256=inspected.sha256,
    )

    assert inspected.relative_path == "requirements.md"
    assert inspected.name == "requirements.md"
    assert len(inspected.sha256) == 64
    assert text.startswith("# 支付需求")


@pytest.mark.parametrize(
    ("file_name", "content", "max_bytes", "reason"),
    [
        ("requirements.rtf", b"rtf", 1024, "unsupported_format"),
        ("large.md", b"a" * 12, 10, "file_too_large"),
    ],
)
def test_document_file_rejects_unsupported_and_oversized_inputs(
    tmp_path: Path,
    file_name: str,
    content: bytes,
    max_bytes: int,
    reason: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = workspace / file_name
    source.write_bytes(content)

    with pytest.raises(DocumentFileError, match=reason):
        LocalDocumentFiles(max_bytes=max_bytes).inspect(str(workspace), str(source))


def test_document_file_rejects_path_traversal_and_damaged_utf8(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("private", encoding="utf-8")
    damaged = workspace / "damaged.txt"
    damaged.write_bytes(b"\xff\xfe")
    files = LocalDocumentFiles(max_bytes=1024)

    with pytest.raises(DocumentFileError, match="path_outside_workspace"):
        files.inspect(str(workspace), str(outside))

    inspected = files.inspect(str(workspace), str(damaged))
    with pytest.raises(DocumentFileError, match="invalid_encoding"):
        files.read_text(
            str(workspace),
            inspected.relative_path,
            expected_sha256=inspected.sha256,
        )


@pytest.mark.parametrize("file_name", ["requirements.docx", "requirements.pdf"])
def test_document_file_accepts_docx_and_pdf_for_worker_parsing(
    tmp_path: Path, file_name: str
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = workspace / file_name
    source.write_bytes(b"worker validates the actual container later")

    inspected = LocalDocumentFiles(max_bytes=1024).inspect(str(workspace), str(source))

    assert inspected.name == file_name
