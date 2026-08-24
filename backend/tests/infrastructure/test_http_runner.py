from __future__ import annotations

import threading
from collections.abc import Generator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import ProxyHandler

import pytest

from backend.app.infrastructure.http_runner import (
    MAX_HTTP_RESPONSE_BYTES,
    HttpRunnerError,
    StdlibHttpRunner,
)


class Handler(BaseHTTPRequestHandler):
    target_called = False

    def do_GET(self) -> None:
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/target")
            self.end_headers()
            return
        if self.path == "/target":
            type(self).target_called = True
        if self.path == "/large":
            payload = b"x" * (MAX_HTTP_RESPONSE_BYTES + 1)
        elif self.path == "/binary":
            payload = b"\xff\x00"
        else:
            payload = b"Bearer top-secret"
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Set-Cookie", "session=top-secret")
        self.send_header("X-Echo", "top-secret")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *args: object) -> None:
        return


@pytest.fixture
def server() -> Generator[tuple[str, ThreadingHTTPServer], None, None]:
    Handler.target_called = False
    instance = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{instance.server_port}", instance
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=5)


def test_http_runner_redacts_response_body_and_sensitive_headers(
    server: tuple[str, ThreadingHTTPServer],
) -> None:
    base_url, _ = server

    result = StdlibHttpRunner().execute(
        method="GET",
        url=f"{base_url}/echo",
        headers={"Authorization": "Bearer top-secret"},
        body=None,
        timeout_seconds=5,
        secrets=("top-secret",),
    )

    assert result.status_code == 200
    assert result.body == "Bearer ***"
    assert result.headers["Set-Cookie"] == "***"
    assert result.headers["X-Echo"] == "***"


def test_http_runner_does_not_follow_redirects(
    server: tuple[str, ThreadingHTTPServer],
) -> None:
    base_url, _ = server

    result = StdlibHttpRunner().execute(
        method="GET",
        url=f"{base_url}/redirect",
        headers={},
        body=None,
        timeout_seconds=5,
        secrets=(),
    )

    assert result.status_code == 302
    assert Handler.target_called is False


def test_http_runner_does_not_implicitly_use_system_proxy() -> None:
    runner = StdlibHttpRunner()

    proxy_handlers = [
        item for item in getattr(runner._opener, "handlers", []) if isinstance(item, ProxyHandler)
    ]

    assert proxy_handlers == []


def test_http_runner_returns_binary_as_base64(server: tuple[str, ThreadingHTTPServer]) -> None:
    base_url, _ = server

    result = StdlibHttpRunner().execute(
        method="GET",
        url=f"{base_url}/binary",
        headers={},
        body=None,
        timeout_seconds=5,
        secrets=(),
    )

    assert result.body_encoding == "base64"
    assert result.body == "/wA="


def test_http_runner_rejects_oversized_response(
    server: tuple[str, ThreadingHTTPServer],
) -> None:
    base_url, _ = server

    with pytest.raises(HttpRunnerError, match="response_too_large"):
        StdlibHttpRunner().execute(
            method="GET",
            url=f"{base_url}/large",
            headers={},
            body=None,
            timeout_seconds=5,
            secrets=(),
        )
