import pytest

from backend.app.application.credentials import CredentialStore, ModelCredentialService
from backend.app.core.errors import AppError


class MemoryCredentialStore(CredentialStore):
    def __init__(self) -> None:
        self.secret: str | None = None

    def is_configured(self) -> bool:
        return self.secret is not None

    def set(self, secret: str) -> None:
        self.secret = secret

    def delete(self) -> None:
        self.secret = None


def test_credential_lifecycle_returns_only_configuration_status() -> None:
    store = MemoryCredentialStore()
    service = ModelCredentialService(store)

    assert service.status() is False
    assert service.set("test-credential-value") is True
    assert store.secret == "test-credential-value"
    assert service.delete() is False
    assert store.secret is None


@pytest.mark.parametrize("secret", ["", "   ", "short", " padded-credential "])
def test_credential_rejects_invalid_secret(secret: str) -> None:
    service = ModelCredentialService(MemoryCredentialStore())

    with pytest.raises(AppError) as raised:
        service.set(secret)

    assert raised.value.code == "MODEL_CREDENTIAL_INVALID"
    assert raised.value.status_code == 422
