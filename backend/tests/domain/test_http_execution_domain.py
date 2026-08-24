import pytest

from backend.app.domain.http_execution import (
    HttpAssertion,
    HttpTemplateError,
    evaluate_http_assertions,
    redact_secrets,
    resolve_template,
    validate_and_normalize_base_url,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://127.0.0.1:8080/api/", "http://127.0.0.1:8080/api"),
        ("https://api.example.test/v1", "https://api.example.test/v1"),
    ],
)
def test_http_environment_accepts_safe_http_base_urls(raw: str, expected: str) -> None:
    assert validate_and_normalize_base_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "ftp://api.example.test",
        "https://user:password@api.example.test",
        "https://api.example.test/v1?token=value",
        "https://api.example.test/v1#fragment",
        "https:///missing-host",
    ],
)
def test_http_environment_rejects_unsafe_base_urls(raw: str) -> None:
    with pytest.raises(ValueError):
        validate_and_normalize_base_url(raw)


def test_http_template_resolves_public_and_secret_variables() -> None:
    assert (
        resolve_template(
            "/users/{{USER_ID}}?token={{secret.API_TOKEN}}",
            variables={"USER_ID": "42"},
            secrets={"API_TOKEN": "top-secret"},
        )
        == "/users/42?token=top-secret"
    )


@pytest.mark.parametrize(
    ("template", "variables", "secrets"),
    [
        ("/{{UNKNOWN}}", {}, {}),
        ("/{{secret.MISSING}}", {}, {}),
        ("/{{bad-name}}", {"bad-name": "value"}, {}),
        ("/{{ secret.API_TOKEN }}", {}, {"API_TOKEN": "value"}),
    ],
)
def test_http_template_rejects_missing_or_malformed_references(
    template: str,
    variables: dict[str, str],
    secrets: dict[str, str],
) -> None:
    with pytest.raises(HttpTemplateError):
        resolve_template(template, variables=variables, secrets=secrets)


def test_http_result_redacts_every_known_secret() -> None:
    assert redact_secrets(
        "Bearer top-secret and second-secret", ["top-secret", "second-secret"]
    ) == ("Bearer *** and ***")


def test_http_assertions_evaluate_status_header_body_and_json_path() -> None:
    results = evaluate_http_assertions(
        (
            HttpAssertion("status_code", None, "200"),
            HttpAssertion("header_equals", "Content-Type", "application/json"),
            HttpAssertion("body_contains", None, "success"),
            HttpAssertion("json_path_equals", "$.data.items.0.id", "42"),
        ),
        status_code=200,
        headers={"content-type": "application/json"},
        body='{"message":"success","data":{"items":[{"id":42}]}}',
        body_encoding="text",
    )

    assert all(item.passed for item in results)
    assert results[-1].actual == "42"


def test_http_assertion_failures_are_safe_and_deterministic() -> None:
    results = evaluate_http_assertions(
        (
            HttpAssertion("status_code", None, "201"),
            HttpAssertion("json_path_equals", "$.missing", '"secret-free"'),
        ),
        status_code=500,
        headers={},
        body='{"token":"must-not-appear"}',
        body_encoding="text",
    )

    assert [item.passed for item in results] == [False, False]
    assert results[0].actual == "500"
    assert results[1].actual is None
    assert "must-not-appear" not in repr(results)


@pytest.mark.parametrize(
    "assertion",
    [
        HttpAssertion("status_code", "unexpected", "200"),
        HttpAssertion("status_code", None, "not-a-number"),
        HttpAssertion("header_equals", None, "value"),
        HttpAssertion("body_contains", "unexpected", "value"),
        HttpAssertion("json_path_equals", "$.bad[0]", "true"),
        HttpAssertion("json_path_equals", "$.value", "not-json"),
    ],
)
def test_http_assertion_configuration_is_validated(assertion: HttpAssertion) -> None:
    with pytest.raises(ValueError):
        assertion.validate()
