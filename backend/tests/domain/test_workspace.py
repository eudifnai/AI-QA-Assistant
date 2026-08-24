import pytest

from backend.app.domain.workspace import normalize_workspace_name


def test_workspace_name_is_trimmed() -> None:
    assert normalize_workspace_name("  示例项目  ") == "示例项目"


@pytest.mark.parametrize("name", ["", "   ", "a" * 81])
def test_workspace_name_rejects_invalid_values(name: str) -> None:
    with pytest.raises(ValueError):
        normalize_workspace_name(name)
