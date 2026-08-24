from __future__ import annotations

import json
from pathlib import Path

from scripts.release.generate_sbom import build_bom, write_bom


def _write_fixture(root: Path) -> None:
    frontend = root / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(
        json.dumps({"name": "@ai-qa-assistant/frontend", "version": "0.1.0"}),
        encoding="utf-8",
    )
    (root / "uv.lock").write_text(
        """
version = 1

[[package]]
name = "ai-qa-assistant"
version = "0.1.0"
source = { virtual = "." }

[[package]]
name = "fastapi"
version = "0.118.0"
source = { registry = "https://pypi.org/simple" }
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (root / "pnpm-lock.yaml").write_text(
        """
lockfileVersion: '9.0'

packages:

  '@scope/runtime@1.2.3':
    resolution: {integrity: sha512-YWJj}

  vue@3.5.0:
    resolution: {integrity: sha512-ZGVm}

snapshots:
""".lstrip(),
        encoding="utf-8",
    )


def test_builds_deterministic_cyclonedx_16_from_both_lockfiles(tmp_path: Path) -> None:
    _write_fixture(tmp_path)

    first = build_bom(tmp_path)
    second = build_bom(tmp_path)

    assert first == second
    assert first["bomFormat"] == "CycloneDX"
    assert first["specVersion"] == "1.6"
    assert first["metadata"]["component"]["version"] == "0.1.0"
    assert [component["purl"] for component in first["components"]] == [
        "pkg:npm/%40scope/runtime@1.2.3",
        "pkg:npm/vue@3.5.0",
        "pkg:pypi/fastapi@0.118.0",
    ]
    assert first["components"][0]["hashes"] == [{"alg": "SHA-512", "content": "616263"}]
    assert str(tmp_path) not in json.dumps(first)


def test_writes_stable_utf8_json_with_a_trailing_newline(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    output = tmp_path / "release" / "ai-qa-assistant.cdx.json"

    write_bom(tmp_path, output)
    first = output.read_bytes()
    write_bom(tmp_path, output)

    assert output.read_bytes() == first
    assert first.endswith(b"\n")
    assert json.loads(first)["serialNumber"].startswith("urn:uuid:")
