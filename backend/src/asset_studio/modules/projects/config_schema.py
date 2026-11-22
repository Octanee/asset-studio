"""Project configuration schema, version 1 (FR-007, RULE-014).

The schema is deliberately small; project-specific data goes into ``extensions``
so the shared model is not forced onto every project (brief §3.3).
"""

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = 1
NAMING_PLACEHOLDERS = {"asset", "view", "category", "version", "size"}


class Category(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,62}$")
    name: str = Field(min_length=1, max_length=80)


class OutputDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")
    width: int = Field(default=1024, ge=64, le=4096)
    height: int = Field(default=1024, ge=64, le=4096)
    format: Literal["png", "webp", "jpeg"] = "png"
    background: Literal["any", "white", "transparent"] = "any"


class ProjectConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    type: str = Field(min_length=1, max_length=60)
    languages: list[str] = Field(default_factory=lambda: ["en"], min_length=1)
    intended_use: Literal["commercial", "non_commercial"]
    categories: list[Category] = Field(default_factory=list, max_length=200)
    naming: str = Field(default="{asset}-{view}", max_length=200)
    output: OutputDefaults = Field(default_factory=OutputDefaults)
    extensions: dict[str, Any] = Field(default_factory=dict)

    @field_validator("languages")
    @classmethod
    def _languages(cls, value: list[str]) -> list[str]:
        for lang in value:
            if not re.fullmatch(r"[a-z]{2}", lang):
                raise ValueError(f"language must be a two-letter code: {lang!r}")
        if len(set(value)) != len(value):
            raise ValueError("languages must be unique")
        return value

    @field_validator("naming")
    @classmethod
    def _naming(cls, value: str) -> str:
        names = set(re.findall(r"\{([a-z_]+)\}", value))
        unknown = names - NAMING_PLACEHOLDERS
        if unknown:
            raise ValueError(f"unknown naming placeholders: {sorted(unknown)}")
        if re.search(r"[\/:*?\"<>|]", re.sub(r"\{[a-z_]+\}", "", value)):
            raise ValueError("naming must not contain path or reserved characters")
        return value

    @model_validator(mode="after")
    def _unique_categories(self) -> "ProjectConfig":
        slugs = [c.slug for c in self.categories]
        if len(set(slugs)) != len(slugs):
            raise ValueError("category slugs must be unique")
        return self


def breaking_changes(old: ProjectConfig, new: ProjectConfig) -> list[str]:
    """Changes that can invalidate existing assets or exports (FR-007)."""
    changes: list[str] = []
    removed = {c.slug for c in old.categories} - {c.slug for c in new.categories}
    if removed:
        changes.append(f"categories removed: {', '.join(sorted(removed))}")
    if old.naming != new.naming:
        changes.append("naming pattern changed")
    if (old.output.width, old.output.height) != (new.output.width, new.output.height):
        changes.append("default output size changed")
    if old.output.format != new.output.format:
        changes.append("default output format changed")
    if old.intended_use != new.intended_use:
        changes.append("intended use changed")
    return changes
