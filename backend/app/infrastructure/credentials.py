import keyring
from keyring.errors import KeyringError, PasswordDeleteError

from backend.app.application.credentials import CredentialStoreUnavailableError

MODEL_CREDENTIAL_SERVICE = "AI-QA-Assistant"
MODEL_CREDENTIAL_ACCOUNT = "model-provider-api-key"
HTTP_SECRET_ACCOUNT_PREFIX = "http-environment"


class KeyringCredentialStore:
    def get(self) -> str | None:
        try:
            return keyring.get_password(MODEL_CREDENTIAL_SERVICE, MODEL_CREDENTIAL_ACCOUNT)
        except KeyringError as exception:
            raise CredentialStoreUnavailableError from exception

    def is_configured(self) -> bool:
        return self.get() is not None

    def set(self, secret: str) -> None:
        try:
            keyring.set_password(MODEL_CREDENTIAL_SERVICE, MODEL_CREDENTIAL_ACCOUNT, secret)
        except KeyringError as exception:
            raise CredentialStoreUnavailableError from exception

    def delete(self) -> None:
        try:
            if keyring.get_password(MODEL_CREDENTIAL_SERVICE, MODEL_CREDENTIAL_ACCOUNT) is None:
                return
            keyring.delete_password(MODEL_CREDENTIAL_SERVICE, MODEL_CREDENTIAL_ACCOUNT)
        except PasswordDeleteError:
            return
        except KeyringError as exception:
            raise CredentialStoreUnavailableError from exception


class KeyringHttpSecretStore:
    @staticmethod
    def _account(environment_id: str, name: str) -> str:
        return f"{HTTP_SECRET_ACCOUNT_PREFIX}:{environment_id}:{name}"

    def get(self, environment_id: str, name: str) -> str | None:
        try:
            return keyring.get_password(
                MODEL_CREDENTIAL_SERVICE,
                self._account(environment_id, name),
            )
        except KeyringError as exception:
            raise CredentialStoreUnavailableError from exception

    def set(self, environment_id: str, name: str, secret: str) -> None:
        try:
            keyring.set_password(
                MODEL_CREDENTIAL_SERVICE,
                self._account(environment_id, name),
                secret,
            )
        except KeyringError as exception:
            raise CredentialStoreUnavailableError from exception

    def delete(self, environment_id: str, name: str) -> None:
        account = self._account(environment_id, name)
        try:
            if keyring.get_password(MODEL_CREDENTIAL_SERVICE, account) is None:
                return
            keyring.delete_password(MODEL_CREDENTIAL_SERVICE, account)
        except PasswordDeleteError:
            return
        except KeyringError as exception:
            raise CredentialStoreUnavailableError from exception
