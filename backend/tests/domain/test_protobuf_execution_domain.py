import pytest

from backend.app.domain.protobuf_execution import (
    ProtoFieldAssertion,
    build_protobuf_url,
    evaluate_proto_assertions,
)


def test_build_protobuf_url_accepts_safe_relative_path() -> None:
    assert build_protobuf_url("https://api.example.com/v1", "/echo?tenant=qa") == (
        "https://api.example.com/v1/echo?tenant=qa"
    )


@pytest.mark.parametrize(
    "base_url,path",
    [
        ("https://user@example.com", "/echo"),
        ("https://api.example.com", "https://evil.example/echo"),
        ("https://api.example.com", "//evil.example/echo"),
        ("https://api.example.com", "/echo#fragment"),
        ("https://api.example.com", "/echo\r\nX-Test: bad"),
    ],
)
def test_build_protobuf_url_rejects_unsafe_targets(base_url: str, path: str) -> None:
    with pytest.raises(ValueError):
        build_protobuf_url(base_url, path)


def test_evaluate_proto_assertions_supports_nested_fields_and_strict_types() -> None:
    assertions = (
        ProtoFieldAssertion("$.reply.id", "7").validate(),
        ProtoFieldAssertion("$.reply.ok", "true").validate(),
        ProtoFieldAssertion("$.items.0", '"first"').validate(),
    )

    results = evaluate_proto_assertions(
        assertions,
        {"reply": {"id": 7, "ok": True}, "items": ["first"]},
    )

    assert [item.passed for item in results] == [True, True, True]


def test_evaluate_proto_assertions_reports_missing_and_type_mismatch() -> None:
    assertions = (
        ProtoFieldAssertion("$.missing", '"value"').validate(),
        ProtoFieldAssertion("$.count", '"1"').validate(),
    )

    results = evaluate_proto_assertions(assertions, {"count": 1})

    assert results[0].actual is None
    assert results[0].passed is False
    assert results[1].actual == "1"
    assert results[1].passed is False


@pytest.mark.parametrize(
    "path,expected_json",
    [("reply.id", "1"), ("$", "1"), ("$.reply", "{}"), ("$.reply", "not-json")],
)
def test_field_assertion_rejects_invalid_input(path: str, expected_json: str) -> None:
    with pytest.raises(ValueError):
        ProtoFieldAssertion(path, expected_json).validate()
