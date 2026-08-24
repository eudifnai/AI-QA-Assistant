import os
import shutil
from pathlib import Path

from backend.app.core.errors import AppError

DEFAULT_MINIMUM_FREE_BYTES = 1024 * 1024


class LocalWorkspaceStorage:
    def __init__(self, minimum_free_bytes: int = DEFAULT_MINIMUM_FREE_BYTES) -> None:
        self._minimum_free_bytes = minimum_free_bytes

    def prepare(self, path: str) -> str:
        requested_path = Path(path).expanduser()
        if not requested_path.is_absolute():
            raise AppError(
                code="WORKSPACE_PATH_INVALID",
                message="工作空间必须使用绝对路径。",
                status_code=422,
            )

        canonical_path = requested_path.resolve(strict=False)
        try:
            canonical_path.mkdir(parents=True, exist_ok=True)
        except OSError as exception:
            raise AppError(
                code="WORKSPACE_PATH_UNAVAILABLE",
                message="无法创建或访问工作空间目录。",
                status_code=409,
            ) from exception

        self._validate_directory(canonical_path)
        return str(canonical_path)

    def ensure_available(self, path: str) -> None:
        canonical_path = Path(path).resolve(strict=False)
        self._validate_directory(canonical_path)

    def _validate_directory(self, path: Path) -> None:
        if not path.is_dir() or not os.access(path, os.W_OK):
            raise AppError(
                code="WORKSPACE_PATH_UNAVAILABLE",
                message="工作空间目录不存在或不可写。",
                status_code=409,
            )
        try:
            free_bytes = shutil.disk_usage(path).free
        except OSError as exception:
            raise AppError(
                code="WORKSPACE_STORAGE_UNAVAILABLE",
                message="无法检查工作空间存储空间。",
                status_code=409,
            ) from exception
        if free_bytes < self._minimum_free_bytes:
            raise AppError(
                code="WORKSPACE_STORAGE_INSUFFICIENT",
                message="工作空间所在磁盘可用空间不足。",
                status_code=409,
            )
