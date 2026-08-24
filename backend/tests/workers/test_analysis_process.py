import json
import os
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel

from backend.app.domain.analysis import ANALYSIS_DIMENSIONS, AnalysisTaskRequest
from backend.app.domain.settings import ModelProvider
from backend.app.infrastructure.analysis import AnalysisRunRecord, SqlModelAnalysisRepository
from backend.app.infrastructure.database import create_database_engine
from backend.app.infrastructure.documents import (
    DocumentChunkRecord,
    DocumentRecord,
    DocumentVersionRecord,
)
from backend.app.infrastructure.workspaces import WorkspaceRecord
from backend.app.workers.analysis import AnalysisWorkerManager

NOW = datetime(2026, 8, 12, 4, 0, tzinfo=UTC)


def model_output() -> str:
    return json.dumps(
        {
            "overall_score": 84,
            "dimension_scores": [
                {"dimension": dimension, "score": 84, "summary": "符合预期"}
                for dimension in ANALYSIS_DIMENSIONS
            ],
            "issues": [
                {
                    "dimension": "clarity",
                    "severity": "medium",
                    "title": "期限不清晰",
                    "description": "没有定义退款期限。",
                    "impact": "无法测试时间边界。",
                    "suggestion": "补充最长处理时间。",
                    "question": "退款应在多久内完成?",
                    "citation_chunk_ids": ["chunk-1"],
                }
            ],
        },
        ensure_ascii=False,
    )


class OllamaHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        request_length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(request_length))
        assert self.path == "/api/chat"
        assert request["stream"] is False
        assert request["format"]["type"] == "object"
        payload = json.dumps(
            {"message": {"role": "assistant", "content": model_output()}},
            ensure_ascii=False,
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *args: object) -> None:
        return


def seed_repository(
    tmp_path: Path, base_url: str
) -> tuple[SqlModelAnalysisRepository, str, Engine]:
    database_path = tmp_path / "analysis-process.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_database_engine(database_url)
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
    repository = SqlModelAnalysisRepository(engine)
    repository.create(
        run_id="run-process",
        workspace_id="workspace-1",
        document_id="document-1",
        version_id="version-1",
        provider=ModelProvider.OLLAMA,
        model_name="test-model",
        base_url=base_url,
        input_chunk_count=1,
        input_character_count=7,
        cloud_data_confirmed_at=None,
        created_at=NOW,
    )
    return repository, database_url, engine


def test_independent_analysis_worker_calls_local_provider_and_persists_result(
    tmp_path: Path,
) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), OllamaHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        repository, database_url, engine = seed_repository(
            tmp_path, f"http://127.0.0.1:{server.server_port}"
        )
        manager = AnalysisWorkerManager(
            repository,
            database_url=database_url,
            timeout_seconds=15,
            model_timeout_seconds=10,
        )

        manager.launch(AnalysisTaskRequest("run-process"))
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            run = repository.get_any("run-process")
            if run is not None and run.status in {
                "passed",
                "failed",
                "error",
                "cancelled",
                "timeout",
            }:
                break
            time.sleep(0.05)

        result = repository.get("workspace-1", "run-process")
        assert result is not None
        assert result.status == "passed"
        assert result.issues[0].citations[0].chunk_id == "chunk-1"
        with Session(engine) as session:
            record = session.get(AnalysisRunRecord, "run-process")
            assert record is not None
            assert record.pid not in (None, os.getpid())
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)
