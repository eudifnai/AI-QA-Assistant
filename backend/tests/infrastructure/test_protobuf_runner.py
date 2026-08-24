from __future__ import annotations

import threading
from collections.abc import Generator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import ProxyHandler

import pytest

from backend.app.infrastructure.protobuf_runner import (
    MAX_PROTO_RESPONSE_BYTES,
    ProtoRunnerError,
    StdlibProtobufRunner,
)


class Handler(BaseHTTPRequestHandler):
    target_called = False
    received_body = b""
    received_content_type = ""

    def do_POST(self) -> None:
        if self.path == "/redirect":
            self.send_response(307)
            self.send_header("Location", "/target")
            self.end_headers()
            return
        if self.path == "/target":
            type(self).target_called = True
        length = int(self.headers.get("Content-Length", "0"))
        type(self).received_body = self.rfile.read(length)
        type(self).received_content_type = self.headers.get("Content-Type", "")
        payload = (
            b"x" * (MAX_PROTO_RESPONSE_BYTES + 1)
            if self.path == "/large"
            else type(self).received_body
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/x-protobuf")
        self.send_header("Set-Cookie", "session=secret-value")
        self.send_header("X-Echo", "secret-value")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *args: object) -> None:
        return


@pytest.fixture
def server() -> Generator[str, None, None]:
    Handler.target_called = False
    Handler.received_body = b""
    Handler.received_content_type = ""
    instance = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{instance.server_port}"
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=5)


def test_protobuf_runner_posts_binary_and_redacts_response_headers(server: str) -> None:
    result = StdlibProtobufRunner().execute(
        url=f"{server}/echo",
        headers={"Authorization": "Bearer secret-value"},
        payload=b"\x08\x07",
        timeout_seconds=5,
        secrets=("secret-value",),
    )

    assert result.status_code == 200
    assert result.payload == b"\x08\x07"
    assert Handler.received_body == b"\x08\x07"
    assert Handler.received_content_type == "application/x-protobuf"
    assert result.headers["Set-Cookie"] == "***"
    assert result.headers["X-Echo"] == "***"


def test_protobuf_runner_does_not_follow_redirects(server: str) -> None:
    result = StdlibProtobufRunner().execute(
        url=f"{server}/redirect",
        headers={},
        payload=b"\x08\x07",
        timeout_seconds=5,
        secrets=(),
    )

    assert result.status_code == 307
    assert result.payload == b""
    assert Handler.target_called is False


def test_protobuf_runner_does_not_use_system_proxy() -> None:
    runner = StdlibProtobufRunner()
    handlers = [
        item for item in getattr(runner._opener, "handlers", []) if isinstance(item, ProxyHandler)
    ]
    assert handlers == []


def test_protobuf_runner_rejects_oversized_response(server: str) -> None:
    with pytest.raises(ProtoRunnerError, match="response_too_large"):
        StdlibProtobufRunner().execute(
            url=f"{server}/large",
            headers={},
            payload=b"request",
            timeout_seconds=5,
            secrets=(),
        )
