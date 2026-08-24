import hashlib
from pathlib import Path

from backend.app.domain.proto_asset import ProtoSource


class ProtoFileError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class LocalProtoFiles:
    def __init__(self, *, max_bytes: int) -> None:
        self._max_bytes = max_bytes

    def inspect(self, workspace_path: str, source_path: str) -> ProtoSource:
        workspace = Path(workspace_path).resolve(strict=False)
        source = Path(source_path)
        if not source.is_absolute():
            raise ProtoFileError("path_invalid")
        resolved = source.resolve(strict=False)
        try:
            relative = resolved.relative_to(workspace)
        except ValueError as exception:
            raise ProtoFileError("path_outside_workspace") from exception
        if not resolved.is_file():
            raise ProtoFileError("file_not_found")
        if resolved.suffix.casefold() != ".proto":
            raise ProtoFileError("unsupported_format")
        try:
            size_bytes = resolved.stat().st_size
            if size_bytes > self._max_bytes:
                raise ProtoFileError("file_too_large")
            digest = self._hash(resolved)
        except OSError as exception:
            raise ProtoFileError("file_unavailable") from exception
        return ProtoSource(resolved.name, relative.as_posix(), digest, size_bytes)

    @staticmethod
    def _hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()
