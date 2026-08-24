import json
from email.message import Message
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from backend.app.infrastructure.model_providers import (
    MAX_MODEL_RESPONSE_BYTES,
    ModelProviderError,
    OpenAICompatibleChatModelProvider,
    _NoRedirectHandler,
)


class Response:
    headers = Message()

    def __init__(self, payload: object, *, raw: bytes | None = None) -> None:
        self._content = raw if raw is not None else json.dumps(payload).encode()

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, limit: int) -> bytes:
        return self._content[:limit]


def test_openai_compatible_provider_sends_bearer_and_strict_json_schema() -> None:
    requests: list[tuple[Request, float]] = []

    def open_request(request: Request, timeout: float) -> Response:
        requests.append((request, timeout))
        return Response({"choices": [{"message": {"content": '{"ok": true}'}}]})

    response_schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
        "additionalProperties": False,
    }
    provider = OpenAICompatibleChatModelProvider(
        base_url="https://models.example.test/v1/",
        model_name="quality-model",
        api_key="cloud-test-secret",
        timeout_seconds=25,
        open_request=open_request,
    )

    result = provider.generate("分析需求", response_schema)

    assert result == '{"ok": true}'
    request, timeout = requests[0]
    request_data = request.data
    assert isinstance(request_data, bytes)
    body = json.loads(request_data)
    assert request.full_url == "https://models.example.test/v1/chat/completions"
    assert request.get_header("Authorization") == "Bearer cloud-test-secret"
    assert request.get_header("Content-type") == "application/json"
    assert timeout == 25
    assert body["model"] == "quality-model"
    assert body["stream"] is False
    assert [message["role"] for message in body["messages"]] == ["developer", "user"]
    assert body["messages"][1]["content"] == "分析需求"
    assert body["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "requirement_analysis",
            "strict": True,
            "schema": response_schema,
        },
    }


@pytest.mark.parametrize(
    "base_url",
    [
        "http://models.example.test/v1",
        "https://user:password@models.example.test/v1",
        "https://models.example.test/v1?tenant=one",
        "https://models.example.test/v1#fragment",
        "https:///v1",
    ],
)
def test_openai_compatible_provider_rejects_unsafe_base_urls(base_url: str) -> None:
    with pytest.raises(ModelProviderError, match="unsafe_base_url"):
        OpenAICompatibleChatModelProvider(
            base_url=base_url,
            model_name="quality-model",
            api_key="cloud-test-secret",
            timeout_seconds=25,
        )


@pytest.mark.parametrize(
    ("status_code", "reason"),
    [
        (302, "request_failed"),
        (400, "invalid_request"),
        (401, "auth_failed"),
        (403, "auth_failed"),
        (404, "model_not_found"),
        (408, "timeout"),
        (413, "request_too_large"),
        (422, "invalid_request"),
        (429, "rate_limited"),
        (500, "unavailable"),
        (504, "timeout"),
    ],
)
def test_openai_compatible_provider_maps_http_errors(
    status_code: int,
    reason: str,
) -> None:
    def fail(request: Request, _timeout: float) -> Response:
        raise HTTPError(request.full_url, status_code, "remote detail", Message(), None)

    provider = OpenAICompatibleChatModelProvider(
        base_url="https://models.example.test/v1",
        model_name="quality-model",
        api_key="cloud-test-secret",
        timeout_seconds=25,
        open_request=fail,
    )

    with pytest.raises(ModelProviderError, match=reason) as raised:
        provider.generate("分析需求", {"type": "object"})

    assert "cloud-test-secret" not in str(raised.value)
    assert "remote detail" not in str(raised.value)


def test_openai_compatible_transport_does_not_follow_redirects() -> None:
    handler = _NoRedirectHandler()

    redirected = handler.redirect_request(
        Request(
            "https://models.example.test/v1/chat/completions",
            headers={"Authorization": "Bearer cloud-test-secret"},
        ),
        None,
        302,
        "Found",
        Message(),
        "https://attacker.example.test/collect",
    )

    assert redirected is None


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        (TimeoutError(), "timeout"),
        (URLError("offline"), "unavailable"),
        (OSError("down"), "unavailable"),
    ],
)
def test_openai_compatible_provider_maps_transport_errors(
    failure: Exception,
    reason: str,
) -> None:
    def fail(_request: Request, _timeout: float) -> Response:
        raise failure

    provider = OpenAICompatibleChatModelProvider(
        base_url="https://models.example.test/v1",
        model_name="quality-model",
        api_key="cloud-test-secret",
        timeout_seconds=25,
        open_request=fail,
    )

    with pytest.raises(ModelProviderError, match=reason):
        provider.generate("分析需求", {"type": "object"})


def test_openai_compatible_provider_rejects_invalid_or_oversized_response() -> None:
    invalid = OpenAICompatibleChatModelProvider(
        base_url="https://models.example.test/v1",
        model_name="quality-model",
        api_key="cloud-test-secret",
        timeout_seconds=25,
        open_request=lambda _request, _timeout: Response(
            {"choices": [{"message": {"content": 42}}]}
        ),
    )
    oversized = OpenAICompatibleChatModelProvider(
        base_url="https://models.example.test/v1",
        model_name="quality-model",
        api_key="cloud-test-secret",
        timeout_seconds=25,
        open_request=lambda _request, _timeout: Response(
            {}, raw=b"x" * (MAX_MODEL_RESPONSE_BYTES + 1)
        ),
    )

    with pytest.raises(ModelProviderError, match="invalid_response"):
        invalid.generate("分析需求", {"type": "object"})
    with pytest.raises(ModelProviderError, match="response_too_large"):
        oversized.generate("分析需求", {"type": "object"})


@pytest.mark.parametrize(
    "message",
    [[], {"content": "result", "refusal": {}}, {"content": "result", "refusal": ""}],
)
def test_openai_compatible_provider_rejects_malformed_message(message: object) -> None:
    provider = OpenAICompatibleChatModelProvider(
        base_url="https://models.example.test/v1",
        model_name="quality-model",
        api_key="cloud-test-secret",
        timeout_seconds=25,
        open_request=lambda _request, _timeout: Response({"choices": [{"message": message}]}),
    )

    with pytest.raises(ModelProviderError, match="invalid_response"):
        provider.generate("分析需求", {"type": "object"})


@pytest.mark.parametrize(
    ("choice", "reason"),
    [
        ({"message": {"content": None, "refusal": "cannot comply"}}, "refused"),
        ({"message": {"content": "partial"}, "finish_reason": "length"}, "response_too_large"),
        (
            {"message": {"content": "partial"}, "finish_reason": "content_filter"},
            "invalid_response",
        ),
    ],
)
def test_openai_compatible_provider_handles_refusal_and_incomplete_output(
    choice: dict[str, object],
    reason: str,
) -> None:
    provider = OpenAICompatibleChatModelProvider(
        base_url="https://models.example.test/v1",
        model_name="quality-model",
        api_key="cloud-test-secret",
        timeout_seconds=25,
        open_request=lambda _request, _timeout: Response({"choices": [choice]}),
    )

    with pytest.raises(ModelProviderError, match=reason):
        provider.generate("分析需求", {"type": "object"})
