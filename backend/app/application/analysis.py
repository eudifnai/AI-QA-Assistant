from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Protocol
from uuid import uuid4

from backend.app.core.errors import AppError
from backend.app.domain.analysis import AnalysisRun, AnalysisTaskRequest
from backend.app.domain.document import DocumentChunk, DocumentItem
from backend.app.domain.settings import AppSettings, ModelMode, ModelProvider
from backend.app.domain.workspace import Workspace

MAX_ANALYSIS_INPUT_CHARS = 200_000


class WorkspaceReader(Protocol):
    def get(self, workspace_id: str) -> Workspace | None: ...


class DocumentReader(Protocol):
    def get(self, workspace_id: str, document_id: str) -> DocumentItem | None: ...

    def list_chunks(self, version_id: str) -> list[DocumentChunk]: ...


class SettingsReader(Protocol):
    def get(self) -> AppSettings: ...


class CredentialStatusReader(Protocol):
    def status(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class AnalysisStartInput:
    expected_version_id: str
    expected_provider: ModelProvider
    expected_model_name: str
    expected_base_url: str
    expected_input_chunk_count: int
    expected_input_character_count: int
    cloud_data_confirmed: bool


class AnalysisRepository(Protocol):
    def create(
        self,
        *,
        run_id: str,
        workspace_id: str,
        document_id: str,
        version_id: str,
        provider: ModelProvider,
        model_name: str,
        base_url: str,
        input_chunk_count: int,
        input_character_count: int,
        cloud_data_confirmed_at: datetime | None,
        created_at: datetime,
    ) -> AnalysisRun: ...

    def list(self, workspace_id: str, document_id: str) -> list[AnalysisRun]: ...

    def get(self, workspace_id: str, run_id: str) -> AnalysisRun | None: ...

    def get_any(self, run_id: str) -> AnalysisRun | None: ...


class AnalysisWorker(Protocol):
    def launch(self, request: AnalysisTaskRequest) -> None: ...

    def cancel(self, run_id: str) -> None: ...

    def recover_interrupted(self) -> None: ...


class AnalysisUseCases(Protocol):
    def start(
        self, workspace_id: str, document_id: str, input: AnalysisStartInput
    ) -> AnalysisRun: ...

    def list_runs(self, workspace_id: str, document_id: str) -> list[AnalysisRun]: ...

    def get_run(self, workspace_id: str, run_id: str) -> AnalysisRun: ...

    def cancel(self, workspace_id: str, run_id: str) -> AnalysisRun: ...


class AnalysisService:
    def __init__(
        self,
        workspaces: WorkspaceReader,
        documents: DocumentReader,
        settings: SettingsReader,
        runs: AnalysisRepository,
        worker: AnalysisWorker,
        credentials: CredentialStatusReader,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._workspaces = workspaces
        self._documents = documents
        self._settings = settings
        self._runs = runs
        self._worker = worker
        self._credentials = credentials
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))
        self._recovered = False
        self._recovery_lock = Lock()

    def start(self, workspace_id: str, document_id: str, input: AnalysisStartInput) -> AnalysisRun:
        self._workspace(workspace_id)
        self._ensure_recovered()
        document = self._documents.get(workspace_id, document_id)
        if document is None:
            raise AppError(code="DOCUMENT_NOT_FOUND", message="未找到该文档。", status_code=404)
        if document.latest_version.status != "passed":
            raise AppError(
                code="ANALYSIS_DOCUMENT_NOT_READY",
                message="文档解析成功后才能开始需求分析。",
                status_code=409,
            )
        chunks = self._documents.list_chunks(document.latest_version.id)
        if not chunks:
            raise AppError(
                code="ANALYSIS_CITATIONS_UNAVAILABLE",
                message="该文档没有可用于分析的引用片段。",
                status_code=409,
            )
        input_character_count = sum(len(chunk.text) for chunk in chunks)
        input_chunk_count = len(chunks)
        settings = self._settings.get()
        supported_local = (
            settings.model_mode is ModelMode.LOCAL
            and settings.model_provider is ModelProvider.OLLAMA
        )
        supported_cloud = (
            settings.model_mode is ModelMode.CLOUD
            and settings.model_provider is ModelProvider.OPENAI_COMPATIBLE
        )
        if not supported_local and not supported_cloud:
            raise AppError(
                code="ANALYSIS_MODEL_CONFIGURATION_UNSUPPORTED",
                message="当前模型模式与 Provider 不匹配。",
                status_code=409,
            )
        if settings.model_name is None:
            raise AppError(
                code="ANALYSIS_MODEL_NOT_CONFIGURED",
                message="请先在设置中填写模型名称。",
                status_code=409,
            )
        if (
            input.expected_version_id != document.latest_version.id
            or input.expected_provider is not settings.model_provider
            or input.expected_model_name != settings.model_name
            or input.expected_base_url != settings.base_url
            or input.expected_input_chunk_count != input_chunk_count
            or input.expected_input_character_count != input_character_count
        ):
            raise AppError(
                code="ANALYSIS_CONTEXT_CHANGED",
                message="文档版本、输入范围或模型配置已变化, 请刷新后重新确认。",
                status_code=409,
            )
        if input_character_count > MAX_ANALYSIS_INPUT_CHARS:
            raise AppError(
                code="ANALYSIS_INPUT_TOO_LARGE",
                message="文档内容超过当前分析上限, 后续需启用检索切片。",
                status_code=413,
            )
        cloud_data_confirmed_at: datetime | None = None
        created_at = self._clock()
        if supported_local:
            if input.cloud_data_confirmed:
                raise AppError(
                    code="ANALYSIS_CONFIRMATION_INVALID",
                    message="本地分析不得记录云端外发确认。",
                    status_code=422,
                )
        else:
            if not settings.cloud_data_consent:
                raise AppError(
                    code="ANALYSIS_CLOUD_CONSENT_REQUIRED",
                    message="请先在设置中同意云端数据外发范围。",
                    status_code=409,
                )
            if not input.cloud_data_confirmed:
                raise AppError(
                    code="ANALYSIS_CLOUD_CONFIRMATION_REQUIRED",
                    message="每次向云端发送文档前都需要明确确认。",
                    status_code=409,
                )
            if not self._credentials.status():
                raise AppError(
                    code="ANALYSIS_CREDENTIAL_NOT_CONFIGURED",
                    message="请先在系统凭据库中保存云端模型凭据。",
                    status_code=409,
                )
            cloud_data_confirmed_at = created_at
        run = self._runs.create(
            run_id=self._id_factory(),
            workspace_id=workspace_id,
            document_id=document.id,
            version_id=document.latest_version.id,
            provider=settings.model_provider,
            model_name=settings.model_name,
            base_url=settings.base_url,
            input_chunk_count=input_chunk_count,
            input_character_count=input_character_count,
            cloud_data_confirmed_at=cloud_data_confirmed_at,
            created_at=created_at,
        )
        self._worker.launch(AnalysisTaskRequest(run.id))
        return run

    def list_runs(self, workspace_id: str, document_id: str) -> list[AnalysisRun]:
        self._workspace(workspace_id)
        self._ensure_recovered()
        if self._documents.get(workspace_id, document_id) is None:
            raise AppError(code="DOCUMENT_NOT_FOUND", message="未找到该文档。", status_code=404)
        return self._runs.list(workspace_id, document_id)

    def get_run(self, workspace_id: str, run_id: str) -> AnalysisRun:
        self._workspace(workspace_id)
        self._ensure_recovered()
        run = self._runs.get(workspace_id, run_id)
        if run is None:
            raise AppError(
                code="ANALYSIS_RUN_NOT_FOUND", message="未找到该分析任务。", status_code=404
            )
        return run

    def cancel(self, workspace_id: str, run_id: str) -> AnalysisRun:
        run = self.get_run(workspace_id, run_id)
        if not run.can_cancel:
            raise AppError(
                code="ANALYSIS_RUN_FINISHED", message="该分析任务已经结束。", status_code=409
            )
        self._worker.cancel(run_id)
        return self._runs.get(workspace_id, run_id) or run

    def _workspace(self, workspace_id: str) -> Workspace:
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise AppError(
                code="WORKSPACE_NOT_FOUND", message="未找到该工作空间。", status_code=404
            )
        return workspace

    def _ensure_recovered(self) -> None:
        if self._recovered:
            return
        with self._recovery_lock:
            if not self._recovered:
                self._worker.recover_interrupted()
                self._recovered = True
