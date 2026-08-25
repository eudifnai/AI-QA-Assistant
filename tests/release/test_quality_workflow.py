from pathlib import Path

WORKFLOW_PATH = Path(__file__).parents[2] / ".github" / "workflows" / "quality.yml"


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_quality_workflow_supports_manual_clean_runner_dispatch() -> None:
    workflow = _workflow_text()

    assert "\n  workflow_dispatch:\n" in workflow
    assert 'branches: [main, "codex/release-*"]' in workflow
    assert "runs-on: windows-latest" in workflow
    assert "-Mode Lifecycle" in workflow
    assert "-AllowSystemChanges" in workflow


def test_windows_lifecycle_allows_slow_hosted_runner_installation() -> None:
    workflow = _workflow_text()

    assert workflow.count("-TimeoutSeconds 600") == 2


def test_quality_workflow_keeps_release_security_gates() -> None:
    workflow = _workflow_text()

    assert "AI_QA_WINDOWS_SIGN_PFX_BASE64" in workflow
    assert "AI_QA_WINDOWS_SIGN_PFX_PASSWORD" in workflow
    assert "$hasCertificate -ne $hasPassword" in workflow
    assert "gitleaks/gitleaks-action@v2" in workflow


def test_formal_release_gate_cannot_skip_signing() -> None:
    workflow = _workflow_text()

    assert "release_gate:" in workflow
    assert "formal" in workflow
    assert "Formal release gate requires the Windows signing secrets." in workflow
    assert "-RequireSignedArtifacts" in workflow


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
