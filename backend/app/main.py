from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.dependencies import create_session_auth_dependency
from backend.app.api.routes.analysis import create_analysis_router
from backend.app.api.routes.documents import create_document_router
from backend.app.api.routes.health import create_health_router
from backend.app.api.routes.http_execution import create_http_execution_router
from backend.app.api.routes.maintenance import create_maintenance_router
from backend.app.api.routes.proto_assets import create_proto_asset_router
from backend.app.api.routes.protobuf_execution import create_protobuf_execution_router
from backend.app.api.routes.reports import create_report_router
from backend.app.api.routes.settings import create_settings_router
from backend.app.api.routes.task_events import create_task_event_router
from backend.app.api.routes.test_design import create_test_design_router
from backend.app.api.routes.websocket_execution import create_websocket_execution_router
from backend.app.api.routes.workspaces import create_workspace_router
from backend.app.application.analysis import AnalysisService, AnalysisUseCases
from backend.app.application.credentials import ModelCredentialService, ModelCredentialUseCases
from backend.app.application.documents import DocumentService, DocumentUseCases
from backend.app.application.health import HealthService
from backend.app.application.http_execution import HttpExecutionService, HttpExecutionUseCases
from backend.app.application.maintenance import MaintenanceService, MaintenanceUseCases
from backend.app.application.proto_assets import ProtoAssetService, ProtoAssetUseCases
from backend.app.application.protobuf_execution import (
    ProtoExecutionService,
    ProtoExecutionUseCases,
)
from backend.app.application.reports import ReportService, ReportUseCases
from backend.app.application.settings import SettingsService, SettingsUseCases
from backend.app.application.task_events import TaskEventService, TaskEventUseCases
from backend.app.application.test_design import TestDesignService, TestDesignUseCases
from backend.app.application.websocket_execution import (
    WebSocketExecutionService,
    WebSocketExecutionUseCases,
)
from backend.app.application.workspaces import WorkspaceService, WorkspaceUseCases
from backend.app.core.config import Settings, get_settings
from backend.app.core.errors import configure_error_handling
from backend.app.core.version import APP_VERSION
from backend.app.infrastructure.analysis import SqlModelAnalysisRepository
from backend.app.infrastructure.credentials import KeyringCredentialStore, KeyringHttpSecretStore
from backend.app.infrastructure.database import create_database_engine
from backend.app.infrastructure.document_files import LocalDocumentFiles
from backend.app.infrastructure.documents import SqlModelDocumentRepository
from backend.app.infrastructure.http_execution import SqlModelHttpExecutionRepository
from backend.app.infrastructure.maintenance import SqliteMaintenanceStorage
from backend.app.infrastructure.proto_assets import SqlModelProtoAssetRepository
from backend.app.infrastructure.proto_files import LocalProtoFiles
from backend.app.infrastructure.protobuf_codec import DynamicProtobufCodec, GrpcToolsProtoCompiler
from backend.app.infrastructure.protobuf_execution import SqlModelProtoExecutionRepository
from backend.app.infrastructure.report_renderers import SafeReportRenderer
from backend.app.infrastructure.reports import SqlModelReportReader
from backend.app.infrastructure.settings import SqlModelSettingsRepository
from backend.app.infrastructure.task_events import SqlModelTaskSnapshotReader
from backend.app.infrastructure.test_design import SqlModelTestDesignRepository
from backend.app.infrastructure.websocket_execution import SqlModelWebSocketExecutionRepository
from backend.app.infrastructure.workspace_storage import LocalWorkspaceStorage
from backend.app.infrastructure.workspaces import SqlModelWorkspaceRepository
from backend.app.workers.analysis import AnalysisWorkerManager
from backend.app.workers.document_parser import DocumentParseWorkerManager
from backend.app.workers.http_execution import HttpExecutionWorkerManager
from backend.app.workers.protobuf_execution import ProtoExecutionWorkerManager
from backend.app.workers.websocket_execution import WebSocketExecutionWorkerManager


def create_app(
    health_service: HealthService | None = None,
    settings: Settings | None = None,
    workspace_service: WorkspaceUseCases | None = None,
    settings_service: SettingsUseCases | None = None,
    credential_service: ModelCredentialUseCases | None = None,
    maintenance_service: MaintenanceUseCases | None = None,
    document_service: DocumentUseCases | None = None,
    analysis_service: AnalysisUseCases | None = None,
    test_design_service: TestDesignUseCases | None = None,
    http_execution_service: HttpExecutionUseCases | None = None,
    websocket_execution_service: WebSocketExecutionUseCases | None = None,
    proto_asset_service: ProtoAssetUseCases | None = None,
    protobuf_execution_service: ProtoExecutionUseCases | None = None,
    report_service: ReportUseCases | None = None,
    task_event_service: TaskEventUseCases | None = None,
    task_event_poll_interval_seconds: float = 0.25,
) -> FastAPI:
    configured_settings = settings or get_settings()
    session_auth = create_session_auth_dependency(configured_settings.session_token)
    app = FastAPI(
        title=configured_settings.app_name,
        version=APP_VERSION,
        dependencies=[Depends(session_auth)],
    )
    configure_error_handling(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(configured_settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["DELETE", "GET", "PATCH", "POST", "PUT"],
        allow_headers=["Accept", "Authorization", "Content-Type", "X-Trace-ID"],
    )
    service = health_service or HealthService(version=APP_VERSION)
    app.include_router(create_health_router(service))
    engine = create_database_engine(configured_settings.database_url)
    if workspace_service is None:
        workspace_service = WorkspaceService(
            repository=SqlModelWorkspaceRepository(engine),
            storage=LocalWorkspaceStorage(),
        )
    app.include_router(create_workspace_router(workspace_service))
    if settings_service is None:
        settings_service = SettingsService(SqlModelSettingsRepository(engine))
    if credential_service is None:
        credential_service = ModelCredentialService(KeyringCredentialStore())
    app.include_router(create_settings_router(settings_service, credential_service))
    if maintenance_service is None:
        maintenance_service = MaintenanceService(
            SqliteMaintenanceStorage(configured_settings.database_url),
            app_version=APP_VERSION,
        )
    app.include_router(create_maintenance_router(maintenance_service))
    if document_service is None:
        document_repository = SqlModelDocumentRepository(engine)
        document_service = DocumentService(
            SqlModelWorkspaceRepository(engine),
            document_repository,
            LocalDocumentFiles(max_bytes=configured_settings.document_max_bytes),
            DocumentParseWorkerManager(
                document_repository,
                database_url=configured_settings.database_url,
                max_bytes=configured_settings.document_max_bytes,
                timeout_seconds=configured_settings.document_parse_timeout_seconds,
            ),
        )
    app.include_router(create_document_router(document_service))
    if analysis_service is None:
        analysis_repository = SqlModelAnalysisRepository(engine)
        analysis_service = AnalysisService(
            SqlModelWorkspaceRepository(engine),
            SqlModelDocumentRepository(engine),
            settings_service,
            analysis_repository,
            AnalysisWorkerManager(
                analysis_repository,
                database_url=configured_settings.database_url,
                timeout_seconds=configured_settings.analysis_timeout_seconds,
                model_timeout_seconds=configured_settings.model_request_timeout_seconds,
            ),
            credential_service,
        )
    app.include_router(create_analysis_router(analysis_service))
    if test_design_service is None:
        test_design_service = TestDesignService(
            analysis_service,
            SqlModelTestDesignRepository(engine),
        )
    app.include_router(create_test_design_router(test_design_service))
    if http_execution_service is None:
        http_repository = SqlModelHttpExecutionRepository(engine)
        http_execution_service = HttpExecutionService(
            SqlModelWorkspaceRepository(engine),
            http_repository,
            KeyringHttpSecretStore(),
            HttpExecutionWorkerManager(
                http_repository,
                database_url=configured_settings.database_url,
                timeout_seconds=configured_settings.http_execution_timeout_seconds,
            ),
        )
    app.include_router(create_http_execution_router(http_execution_service))
    if websocket_execution_service is None:
        websocket_repository = SqlModelWebSocketExecutionRepository(engine)
        websocket_execution_service = WebSocketExecutionService(
            SqlModelWorkspaceRepository(engine),
            SqlModelHttpExecutionRepository(engine),
            websocket_repository,
            WebSocketExecutionWorkerManager(
                websocket_repository,
                database_url=configured_settings.database_url,
                timeout_seconds=configured_settings.websocket_execution_timeout_seconds,
            ),
        )
    app.include_router(create_websocket_execution_router(websocket_execution_service))
    if proto_asset_service is None:
        proto_asset_service = ProtoAssetService(
            SqlModelWorkspaceRepository(engine),
            SqlModelProtoAssetRepository(engine),
            LocalProtoFiles(max_bytes=configured_settings.proto_max_bytes),
            GrpcToolsProtoCompiler(),
            DynamicProtobufCodec(),
        )
    app.include_router(create_proto_asset_router(proto_asset_service))
    if protobuf_execution_service is None:
        protobuf_repository = SqlModelProtoExecutionRepository(engine)
        protobuf_execution_service = ProtoExecutionService(
            SqlModelWorkspaceRepository(engine),
            SqlModelHttpExecutionRepository(engine),
            SqlModelProtoAssetRepository(engine),
            protobuf_repository,
            DynamicProtobufCodec(),
            ProtoExecutionWorkerManager(
                protobuf_repository,
                database_url=configured_settings.database_url,
                timeout_seconds=configured_settings.protobuf_execution_timeout_seconds,
            ),
        )
    app.include_router(create_protobuf_execution_router(protobuf_execution_service))
    if report_service is None:
        report_service = ReportService(
            SqlModelWorkspaceRepository(engine),
            SqlModelReportReader(engine),
            SafeReportRenderer(),
        )
    app.include_router(create_report_router(report_service))
    if task_event_service is None:
        task_event_service = TaskEventService(
            SqlModelWorkspaceRepository(engine),
            SqlModelTaskSnapshotReader(engine),
        )
    app.include_router(
        create_task_event_router(
            task_event_service,
            poll_interval_seconds=task_event_poll_interval_seconds,
        )
    )
    return app


app = create_app()
