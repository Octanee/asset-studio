"""The versioned model catalogue (FR-080): ``catalogue.json`` next to this file.

Model weights are never committed; the catalogue references upstream sources with their
SHA-256 and size (Security-Architecture). Each entry was checked against the source's LFS
metadata when it was added.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

PATH = Path(__file__).with_name("catalogue.json")
Kind = Literal["checkpoint", "lora", "controlnet", "ip_adapter", "clip_vision", "vae", "pose"]
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9.+-]{0,79}$")]
FileName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,200}$")]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Family(_Strict):
    id: Slug
    name: str


class LicenceEntry(_Strict):
    id: Slug
    name: str
    commercial_use: Literal["allowed", "forbidden", "unknown"]
    url: str = ""
    notes: str = ""


class ModelEntry(_Strict):
    id: Slug
    name: str
    kind: Kind
    family: Slug | None
    file_name: FileName
    source_url: Annotated[str, StringConstraints(pattern=r"^https://")]
    sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    bytes: int = Field(gt=0)
    licence: Slug
    notes: str = ""


class Catalogue(_Strict):
    schema_version: Literal[1]
    version: int
    families: list[Family]
    licences: list[LicenceEntry]
    models: list[ModelEntry]

    @model_validator(mode="after")
    def _references(self) -> "Catalogue":
        families = {f.id for f in self.families}
        licences = {lic.id for lic in self.licences}
        if "unknown" not in licences:
            raise ValueError("the catalogue needs an 'unknown' licence for local files")
        seen: set[str] = set()
        files: set[tuple[str, str]] = set()
        for m in self.models:
            if m.id in seen:
                raise ValueError(f"duplicate model id {m.id}")
            if (m.kind, m.file_name) in files:
                raise ValueError(f"two models use the file {m.kind}/{m.file_name}")
            if m.family is not None and m.family not in families:
                raise ValueError(f"{m.id}: unknown family {m.family}")
            if m.licence not in licences:
                raise ValueError(f"{m.id}: unknown licence {m.licence}")
            seen.add(m.id)
            files.add((m.kind, m.file_name))
        return self


def parse(text: str) -> Catalogue:
    return Catalogue.model_validate(json.loads(text))


@lru_cache
def load() -> Catalogue:
    return parse(PATH.read_text(encoding="utf-8"))
