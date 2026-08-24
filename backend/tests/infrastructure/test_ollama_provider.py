import json
from email.message import Message
from urllib.request import Request

import pytest

from backend.app.infrastructure.model_providers import (
    ModelProviderError,
    OllamaChatModelProvider,
    _NoRedirectHandler,
)


class Response:
    headers = Message()

    def __init__(self, payload: object) -> None:
        self._content = json.dumps(payload).encode()

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, limit: int) -> bytes:
        return self._content[:limit]


def test_ollama_provider_requests_non_streaming_schema_output() -> None:
    requests: list[tuple[Request, float]] = []

    def open_request(request: Request, timeout: float) -> Response:
        requests.append((request, timeout))
        return Response({"message": {"role": "assistant", "content": '{"ok": true}'}})

    provider = OllamaChatModelProvider(
        base_url="http://127.0.0.1:11434",
        model_name="qwen3:8b",
        timeout_seconds=20,
        open_request=open_request,
    )

    result = provider.generate("分析需求", {"type": "object"})

    assert result == '{"ok": true}'
    request, timeout = requests[0]
    request_data = request.data
    assert isinstance(request_data, bytes)
    body = json.loads(request_data)
    assert request.full_url == "http://127.0.0.1:11434/api/chat"
    assert timeout == 20
    assert body["stream"] is False
    assert body["format"] == {"type": "object"}
    assert body["options"]["temperature"] == 0


def test_ollama_provider_rejects_malformed_response() -> None:
    provider = OllamaChatModelProvider(
        base_url="http://127.0.0.1:11434",
        model_name="qwen3:8b",
        timeout_seconds=20,
        open_request=lambda _request, _timeout: Response({"message": {"content": 42}}),
    )

    with pytest.raises(ModelProviderError, match="invalid_response"):
        provider.generate("分析需求", {"type": "object"})


def test_ollama_transport_does_not_follow_redirects() -> None:
    handler = _NoRedirectHandler()

    redirected = handler.redirect_request(
        Request("http://127.0.0.1:11434/api/chat"),
        None,
        302,
        "Found",
        Message(),
        "https://attacker.example.test/collect",
    )

    assert redirected is None
