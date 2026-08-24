from datetime import UTC, datetime
from typing import NoReturn

from fastapi.testclient import TestClient

from backend.app.application.analysis import AnalysisStartInput, AnalysisUseCases
from backend.app.domain.analysis import AnalysisRun
from backend.app.domain.settings import ModelProvider
from backend.app.main import create_app

NOW = datetime(2026, 8, 12, 1, 0, tzinfo=UTC)
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


class StubAnalysis(AnalysisUseCases):
    received: AnalysisStartInput | None = None

    def start(self, workspace_id: str, document_id: str, input: AnalysisStartInput) -> AnalysisRun:
        self.received = input
        return RUN

    def list_runs(self, workspace_id: str, document_id: str) -> list[AnalysisRun]:
        return [RUN]

    def get_run(self, workspace_id: str, run_id: str) -> AnalysisRun:
        return RUN

    def cancel(self, workspace_id: str, run_id: str) -> AnalysisRun:
        return RUN


class CrashingAnalysis(StubAnalysis):
    def start(self, workspace_id: str, document_id: str, input: AnalysisStartInput) -> NoReturn:
        raise RuntimeError("sensitive prompt detail")


START_BODY = {
    "expected_version_id": "version-1",
    "expected_provider": "ollama",
    "expected_model_name": "qwen3:8b",
    "expected_base_url": "http://127.0.0.1:11434",
    "expected_input_chunk_count": 1,
    "expected_input_character_count": 4,
    "cloud_data_confirmed": False,
}


def test_analysis_start_list_get_and_cancel_api() -> None:
    service = StubAnalysis()
    app = create_app(analysis_service=service)
    with TestClient(app) as client:
        started = client.post(
            "/api/workspaces/workspace-1/documents/document-1/analysis-runs",
            json=START_BODY,
        )
        listed = client.get("/api/workspaces/workspace-1/documents/document-1/analysis-runs")
        fetched = client.get("/api/workspaces/workspace-1/analysis-runs/run-1")
        cancelled = client.post("/api/workspaces/workspace-1/analysis-runs/run-1/cancel")

    assert started.status_code == 202
    assert started.json()["provider"] == "ollama"
    assert started.json()["base_url"] == "http://127.0.0.1:11434"
    assert started.json()["input_character_count"] == 4
    assert service.received == AnalysisStartInput(
        expected_version_id="version-1",
        expected_provider=ModelProvider.OLLAMA,
        expected_model_name="qwen3:8b",
        expected_base_url="http://127.0.0.1:11434",
        expected_input_chunk_count=1,
        expected_input_character_count=4,
        cloud_data_confirmed=False,
    )
    assert listed.json()[0]["id"] == "run-1"
    assert fetched.status_code == 200
    assert cancelled.status_code == 200


def test_analysis_api_redacts_unexpected_failure() -> None:
    app = create_app(analysis_service=CrashingAnalysis())
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/workspaces/workspace-1/documents/document-1/analysis-runs",
            json=START_BODY,
        )

    assert response.status_code == 500
    assert "sensitive prompt detail" not in response.text


def test_analysis_start_requires_an_explicit_snapshot_body() -> None:
    app = create_app(analysis_service=StubAnalysis())
    with TestClient(app) as client:
        response = client.post("/api/workspaces/workspace-1/documents/document-1/analysis-runs")

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_analysis_start_requires_input_scope_snapshot_fields() -> None:
    app = create_app(analysis_service=StubAnalysis())
    incomplete = {
        key: value
        for key, value in START_BODY.items()
        if key not in {"expected_input_chunk_count", "expected_input_character_count"}
    }
    with TestClient(app) as client:
        response = client.post(
            "/api/workspaces/workspace-1/documents/document-1/analysis-runs",
            json=incomplete,
        )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
