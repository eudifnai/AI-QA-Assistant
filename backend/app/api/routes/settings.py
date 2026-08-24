from fastapi import APIRouter

from backend.app.application.credentials import ModelCredentialUseCases
from backend.app.application.settings import SettingsUseCases
from backend.app.schemas.settings import (
    ModelCredentialRequest,
    ModelCredentialStatusResponse,
    SettingsResponse,
    SettingsUpdateRequest,
)


def create_settings_router(
    service: SettingsUseCases, credential_service: ModelCredentialUseCases
) -> APIRouter:
    router = APIRouter(prefix="/api/settings", tags=["settings"])

    @router.get("", response_model=SettingsResponse)
    def get_settings() -> SettingsResponse:
        return SettingsResponse.model_validate(service.get())

    @router.put("", response_model=SettingsResponse)
    def update_settings(payload: SettingsUpdateRequest) -> SettingsResponse:
        return SettingsResponse.model_validate(service.update(**payload.model_dump()))

    @router.get("/model-credential", response_model=ModelCredentialStatusResponse)
    def get_model_credential_status() -> ModelCredentialStatusResponse:
        return ModelCredentialStatusResponse(configured=credential_service.status())

    @router.put("/model-credential", response_model=ModelCredentialStatusResponse)
    def set_model_credential(payload: ModelCredentialRequest) -> ModelCredentialStatusResponse:
        return ModelCredentialStatusResponse(configured=credential_service.set(payload.api_key))

    @router.delete("/model-credential", response_model=ModelCredentialStatusResponse)
    def delete_model_credential() -> ModelCredentialStatusResponse:
        return ModelCredentialStatusResponse(configured=credential_service.delete())

    return router
