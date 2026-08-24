from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import tomllib
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

PNPM_PACKAGE_LINE = re.compile(r"^  (?P<key>(?:'[^']+'|[^' ].*)):$")
PNPM_INTEGRITY = re.compile(
    r"integrity:\s*(?P<algorithm>sha(?:256|384|512))-(?P<value>[A-Za-z0-9+/=]+)"
)


def _npm_identity(lock_key: str) -> tuple[str, str]:
    key = lock_key.strip("'")
    separator = key.rfind("@")
    if separator <= 0 or separator == len(key) - 1:
        raise ValueError(f"pnpm 锁文件包含无法识别的包键: {key}")
    return key[:separator], key[separator + 1 :]


def _npm_component(name: str, version: str, integrity: str | None) -> dict[str, Any]:
    group, component_name = name.rsplit("/", 1) if name.startswith("@") else (None, name)
    component: dict[str, Any] = {
        "type": "library",
        "name": component_name,
        "version": version,
        "purl": f"pkg:npm/{quote(name, safe='/')}@{version}",
        "properties": [{"name": "ai-qa-assistant:ecosystem", "value": "npm"}],
    }
    if group:
        component["group"] = group
    if integrity:
        match = PNPM_INTEGRITY.search(integrity)
        if match:
            digest = base64.b64decode(match.group("value"), validate=True).hex()
            component["hashes"] = [
                {"alg": match.group("algorithm").upper().replace("SHA", "SHA-"), "content": digest}
            ]
    component["bom-ref"] = component["purl"]
    return component


def _read_pnpm_components(lock_path: Path) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    current: tuple[str, str] | None = None
    current_integrity: str | None = None
    in_packages = False

    def append_current() -> None:
        if current:
            components.append(_npm_component(*current, current_integrity))

    for line in lock_path.read_text(encoding="utf-8").splitlines():
        if line == "packages:":
            in_packages = True
            continue
        if in_packages and line == "snapshots:":
            append_current()
            break
        if not in_packages:
            continue
        package_match = PNPM_PACKAGE_LINE.match(line)
        if package_match:
            append_current()
            current = _npm_identity(package_match.group("key"))
            current_integrity = None
            continue
        if current and (integrity_match := PNPM_INTEGRITY.search(line)):
            current_integrity = integrity_match.group(0)
    else:
        if in_packages:
            append_current()
    return components


def _read_python_components(lock_path: Path) -> list[dict[str, Any]]:
    with lock_path.open("rb") as lock_file:
        lock = tomllib.load(lock_file)
    components: list[dict[str, Any]] = []
    for package in lock.get("package", []):
        source = package.get("source", {})
        if "virtual" in source:
            continue
        name = str(package["name"]).lower().replace("_", "-")
        version = str(package["version"])
        purl = f"pkg:pypi/{quote(name)}@{version}"
        components.append(
            {
                "type": "library",
                "name": name,
                "version": version,
                "purl": purl,
                "bom-ref": purl,
                "properties": [{"name": "ai-qa-assistant:ecosystem", "value": "pypi"}],
            }
        )
    return components


def build_bom(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    package_json = json.loads((root / "frontend" / "package.json").read_text(encoding="utf-8"))
    version = str(package_json["version"])
    components_by_ref = {
        component["bom-ref"]: component
        for component in [
            *_read_pnpm_components(root / "pnpm-lock.yaml"),
            *_read_python_components(root / "uv.lock"),
        ]
    }
    components = [components_by_ref[key] for key in sorted(components_by_ref)]
    identity = "\n".join([version, *(component["bom-ref"] for component in components)])
    serial = uuid.uuid5(uuid.NAMESPACE_URL, f"ai-qa-assistant:{identity}")
    application_ref = f"pkg:generic/ai-qa-assistant@{version}"
    return {
        "$schema": "https://cyclonedx.org/schema/bom-1.6.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "AI QA Assistant",
                "version": version,
                "purl": application_ref,
                "bom-ref": application_ref,
            },
            "properties": [
                {
                    "name": "ai-qa-assistant:inventory-scope",
                    "value": "locked-source-and-build-dependencies",
                },
                {
                    "name": "ai-qa-assistant:source-lockfiles-sha256",
                    "value": ",".join(
                        hashlib.sha256((root / name).read_bytes()).hexdigest()
                        for name in ("pnpm-lock.yaml", "uv.lock")
                    ),
                },
            ],
        },
        "components": components,
    }


def write_bom(project_root: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(build_bom(project_root), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 AI QA Assistant CycloneDX SBOM。")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    write_bom(arguments.project_root, arguments.output)
    print(f"Generated CycloneDX SBOM: {arguments.output}")


if __name__ == "__main__":
    main()
