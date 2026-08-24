"""Tests for the operating-system keyring adapter."""

import keyring
import pytest

from backend.app.application.credentials import CredentialStoreUnavailableError
from backend.app.infrastructure.credentials import (
    HTTP_SECRET_ACCOUNT_PREFIX,
    MODEL_CREDENTIAL_ACCOUNT,
    MODEL_CREDENTIAL_SERVICE,
    KeyringCredentialStore,
    KeyringHttpSecretStore,
)


def test_keyring_adapter_uses_fixed_service_and_account(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        keyring,
        "set_password",
        lambda service, account, secret: calls.append(("set", service, account, secret)),
    )
    monkeypatch.setattr(
        keyring,
        "get_password",
        lambda service, account: "configured" if account == MODEL_CREDENTIAL_ACCOUNT else None,
    )
    monkeypatch.setattr(
        keyring,
        "delete_password",
        lambda service, account: calls.append(("delete", service, account)),
    )
    store = KeyringCredentialStore()

    store.set("test-credential-value")
    assert store.get() == "configured"
    assert store.is_configured() is True
    store.delete()

    assert calls == [
        ("set", MODEL_CREDENTIAL_SERVICE, MODEL_CREDENTIAL_ACCOUNT, "test-credential-value"),
        ("delete", MODEL_CREDENTIAL_SERVICE, MODEL_CREDENTIAL_ACCOUNT),
    ]


def test_keyring_adapter_maps_backend_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_get(service: str, account: str) -> None:
        raise keyring.errors.KeyringError("sensitive backend detail")

    monkeypatch.setattr(keyring, "get_password", fail_get)

    with pytest.raises(CredentialStoreUnavailableError):
        KeyringCredentialStore().is_configured()
    with pytest.raises(CredentialStoreUnavailableError):
        KeyringCredentialStore().get()


def test_http_secret_adapter_scopes_values_by_environment_and_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []
    account = f"{HTTP_SECRET_ACCOUNT_PREFIX}:environment-1:API_TOKEN"
    monkeypatch.setattr(
        keyring,
        "set_password",
        lambda service, current_account, secret: calls.append(
            ("set", service, current_account, secret)
        ),
    )
    monkeypatch.setattr(
        keyring,
        "get_password",
        lambda service, current_account: "configured" if current_account == account else None,
    )
    monkeypatch.setattr(
        keyring,
        "delete_password",
        lambda service, current_account: calls.append(("delete", service, current_account)),
    )
    store = KeyringHttpSecretStore()

    store.set("environment-1", "API_TOKEN", "top-secret")
    assert store.get("environment-1", "API_TOKEN") == "configured"
    store.delete("environment-1", "API_TOKEN")

    assert calls == [
        ("set", MODEL_CREDENTIAL_SERVICE, account, "top-secret"),
        ("delete", MODEL_CREDENTIAL_SERVICE, account),
    ]
