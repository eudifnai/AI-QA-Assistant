from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel

from backend.app.domain.analysis import ANALYSIS_DIMENSIONS, AnalysisOutput, AnalysisRun
from backend.app.domain.settings import ModelProvider
from backend.app.infrastructure.analysis import SqlModelAnalysisRepository
from backend.app.infrastructure.database import create_database_engine
from backend.app.infrastructure.documents import (
    DocumentChunkRecord,
    DocumentRecord,
    DocumentVersionRecord,
)
from backend.app.infrastructure.workspaces import WorkspaceRecord

NOW = datetime(2026, 8, 12, 3, 0, tzinfo=UTC)


def repository(tmp_path: Path) -> SqlModelAnalysisRepository:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'analysis.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            WorkspaceRecord(
                id="workspace-1",
                name="支付",
                name_key="支付",
                path=str(tmp_path),
                path_key=str(tmp_path).casefold(),
                created_at=NOW,
                last_opened_at=NOW,
            )
        )
        session.add(
            DocumentRecord(
                id="document-1",
                workspace_id="workspace-1",
                name="requirements.md",
                relative_path="requirements.md",
                path_key="requirements.md",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.add(
            DocumentVersionRecord(
                id="version-1",
                document_id="document-1",
                workspace_id="workspace-1",
                version_number=1,
                sha256="a" * 64,
                size_bytes=20,
                status="passed",
                parsed_text="必须支持退款。",
                created_at=NOW,
            )
        )
        session.add(
            DocumentChunkRecord(
                id="chunk-1",
                version_id="version-1",
                ordinal=1,
                source_type="lines",
                source_start=1,
                source_end=1,
                start_offset=0,
                end_offset=7,
                text="必须支持退款。",
            )
        )
        session.commit()
    return SqlModelAnalysisRepository(engine)


def create_run(runs: SqlModelAnalysisRepository, run_id: str) -> AnalysisRun:
    return runs.create(
        run_id=run_id,
        workspace_id="workspace-1",
        document_id="document-1",
        version_id="version-1",
        provider=ModelProvider.OLLAMA,
        model_name="qwen3:8b",
        base_url="http://127.0.0.1:11434",
        input_chunk_count=1,
        input_character_count=7,
        cloud_data_confirmed_at=None,
        created_at=NOW,
    )


def valid_output() -> AnalysisOutput:
    return AnalysisOutput.model_validate(
        {
            "overall_score": 82,
            "dimension_scores": [
                {"dimension": dimension, "score": 82, "summary": "符合预期"}
                for dimension in ANALYSIS_DIMENSIONS
            ],
            "issues": [
                {
                    "dimension": "clarity",
                    "severity": "medium",
                    "title": "退款期限不清晰",
                    "description": "没有说明退款完成期限。",
                    "impact": "无法设计时间边界测试。",
                    "suggestion": "补充最长退款时间。",
                    "question": "退款应在多久内完成?",
                    "citation_chunk_ids": ["chunk-1"],
                }
            ],
        }
    )


def test_repository_persists_normalized_analysis_with_stable_citations(tmp_path: Path) -> None:
    runs = repository(tmp_path)
    create_run(runs, "run-passed")

    execution = runs.load_execution_input("run-passed")
    runs.mark_running("run-passed", pid=42, now=NOW)
    runs.mark_generating("run-passed", now=NOW)
    runs.mark_passed("run-passed", output=valid_output(), now=NOW)
    result = runs.get("workspace-1", "run-passed")

    assert execution is not None
    assert execution.provider is ModelProvider.OLLAMA
    assert execution.chunks[0].locator == "第 1 行"
    assert result is not None
    assert result.status == "passed"
    assert result.base_url == "http://127.0.0.1:11434"
    assert result.input_chunk_count == 1
    assert result.input_character_count == 7
    assert result.cloud_data_confirmed_at is None
    assert result.overall_score == 82
    assert {score.dimension for score in result.scores} == set(ANALYSIS_DIMENSIONS)
    assert result.issues[0].citations[0].chunk_id == "chunk-1"
    assert result.issues[0].citations[0].text == "必须支持退款。"


@pytest.mark.parametrize(
    ("terminal", "expected_code"),
    [
        ("failed", "MODEL_FAILED"),
        ("error", "WORKER_CRASHED"),
        ("cancelled", None),
        ("timeout", "ANALYSIS_TIMEOUT"),
    ],
)
def test_repository_records_terminal_worker_outcomes(
    tmp_path: Path, terminal: str, expected_code: str | None
) -> None:
    runs = repository(tmp_path)
    create_run(runs, f"run-{terminal}")
    runs.mark_running(f"run-{terminal}", pid=42, now=NOW)

    if terminal == "failed":
        runs.mark_failed(f"run-{terminal}", code="MODEL_FAILED", message="模型失败。", now=NOW)
    elif terminal == "error":
        runs.mark_error(f"run-{terminal}", code="WORKER_CRASHED", message="进程崩溃。", now=NOW)
    elif terminal == "cancelled":
        runs.mark_cancelled(f"run-{terminal}", now=NOW)
    else:
        runs.mark_timeout(f"run-{terminal}", now=NOW)

    result = runs.get("workspace-1", f"run-{terminal}")
    assert result is not None
    assert result.status == terminal
    assert result.progress == 100
    assert result.error_code == expected_code


def test_repository_recovers_queued_and_running_jobs_after_restart(tmp_path: Path) -> None:
    runs = repository(tmp_path)
    create_run(runs, "run-queued")
    create_run(runs, "run-running")
    create_run(runs, "run-finished")
    runs.mark_running("run-running", pid=42, now=NOW)
    runs.mark_cancelled("run-finished", now=NOW)

    runs.recover_interrupted(now=NOW)

    assert runs.get_any("run-queued").error_code == "ANALYSIS_WORKER_INTERRUPTED"  # type: ignore[union-attr]
    assert runs.get_any("run-running").status == "error"  # type: ignore[union-attr]
    assert runs.get_any("run-finished").status == "cancelled"  # type: ignore[union-attr]
