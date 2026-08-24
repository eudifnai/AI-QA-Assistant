from collections.abc import Callable
from typing import Protocol, TypeVar

from backend.app.core.errors import AppError

MIN_MODEL_CREDENTIAL_LENGTH = 8
MAX_MODEL_CREDENTIAL_LENGTH = 8192
T = TypeVar("T")


class CredentialStoreUnavailableError(Exception):
    pass


class CredentialStore(Protocol):
    def is_configured(self) -> bool: ...

    def set(self, secret: str) -> None: ...

    def delete(self) -> None: ...


class ModelCredentialUseCases(Protocol):
    def status(self) -> bool: ...

    def set(self, secret: str) -> bool: ...

    def delete(self) -> bool: ...


class ModelCredentialService:
    def __init__(self, store: CredentialStore) -> None:
        self._store = store

    def status(self) -> bool:
        return self._with_store_error_mapping(self._store.is_configured)

    def set(self, secret: str) -> bool:
        if (
            len(secret) < MIN_MODEL_CREDENTIAL_LENGTH
            or len(secret) > MAX_MODEL_CREDENTIAL_LENGTH
            or secret != secret.strip()
        ):
            raise AppError(
                code="MODEL_CREDENTIAL_INVALID",
                message="模型凭据格式不正确。",
                status_code=422,
            )
        self._with_store_error_mapping(lambda: self._store.set(secret))
        return True

    def delete(self) -> bool:
        self._with_store_error_mapping(self._store.delete)
        return False

    @staticmethod
    def _with_store_error_mapping(operation: Callable[[], T]) -> T:
        try:
            return operation()
        except CredentialStoreUnavailableError as exception:
            raise AppError(
                code="CREDENTIAL_STORE_UNAVAILABLE",
                message="操作系统凭据库当前不可用。",
                status_code=503,
            ) from exception
