from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.app import run
from backend.app.core.config import Settings
from backend.app.core.network import API_LOOPBACK_HOST, validate_api_bind_host


@pytest.mark.parametrize(
    "host",
    ["0.0.0.0", "::", "::1", "localhost", "192.168.1.20", "127.0.0.2"],
)
def test_api_bind_host_rejects_every_non_canonical_loopback_value(host: str) -> None:
    with pytest.raises(ValueError, match=r"127\.0\.0\.1"):
        validate_api_bind_host(host)
    with pytest.raises(ValidationError):
        Settings(api_host=host, _env_file=None)


def test_api_bind_host_accepts_only_the_ipv4_loopback_endpoint() -> None:
    assert validate_api_bind_host(API_LOOPBACK_HOST) == API_LOOPBACK_HOST
    assert Settings(_env_file=None).api_host == API_LOOPBACK_HOST


def test_development_entry_passes_only_the_validated_loopback_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(app: str, **options: object) -> None:
        captured["app"] = app
        captured.update(options)

    monkeypatch.setattr(
        run,
        "get_settings",
        lambda: SimpleNamespace(api_host=API_LOOPBACK_HOST, api_port=8765),
    )
    monkeypatch.setattr(run, "configure_logging", lambda: None)
    monkeypatch.setattr("backend.app.run.uvicorn.run", fake_run)

    run.main()

    assert captured == {
        "app": "backend.app.main:app",
        "host": API_LOOPBACK_HOST,
        "port": 8765,
        "reload": False,
        "log_config": None,
    }
