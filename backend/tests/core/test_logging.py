import json
import logging
import sys

from backend.app.core.logging import JsonFormatter


def test_json_formatter_includes_trace_context() -> None:
    record = logging.LogRecord(
        name="backend.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="health checked",
        args=(),
        exc_info=None,
    )
    record.trace_id = "trace-123"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "backend.test"
    assert payload["message"] == "health checked"
    assert payload["trace_id"] == "trace-123"
    assert payload["timestamp"].endswith("+00:00")


def test_json_formatter_redacts_exception_message() -> None:
    try:
        raise ValueError("secret exception detail")
    except ValueError:
        exception_info = sys.exc_info()

    record = logging.LogRecord(
        name="backend.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=20,
        msg="Unhandled API exception",
        args=(),
        exc_info=exception_info,
    )

    formatted = JsonFormatter().format(record)

    assert "secret exception detail" not in formatted
    assert json.loads(formatted)["exception_type"] == "ValueError"
