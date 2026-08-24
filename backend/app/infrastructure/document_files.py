import hashlib
from pathlib import Path

from backend.app.domain.document import DocumentSource

SUPPORTED_DOCUMENT_SUFFIXES = frozenset({".docx", ".md", ".pdf", ".txt"})


class DocumentFileError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class LocalDocumentFiles:
    def __init__(self, *, max_bytes: int) -> None:
        self._max_bytes = max_bytes

    def inspect(self, workspace_path: str, source_path: str) -> DocumentSource:
        workspace = Path(workspace_path).resolve(strict=False)
        source = Path(source_path)
        if not source.is_absolute():
            raise DocumentFileError("path_invalid")
        resolved = source.resolve(strict=False)
        try:
            relative = resolved.relative_to(workspace)
        except ValueError as exception:
            raise DocumentFileError("path_outside_workspace") from exception
        if not resolved.is_file():
            raise DocumentFileError("file_not_found")
        if resolved.suffix.casefold() not in SUPPORTED_DOCUMENT_SUFFIXES:
            raise DocumentFileError("unsupported_format")
        try:
            size_bytes = resolved.stat().st_size
            if size_bytes > self._max_bytes:
                raise DocumentFileError("file_too_large")
            digest = self._hash(resolved)
        except OSError as exception:
            raise DocumentFileError("file_unavailable") from exception
        return DocumentSource(
            name=resolved.name,
            relative_path=relative.as_posix(),
            sha256=digest,
            size_bytes=size_bytes,
        )

    def read_text(
        self,
        workspace_path: str,
        relative_path: str,
        *,
        expected_sha256: str,
    ) -> str:
        content = self.read_bytes(
            workspace_path,
            relative_path,
            expected_sha256=expected_sha256,
        )
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError as exception:
            raise DocumentFileError("invalid_encoding") from exception

    def read_bytes(
        self,
        workspace_path: str,
        relative_path: str,
        *,
        expected_sha256: str,
    ) -> bytes:
        workspace = Path(workspace_path).resolve(strict=False)
        source = (workspace / relative_path).resolve(strict=False)
        try:
            source.relative_to(workspace)
        except ValueError as exception:
            raise DocumentFileError("path_outside_workspace") from exception
        if not source.is_file():
            raise DocumentFileError("file_not_found")
        if source.suffix.casefold() not in SUPPORTED_DOCUMENT_SUFFIXES:
            raise DocumentFileError("unsupported_format")
        try:
            if source.stat().st_size > self._max_bytes:
                raise DocumentFileError("file_too_large")
            content = source.read_bytes()
        except OSError as exception:
            raise DocumentFileError("file_unavailable") from exception
        if hashlib.sha256(content).hexdigest() != expected_sha256:
            raise DocumentFileError("file_changed")
        return content

    @staticmethod
    def _hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()
