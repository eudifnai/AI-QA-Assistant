from datetime import UTC, datetime

import pytest

from backend.app.application.analysis import AnalysisService, AnalysisStartInput
from backend.app.core.errors import AppError
from backend.app.domain.analysis import AnalysisRun, AnalysisTaskRequest
from backend.app.domain.document import DocumentChunk, DocumentItem, DocumentJob, DocumentVersion
from backend.app.domain.settings import AppSettings, ModelMode, ModelProvider, Theme
from backend.app.domain.workspace import Workspace

NOW = datetime(2026, 8, 12, 1, 0, tzinfo=UTC)
WORKSPACE = Workspace("workspace-1", "支付", "C:/qa/pay", NOW, NOW)
VERSION = DocumentVersion(
    "version-1", "document-1", 1, "a" * 64, 100, "passed", "需求文本", None, None, NOW
)
JOB = DocumentJob("job-1", "version-1", "passed", 100, None, None, NOW, NOW, NOW)
DOCUMENT = DocumentItem(
    "document-1", "workspace-1", "requirements.md", "requirements.md", NOW, NOW, VERSION, JOB
)
CHUNK = DocumentChunk("chunk-1", "version-1", 1, "lines", 1, 2, 0, 4, "需求文本")
SETTINGS = AppSettings(
    Theme.LIGHT,
    ModelMode.LOCAL,
    ModelProvider.OLLAMA,
    "qwen3:8b",
    "http://127.0.0.1:11434",
    False,
    NOW,
)
RUN = AnalysisRun(
    "run-1",
    "workspace-1",
    "document-1",
    "version-1",
    ModelProvider.OLLAMA,
    "qwen3:8b",
    "http://127.0.0.1:11434",
    1,
    4,
    None,
    "queued",
    0,
    None,
    None,
    None,
    NOW,
    None,
    None,
    (),
    (),
)


class Workspaces:
    def get(self, workspace_id: str) -> Workspace | None:
        return WORKSPACE if workspace_id == WORKSPACE.id else None


class Documents:
    def __init__(self) -> None:
        self.value: DocumentItem | None = DOCUMENT
        self.chunks: list[DocumentChunk] = [CHUNK]

    def get(self, workspace_id: str, document_id: str) -> DocumentItem | None:
        return self.value if document_id == "document-1" else None

    def list_chunks(self, version_id: str) -> list[DocumentChunk]:
        return self.chunks


class Settings:
    value = SETTINGS

    def get(self) -> AppSettings:
        return self.value


class Runs:
    def __init__(self) -> None:
        self.created: dict[str, object] | None = None

    def create(self, **values: object) -> AnalysisRun:
        self.created = values
        return RUN

    def list(self, workspace_id: str, document_id: str) -> list[AnalysisRun]:
        return [RUN]

    def get(self, workspace_id: str, run_id: str) -> AnalysisRun | None:
        return RUN if workspace_id == "workspace-1" and run_id == "run-1" else None

    def get_any(self, run_id: str) -> AnalysisRun | None:
        return RUN if run_id == "run-1" else None


class Worker:
    request: AnalysisTaskRequest | None = None
    cancelled: str | None = None
    recovered = False

    def launch(self, request: AnalysisTaskRequest) -> None:
        self.request = request

    def cancel(self, run_id: str) -> None:
        self.cancelled = run_id

    def recover_interrupted(self) -> None:
        self.recovered = True


class Credentials:
    def __init__(self, configured: bool = True) -> None:
        self.configured = configured
        self.status_calls = 0

    def status(self) -> bool:
        self.status_calls += 1
        return self.configured


def start_input(
    settings: AppSettings = SETTINGS,
    *,
    confirmed: bool = False,
    version_id: str = VERSION.id,
    input_chunk_count: int = 1,
    input_character_count: int = 4,
) -> AnalysisStartInput:
    return AnalysisStartInput(
        expected_version_id=version_id,
        expected_provider=settings.model_provider,
        expected_model_name=settings.model_name or "missing-model",
        expected_base_url=settings.base_url,
        expected_input_chunk_count=input_chunk_count,
        expected_input_character_count=input_character_count,
        cloud_data_confirmed=confirmed,
    )


def service(
    *,
    documents: Documents | None = None,
    settings: Settings | None = None,
    worker: Worker | None = None,
    credentials: Credentials | None = None,
    runs: Runs | None = None,
) -> AnalysisService:
    return AnalysisService(
        Workspaces(),
        documents or Documents(),
        settings or Settings(),
        runs or Runs(),
        worker or Worker(),
        credentials or Credentials(),
        clock=lambda: NOW,
        id_factory=lambda: "run-1",
    )


def test_start_analysis_freezes_local_model_and_launches_worker() -> None:
    worker = Worker()
    runs = Runs()

    run = service(worker=worker, runs=runs).start("workspace-1", "document-1", start_input())

    assert run.status == "queued"
    assert worker.recovered is True
    assert worker.request == AnalysisTaskRequest("run-1")
    assert runs.created is not None
    assert runs.created["provider"] is ModelProvider.OLLAMA
    assert runs.created["input_chunk_count"] == 1
    assert runs.created["input_character_count"] == 4
    assert runs.created["cloud_data_confirmed_at"] is None


def test_local_analysis_does_not_touch_cloud_credentials() -> None:
    class UnexpectedCredentials(Credentials):
        def status(self) -> bool:
            raise AssertionError("local analysis must not access keyring")

    service(credentials=UnexpectedCredentials()).start("workspace-1", "document-1", start_input())


def test_start_analysis_rejects_unparsed_document_missing_model_and_cloud_mode() -> None:
    documents = Documents()
    documents.value = DocumentItem(
        DOCUMENT.id,
        DOCUMENT.workspace_id,
        DOCUMENT.name,
        DOCUMENT.relative_path,
        DOCUMENT.created_at,
        DOCUMENT.updated_at,
        DocumentVersion(
            VERSION.id,
            VERSION.document_id,
            VERSION.version_number,
            VERSION.sha256,
            VERSION.size_bytes,
            "failed",
            None,
            "FAILED",
            "失败",
            NOW,
        ),
        JOB,
    )
    with pytest.raises(AppError) as unparsed:
        service(documents=documents).start("workspace-1", "document-1", start_input())
    assert unparsed.value.code == "ANALYSIS_DOCUMENT_NOT_READY"

    missing_model = Settings()
    missing_model.value = AppSettings(
        Theme.LIGHT,
        ModelMode.LOCAL,
        ModelProvider.OLLAMA,
        None,
        "http://127.0.0.1:11434",
        False,
        NOW,
    )
    with pytest.raises(AppError) as missing:
        service(settings=missing_model).start(
            "workspace-1", "document-1", start_input(missing_model.value)
        )
    assert missing.value.code == "ANALYSIS_MODEL_NOT_CONFIGURED"

    cloud = Settings()
    cloud.value = AppSettings(
        Theme.LIGHT,
        ModelMode.CLOUD,
        ModelProvider.OPENAI_COMPATIBLE,
        "cloud-model",
        "https://models.example.com/v1",
        True,
        NOW,
    )
    with pytest.raises(AppError) as confirmation_error:
        service(settings=cloud).start("workspace-1", "document-1", start_input(cloud.value))
    assert confirmation_error.value.code == "ANALYSIS_CLOUD_CONFIRMATION_REQUIRED"


def test_cloud_analysis_requires_credential_and_persists_per_run_confirmation() -> None:
    cloud = Settings()
    cloud.value = AppSettings(
        Theme.LIGHT,
        ModelMode.CLOUD,
        ModelProvider.OPENAI_COMPATIBLE,
        "cloud-model",
        "https://models.example.com/v1",
        True,
        NOW,
    )
    missing_credentials = Credentials(configured=False)
    with pytest.raises(AppError) as missing:
        service(settings=cloud, credentials=missing_credentials).start(
            "workspace-1", "document-1", start_input(cloud.value, confirmed=True)
        )
    assert missing.value.code == "ANALYSIS_CREDENTIAL_NOT_CONFIGURED"

    credentials = Credentials()
    runs = Runs()
    worker = Worker()
    service(
        settings=cloud,
        credentials=credentials,
        runs=runs,
        worker=worker,
    ).start("workspace-1", "document-1", start_input(cloud.value, confirmed=True))

    assert credentials.status_calls == 1
    assert worker.request == AnalysisTaskRequest("run-1")
    assert runs.created is not None
    assert runs.created["provider"] is ModelProvider.OPENAI_COMPATIBLE
    assert runs.created["cloud_data_confirmed_at"] == NOW


@pytest.mark.parametrize(
    "input_override",
    [
        {"expected_version_id": "version-old"},
        {"expected_provider": ModelProvider.OPENAI_COMPATIBLE},
        {"expected_model_name": "other-model"},
        {"expected_base_url": "http://127.0.0.1:9999"},
    ],
)
def test_start_analysis_rejects_stale_confirmation_snapshot(
    input_override: dict[str, object],
) -> None:
    values: dict[str, object] = {
        "expected_version_id": VERSION.id,
        "expected_provider": SETTINGS.model_provider,
        "expected_model_name": SETTINGS.model_name,
        "expected_base_url": SETTINGS.base_url,
        "expected_input_chunk_count": 1,
        "expected_input_character_count": 4,
        "cloud_data_confirmed": False,
    }
    values.update(input_override)

    with pytest.raises(AppError) as changed:
        service().start("workspace-1", "document-1", AnalysisStartInput(**values))  # type: ignore[arg-type]

    assert changed.value.code == "ANALYSIS_CONTEXT_CHANGED"


@pytest.mark.parametrize(
    ("input_chunk_count", "input_character_count"),
    [(2, 4), (1, 5)],
)
def test_start_analysis_rejects_changed_input_scope(
    input_chunk_count: int,
    input_character_count: int,
) -> None:
    with pytest.raises(AppError) as changed:
        service().start(
            "workspace-1",
            "document-1",
            start_input(
                input_chunk_count=input_chunk_count,
                input_character_count=input_character_count,
            ),
        )

    assert changed.value.code == "ANALYSIS_CONTEXT_CHANGED"
    assert changed.value.status_code == 409


def test_local_analysis_rejects_cloud_confirmation_flag() -> None:
    with pytest.raises(AppError) as invalid:
        service().start("workspace-1", "document-1", start_input(confirmed=True))

    assert invalid.value.code == "ANALYSIS_CONFIRMATION_INVALID"


def test_start_analysis_rejects_oversized_input_without_truncation() -> None:
    documents = Documents()
    documents.chunks = [
        DocumentChunk(
            "chunk-large",
            VERSION.id,
            1,
            "document",
            1,
            1,
            0,
            200_001,
            "x" * 200_001,
        )
    ]

    with pytest.raises(AppError) as too_large:
        service(documents=documents).start(
            "workspace-1",
            "document-1",
            start_input(input_character_count=200_001),
        )

    assert too_large.value.code == "ANALYSIS_INPUT_TOO_LARGE"
    assert too_large.value.status_code == 413


def test_analysis_scope_and_cancel_rules() -> None:
    worker = Worker()
    subject = service(worker=worker)

    assert subject.list_runs("workspace-1", "document-1") == [RUN]
    assert subject.get_run("workspace-1", "run-1") == RUN
    subject.cancel("workspace-1", "run-1")
    assert worker.cancelled == "run-1"

    with pytest.raises(AppError) as missing:
        subject.get_run("workspace-1", "missing")
    assert missing.value.code == "ANALYSIS_RUN_NOT_FOUND"
