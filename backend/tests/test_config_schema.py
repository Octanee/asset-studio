import pytest
from pydantic import ValidationError

from asset_studio.modules.projects.config_schema import ProjectConfig, breaking_changes
from tests.conftest import project_config


def test_valid_config() -> None:
    assert ProjectConfig.model_validate(project_config()).schema_version == 1


@pytest.mark.parametrize(
    "override",
    [
        {"languages": ["pl", "pl"]},
        {"languages": ["pol"]},
        {"naming": "{asset}-{unknown}"},
        {"naming": "../{asset}"},
        {"categories": [{"slug": "a", "name": "A"}, {"slug": "a", "name": "B"}]},
        {"unexpected": True},
    ],
)
def test_rule014_invalid_configs_are_rejected(override: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ProjectConfig.model_validate(project_config(**override))


def test_breaking_changes_detected() -> None:
    old = ProjectConfig.model_validate(project_config())
    new = ProjectConfig.model_validate(
        project_config(intended_use="non_commercial", naming="{asset}")
    )
    assert set(breaking_changes(old, new)) == {"intended use changed", "naming pattern changed"}
