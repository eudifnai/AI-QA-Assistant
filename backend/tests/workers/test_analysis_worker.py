import json
import logging
import multiprocessing
from multiprocessing.process import BaseProcess
from typing import cast

import pytest

from backend.app.application.credentials import CredentialStoreUnavailableError
from backend.app.domain.analysis import (
    ANALYSIS_DIMENSIONS,
    AnalysisExecutionInput,
    AnalysisOutput,
    AnalysisTaskRequest,
)
from backend.app.domain.settings import ModelProvider
from backend.app.infrastructure.analysis import SqlModelAnalysisRepository
from backend.app.infrastructure.model_providers import (
    ModelProviderError,
    OllamaChatModelProvider,
    OpenAICompatibleChatModelProvider,
)
from backend.app.workers.analysis import (
    AnalysisOutputError,
    AnalysisWorkerManager,
    _create_provider,
    _model_failure,
    generate_validated_output,
)


def output(chunk_id: str = "chunk-1") -> str:
    return json.dumps(
        {
            "overall_score": 80,
            "dimension_scores": [
                {"dimension": dimension, "score": 80, "summary": "摘要"}
                for dimension in ANALYSIS_DIMENSIONS
            ],
            "issues": [
                {
                    "dimension": "clarity",
                    "severity": "medium",
                    "title": "描述模糊",
                    "description": "描述不明确",
                    "impact": "影响测试设计",
                    "suggestion": "补充约束",
                    "question": "具体约束是什么?",
                    "citation_chunk_ids": [chunk_id],
                }
            ],
        }
    )


class Provider:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.prompts: list[str] = []

    def generate(self, prompt: str, response_schema: dict[str, object]) -> str:
        self.prompts.append(prompt)
        assert response_schema == AnalysisOutput.model_json_schema()
        return next(self.responses)


def test_analysis_worker_retries_invalid_schema_once() -> None:
    provider = Provider(["not-json", output()])

    result = generate_validated_output(provider, "原始提示", {"chunk-1"})

    assert result.overall_score == 80
    assert len(provider.prompts) == 2
    assert "上一次输出未通过" in provider.prompts[1]


def test_analysis_worker_fails_after_retry_or_unknown_citation() -> None:
    with pytest.raises(AnalysisOutputError):
        generate_validated_output(Provider(["bad", "still-bad"]), "提示", {"chunk-1"})
    with pytest.raises(AnalysisOutputError):
        generate_validated_output(Provider([output("other"), output("other")]), "提示", {"chunk-1"})


class UnavailableProvider:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, prompt: str, response_schema: dict[str, object]) -> str:
        self.calls += 1
        raise ModelProviderError("unavailable")


def test_analysis_worker_does_not_retry_transport_failures() -> None:
    provider = UnavailableProvider()

    with pytest.raises(ModelProviderError, match="unavailable"):
        generate_validated_output(provider, "提示", {"chunk-1"})

    assert provider.calls == 1


class CredentialStore:
    def __init__(
        self, secret: str | None = "cloud-test-secret", *, unavailable: bool = False
    ) -> None:
        self.secret = secret
        self.unavailable = unavailable

    def get(self) -> str | None:
        if self.unavailable:
            raise CredentialStoreUnavailableError
        return self.secret


def execution(provider: ModelProvider) -> AnalysisExecutionInput:
    return AnalysisExecutionInput(
        run_id="run-1",
        provider=provider,
        base_url=(
            "http://127.0.0.1:11434" if provider == "ollama" else "https://models.example.test/v1"
        ),
        model_name="quality-model",
        chunks=(),
    )


def test_worker_selects_provider_without_reading_keyring_for_local() -> None:
    keyring_reads = 0

    def credential_store_factory() -> CredentialStore:
        nonlocal keyring_reads
        keyring_reads += 1
        return CredentialStore()

    provider = _create_provider(
        execution(ModelProvider.OLLAMA),
        20,
        credential_store_factory,
    )

    assert isinstance(provider, OllamaChatModelProvider)
    assert keyring_reads == 0


def test_worker_reads_cloud_credential_inside_provider_factory() -> None:
    provider = _create_provider(
        execution(ModelProvider.OPENAI_COMPATIBLE),
        20,
        lambda: CredentialStore(),
    )

    assert isinstance(provider, OpenAICompatibleChatModelProvider)


@pytest.mark.parametrize(
    ("store", "reason"),
    [
        (CredentialStore(None), "credential_not_configured"),
        (CredentialStore(unavailable=True), "credential_store_unavailable"),
    ],
)
def test_worker_maps_cloud_credential_failures(store: CredentialStore, reason: str) -> None:
    with pytest.raises(ModelProviderError, match=reason):
        _create_provider(execution(ModelProvider.OPENAI_COMPATIBLE), 20, lambda: store)


def test_worker_does_not_fallback_for_unknown_provider() -> None:
    with pytest.raises(ModelProviderError, match="provider_not_supported"):
        _create_provider(
            execution(cast(ModelProvider, "unknown")),
            20,
            lambda: CredentialStore(),
        )


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        (
            "credential_not_configured",
            ("ANALYSIS_CREDENTIAL_NOT_CONFIGURED", "未配置云端模型凭据。"),
        ),
        (
            "credential_store_unavailable",
            ("ANALYSIS_CREDENTIAL_STORE_UNAVAILABLE", "操作系统凭据库当前不可用。"),
        ),
        ("auth_failed", ("ANALYSIS_MODEL_AUTH_FAILED", "云端模型凭据无效或无权访问。")),
        ("rate_limited", ("ANALYSIS_MODEL_RATE_LIMITED", "云端模型请求过于频繁。请稍后重试。")),
        ("request_failed", ("ANALYSIS_MODEL_REQUEST_FAILED", "云端模型请求失败。")),
    ],
)
def test_worker_uses_safe_cloud_failure_messages(
    reason: str,
    expected: tuple[str, str],
) -> None:
    assert _model_failure("openai_compatible", reason) == expected


class FailingProcess:
    def start(self) -> None:
        raise RuntimeError("sensitive worker start detail")


class ProcessContext:
    def Process(self, **_kwargs: object) -> FailingProcess:
        return FailingProcess()


class ErrorRecordingRepository:
    def __init__(self) -> None:
        self.errors: list[tuple[str, str, str]] = []
        self.cancelled: list[str] = []
        self.timed_out: list[str] = []

    def mark_error(self, run_id: str, *, code: str, message: str, now: object) -> None:
        self.errors.append((run_id, code, message))

    def mark_cancelled(self, run_id: str, *, now: object) -> None:
        self.cancelled.append(run_id)

    def mark_timeout(self, run_id: str, *, now: object) -> None:
        self.timed_out.append(run_id)


class ManagedProcess:
    def __init__(self, *, alive: bool, exitcode: int | None) -> None:
        self.alive = alive
        self.exitcode = exitcode
        self.terminate_calls = 0
        self.join_timeouts: list[float | None] = []

    def join(self, timeout: float | None = None) -> None:
        self.join_timeouts.append(timeout)

    def is_alive(self) -> bool:
        return self.alive

    def terminate(self) -> None:
        self.terminate_calls += 1
        self.alive = False
        self.exitcode = -15


def worker_manager(
    monkeypatch: pytest.MonkeyPatch,
    repository: ErrorRecordingRepository,
) -> AnalysisWorkerManager:
    monkeypatch.setattr(multiprocessing, "get_context", lambda _method: ProcessContext())
    return AnalysisWorkerManager(
        cast(SqlModelAnalysisRepository, repository),
        database_url="sqlite:///unused.db",
        timeout_seconds=10,
        model_timeout_seconds=5,
    )


def test_worker_manager_marks_run_error_when_process_start_fails(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    repository = ErrorRecordingRepository()
    manager = worker_manager(monkeypatch, repository)

    with (
        caplog.at_level(logging.ERROR, logger="backend.app.workers.analysis"),
        pytest.raises(RuntimeError, match="sensitive worker start detail"),
    ):
        manager.launch(AnalysisTaskRequest("run-start-failure"))

    assert repository.errors == [
        (
            "run-start-failure",
            "ANALYSIS_WORKER_START_FAILED",
            "无法启动需求分析进程。",
        )
    ]
    assert "sensitive worker start detail" not in caplog.text
    record = caplog.records[-1]
    assert record.getMessage() == "Analysis worker start failed"
    assert record.run_id == "run-start-failure"  # type: ignore[attr-defined]
    assert record.error_type == "RuntimeError"  # type: ignore[attr-defined]


def test_worker_manager_cancel_terminates_live_process_and_clears_tracking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = ErrorRecordingRepository()
    manager = worker_manager(monkeypatch, repository)
    process = ManagedProcess(alive=True, exitcode=None)
    manager._processes["run-cancel"] = cast(BaseProcess, process)

    manager.cancel("run-cancel")

    assert repository.cancelled == ["run-cancel"]
    assert process.terminate_calls == 1
    assert process.join_timeouts == [5]
    assert "run-cancel" not in manager._processes


def test_worker_manager_supervisor_terminates_timeout_and_clears_tracking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = ErrorRecordingRepository()
    manager = worker_manager(monkeypatch, repository)
    process = ManagedProcess(alive=True, exitcode=None)
    manager._processes["run-timeout"] = cast(BaseProcess, process)

    manager._supervise("run-timeout", cast(BaseProcess, process))

    assert process.terminate_calls == 1
    assert process.join_timeouts == [10, 5]
    assert repository.timed_out == ["run-timeout"]
    assert repository.errors == []
    assert "run-timeout" not in manager._processes


def test_worker_manager_supervisor_marks_nonzero_exit_as_crashed_and_clears_tracking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = ErrorRecordingRepository()
    manager = worker_manager(monkeypatch, repository)
    process = ManagedProcess(alive=False, exitcode=7)
    manager._processes["run-crashed"] = cast(BaseProcess, process)

    manager._supervise("run-crashed", cast(BaseProcess, process))

    assert process.terminate_calls == 0
    assert process.join_timeouts == [10]
    assert repository.errors == [
        ("run-crashed", "ANALYSIS_WORKER_CRASHED", "需求分析进程意外退出。")
    ]
    assert "run-crashed" not in manager._processes


def test_worker_manager_supervisor_does_not_overwrite_cancelled_terminal_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = ErrorRecordingRepository()
    manager = worker_manager(monkeypatch, repository)
    process = ManagedProcess(alive=True, exitcode=None)
    manager._processes["run-cancel-race"] = cast(BaseProcess, process)

    manager.cancel("run-cancel-race")
    manager._supervise("run-cancel-race", cast(BaseProcess, process))

    assert repository.cancelled == ["run-cancel-race"]
    assert repository.errors == []
    assert repository.timed_out == []
    assert "run-cancel-race" not in manager._processes
