import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar, cast

from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.domain.analysis import ANALYSIS_DIMENSIONS
from backend.app.infrastructure.database_migrations import upgrade_database
from backend.app.main import create_app

TERMINAL_STATUSES = {"passed", "failed", "error", "cancelled", "timeout"}


class CoreLoopServiceHandler(BaseHTTPRequestHandler):
    model_requests: ClassVar[list[dict[str, Any]]] = []
    product_requests: ClassVar[list[str]] = []
    request_lock = threading.Lock()

    def do_POST(self) -> None:
        if self.path != "/api/chat":
            self.send_error(404)
            return

        request_length = int(self.headers.get("Content-Length", "0"))
        request = cast(dict[str, Any], json.loads(self.rfile.read(request_length)))
        with self.request_lock:
            self.model_requests.append(request)

        prompt = cast(str, request["messages"][1]["content"])
        chunk_match = re.search(r'"chunk_id":\s*"([^"]+)"', prompt)
        assert chunk_match is not None
        model_output = {
            "overall_score": 82,
            "dimension_scores": [
                {"dimension": dimension, "score": 82, "summary": "已完成确定性评审。"}
                for dimension in ANALYSIS_DIMENSIONS
            ],
            "issues": [
                {
                    "dimension": "testability",
                    "severity": "high",
                    "title": "退款期限缺少可验证边界",
                    "description": "需求没有给出退款完成时限。",
                    "impact": "无法判定退款处理是否超时。",
                    "suggestion": "明确退款必须在 24 小时内完成。",
                    "question": "退款最长允许多久完成?",
                    "citation_chunk_ids": [chunk_match.group(1)],
                }
            ],
        }
        self._send_json(
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps(model_output, ensure_ascii=False),
                }
            }
        )

    def do_GET(self) -> None:
        if self.path != "/qa/health?client=desktop":
            self.send_error(404)
            return
        with self.request_lock:
            self.product_requests.append(self.path)
        self._send_json({"ok": True, "service": "payments"})

    def _send_json(self, value: dict[str, Any]) -> None:
        payload = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *args: object) -> None:
        return


def wait_for_terminal(
    client: TestClient,
    path: str,
    *,
    status_path: tuple[str, ...] = ("status",),
    timeout_seconds: float = 20,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_payload: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = client.get(path)
        assert response.status_code == 200, response.text
        last_payload = cast(dict[str, Any], response.json())
        status: Any = last_payload
        for key in status_path:
            status = status[key]
        if status in TERMINAL_STATUSES:
            return last_payload
        time.sleep(0.05)
    raise AssertionError(f"任务未在期限内结束: {last_payload}")


def test_core_user_loop_from_requirement_import_to_report(tmp_path: Path) -> None:
    CoreLoopServiceHandler.model_requests = []
    CoreLoopServiceHandler.product_requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), CoreLoopServiceHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    workspace_path = tmp_path / "payment-workspace"
    workspace_path.mkdir()
    requirement_path = workspace_path / "requirements.md"
    requirement_path.write_text(
        "# 退款需求\n用户提交退款后, 系统应完成退款并返回成功状态。",
        encoding="utf-8",
    )
    database_path = tmp_path / "core-loop.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    upgrade_database(database_url)
    base_url = f"http://127.0.0.1:{server.server_port}"
    settings = Settings(
        database_url=database_url,
        document_parse_timeout_seconds=20,
        analysis_timeout_seconds=20,
        model_request_timeout_seconds=10,
        http_execution_timeout_seconds=20,
    )

    try:
        with TestClient(create_app(settings=settings)) as client:
            workspace_response = client.post(
                "/api/workspaces",
                json={"name": "支付项目", "path": str(workspace_path)},
            )
            assert workspace_response.status_code == 201, workspace_response.text
            workspace = cast(dict[str, Any], workspace_response.json())
            workspace_id = cast(str, workspace["id"])

            settings_response = client.put(
                "/api/settings",
                json={
                    "theme": "light",
                    "model_mode": "local",
                    "model_provider": "ollama",
                    "model_name": "deterministic-e2e-model",
                    "base_url": base_url,
                    "cloud_data_consent": False,
                },
            )
            assert settings_response.status_code == 200, settings_response.text

            import_response = client.post(
                f"/api/workspaces/{workspace_id}/documents",
                json={"source_path": str(requirement_path)},
            )
            assert import_response.status_code == 202, import_response.text
            imported = cast(dict[str, Any], import_response.json())
            document_id = cast(str, imported["id"])
            document = wait_for_terminal(
                client,
                f"/api/workspaces/{workspace_id}/documents/{document_id}",
                status_path=("job", "status"),
            )
            assert document["job"]["status"] == "passed"
            assert document["latest_version"]["status"] == "passed"
            assert "退款需求" in document["latest_version"]["parsed_text"]

            chunks_response = client.get(
                f"/api/workspaces/{workspace_id}/documents/{document_id}/chunks"
            )
            assert chunks_response.status_code == 200, chunks_response.text
            chunks = cast(list[dict[str, Any]], chunks_response.json())
            assert chunks

            analysis_response = client.post(
                f"/api/workspaces/{workspace_id}/documents/{document_id}/analysis-runs",
                json={
                    "expected_version_id": document["latest_version"]["id"],
                    "expected_provider": "ollama",
                    "expected_model_name": "deterministic-e2e-model",
                    "expected_base_url": base_url,
                    "expected_input_chunk_count": len(chunks),
                    "expected_input_character_count": sum(len(chunk["text"]) for chunk in chunks),
                    "cloud_data_confirmed": False,
                },
            )
            assert analysis_response.status_code == 202, analysis_response.text
            analysis_id = cast(str, analysis_response.json()["id"])
            analysis = wait_for_terminal(
                client,
                f"/api/workspaces/{workspace_id}/analysis-runs/{analysis_id}",
            )
            assert analysis["status"] == "passed"
            assert analysis["overall_score"] == 82
            assert len(analysis["scores"]) == 5
            issue = analysis["issues"][0]
            assert issue["citations"][0]["chunk_id"] == chunks[0]["id"]

            review_response = client.put(
                f"/api/workspaces/{workspace_id}/analysis-runs/{analysis_id}"
                f"/issues/{issue['id']}/review",
                json={
                    "status": "accepted",
                    "answer": "按 24 小时上限补充需求, 并覆盖边界测试。",
                },
            )
            assert review_response.status_code == 200, review_response.text

            points_response = client.post(
                f"/api/workspaces/{workspace_id}/analysis-runs/{analysis_id}/test-points/generate"
            )
            assert points_response.status_code == 201, points_response.text
            point = cast(dict[str, Any], points_response.json()[0])
            confirm_point_response = client.put(
                f"/api/workspaces/{workspace_id}/analysis-runs/{analysis_id}"
                f"/test-points/{point['id']}",
                json={
                    "title": point["title"],
                    "objective": point["objective"],
                    "test_type": point["test_type"],
                    "priority": point["priority"],
                    "status": "confirmed",
                    "automation_candidate": point["automation_candidate"],
                },
            )
            assert confirm_point_response.status_code == 200, confirm_point_response.text

            cases_response = client.post(
                f"/api/workspaces/{workspace_id}/analysis-runs/{analysis_id}/test-cases/generate"
            )
            assert cases_response.status_code == 201, cases_response.text
            test_case = cast(dict[str, Any], cases_response.json()[0])
            confirm_case_response = client.put(
                f"/api/workspaces/{workspace_id}/analysis-runs/{analysis_id}"
                "/test-cases/batch-status",
                json={"test_case_ids": [test_case["id"]], "status": "confirmed"},
            )
            assert confirm_case_response.status_code == 200, confirm_case_response.text

            environment_response = client.post(
                f"/api/workspaces/{workspace_id}/http-environments",
                json={"name": "本地业务服务", "base_url": base_url, "variables": {}},
            )
            assert environment_response.status_code == 201, environment_response.text
            environment_id = cast(str, environment_response.json()["id"])
            execution_response = client.post(
                f"/api/workspaces/{workspace_id}/http-executions",
                json={
                    "environment_id": environment_id,
                    "method": "GET",
                    "path": "/qa/health?client=desktop",
                    "headers": {},
                    "body": None,
                    "timeout_seconds": 10,
                    "max_attempts": 1,
                    "assertions": [{"kind": "status_code", "target": None, "expected": "200"}],
                },
            )
            assert execution_response.status_code == 202, execution_response.text
            execution_id = cast(str, execution_response.json()["id"])
            execution = wait_for_terminal(
                client,
                f"/api/workspaces/{workspace_id}/http-executions/{execution_id}",
            )
            assert execution["status"] == "passed"
            assert execution["assertion_results"][0]["passed"] is True
            assert json.loads(execution["response_body"])["service"] == "payments"

            report_response = client.get(f"/api/workspaces/{workspace_id}/report")
            assert report_response.status_code == 200, report_response.text
            report = cast(dict[str, Any], report_response.json())
            assert report["analysis_summary"] == {
                "total": 1,
                "passed": 1,
                "failed_or_error": 0,
                "latest_overall_score": 82,
                "issue_count": 1,
            }
            assert report["design_summary"] == {
                "test_point_total": 1,
                "test_point_confirmed": 1,
                "test_case_total": 1,
                "test_case_confirmed": 1,
            }
            assert report["execution_summary"]["total"] == 1
            assert report["execution_summary"]["passed"] == 1
            assert report["failure_attribution_summary"]["total"] == 0

            artifact_response = client.post(
                f"/api/workspaces/{workspace_id}/report/render",
                json={"format": "markdown"},
            )
            assert artifact_response.status_code == 200, artifact_response.text
            artifact = cast(dict[str, Any], artifact_response.json())
            assert artifact["media_type"] == "text/markdown"
            assert "支付项目" in artifact["content"]
            assert "/qa/health?client=desktop" in artifact["content"]

        assert len(CoreLoopServiceHandler.model_requests) == 1
        assert CoreLoopServiceHandler.model_requests[0]["model"] == "deterministic-e2e-model"
        assert CoreLoopServiceHandler.product_requests == ["/qa/health?client=desktop"]
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)
