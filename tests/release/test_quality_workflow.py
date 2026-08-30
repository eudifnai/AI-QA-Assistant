from pathlib import Path

WORKFLOW_PATH = Path(__file__).parents[2] / ".github" / "workflows" / "quality.yml"
PACKAGE_JSON_PATH = Path(__file__).parents[2] / "package.json"
WORKSPACE_CONFIG_PATH = Path(__file__).parents[2] / "pnpm-workspace.yaml"
PNPM_LOCK_PATH = Path(__file__).parents[2] / "pnpm-lock.yaml"
FORGE_PATCH_PATH = Path(__file__).parents[2] / "patches" / "@electron-forge__core@7.11.2.patch"
INSTALLER_MODULE_PATH = (
    Path(__file__).parents[2] / "scripts" / "windows-release" / "InstallerAcceptance.psm1"
)


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_quality_workflow_supports_manual_clean_runner_dispatch() -> None:
    workflow = _workflow_text()

    assert "\n  workflow_dispatch:\n" in workflow
    assert 'branches: [main, "codex/release-*"]' in workflow
    assert "runs-on: windows-latest" in workflow
    assert "-Mode Lifecycle" in workflow
    assert "-AllowSystemChanges" in workflow


def test_quality_workflow_keeps_release_security_gates() -> None:
    workflow = _workflow_text()

    assert "id-token: write" in workflow
    assert "azure/login@v3" in workflow
    assert "azure/artifact-signing-action@v2" in workflow
    assert "AI_QA_ARTIFACT_SIGNING_ENDPOINT" in workflow
    assert "AI_QA_ARTIFACT_SIGNING_ACCOUNT_NAME" in workflow
    assert "AI_QA_ARTIFACT_SIGNING_CERTIFICATE_PROFILE_NAME" in workflow
    assert "AI_QA_WINDOWS_SIGN_PFX_BASE64" not in workflow
    assert "AI_QA_WINDOWS_SIGN_PFX_PASSWORD" not in workflow
    assert "gitleaks/gitleaks-action@v2" in workflow


def test_formal_release_gate_cannot_skip_signing() -> None:
    workflow = _workflow_text()
    package_json = PACKAGE_JSON_PATH.read_text(encoding="utf-8")

    assert "release_gate:" in workflow
    assert "formal" in workflow
    assert "Formal release gate requires all Azure Artifact Signing variables." in workflow
    assert "pnpm electron:package" in workflow
    assert "files-folder-recurse: true" in workflow
    assert "files-folder-filter: exe,dll,node" in workflow
    assert "pnpm electron:make:from-package" in workflow
    assert (
        '"electron:make:from-package": "pnpm --dir frontend electron:make:from-package"'
        in package_json
    )
    assert 'AI_QA_WINDOWS_SIGN_MODE: "artifact_signing"' in workflow
    assert "-RequireSignedArtifacts" in workflow
    assert "id-token: write" not in workflow.split("\njobs:\n", maxsplit=1)[0]
    assert workflow.index("pnpm electron:package") < workflow.index(
        "azure/artifact-signing-action@v2"
    )
    assert workflow.index("azure/artifact-signing-action@v2") < workflow.index(
        "pnpm electron:make:from-package"
    )
    assert workflow.index("pnpm electron:make:from-package") < workflow.index(
        "-RequireSignedArtifacts"
    )


def test_quality_workflow_archives_and_reuses_release_candidates() -> None:
    workflow = _workflow_text()

    assert "previous_run_id:" in workflow
    assert "Previous workflow run id must be a positive integer." in workflow
    assert "actions: read" in workflow
    assert "actions/download-artifact@v4" in workflow
    assert "run-id: ${{ inputs.previous_run_id }}" in workflow
    assert "-PreviousArtifactRoot" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "windows-release-candidate-${{ github.run_id }}" in workflow
    assert "retention-days: 90" in workflow


def test_desktop_packaging_does_not_ignore_the_extract_zip_advisory() -> None:
    workflow = _workflow_text()
    workspace_config = WORKSPACE_CONFIG_PATH.read_text(encoding="utf-8")
    lockfile = PNPM_LOCK_PATH.read_text(encoding="utf-8")
    forge_patch = FORGE_PATCH_PATH.read_text(encoding="utf-8")

    assert '"@electron/packager": 20.3.0' in workspace_config
    assert (
        '"@electron-forge/core@7.11.2": patches/@electron-forge__core@7.11.2.patch'
        in workspace_config
    )
    assert "async ({ buildPath, electronVersion, platform, arch }) =>" in forge_patch
    assert "async (targets) =>" in forge_patch
    assert "await (0, node_util_1.promisify)(hook)(" in forge_patch
    assert "extract-zip@2.0.1:" not in lockfile
    assert "GHSA-jmr9-qjv8-65gv" not in workspace_config
    assert "GHSA-jmr9-qjv8-65gv" not in workflow


def test_windows_lifecycle_repeats_install_and_probes_credential_retention() -> None:
    installer_module = INSTALLER_MODULE_PATH.read_text(encoding="utf-8")

    assert 'name = "repeat_install"' in installer_module
    assert 'name = "credential_retention"' in installer_module
    assert "system_credential_retained_after_uninstall" in installer_module
    assert "AI_QA_ACCEPTANCE_CREDENTIAL_SECRET" in installer_module
