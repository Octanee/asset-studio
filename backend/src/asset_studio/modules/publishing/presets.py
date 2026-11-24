"""Export preset definition (FR-090) and file naming.

A preset turns one version into one file per size. Names and folders are patterns with
placeholders; every value written into them is reduced to safe characters, so a pattern can
never leave the target folder.
"""

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

NAME_PLACEHOLDERS = {"asset", "view", "category", "version", "size", "suffix", "project"}
FOLDER_PLACEHOLDERS = {"asset", "view", "category", "project"}
RESERVED = re.compile(r"[\\:*?\"<>|]")
PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
MAX_PATH = 400


class Size(BaseModel):
    model_config = ConfigDict(extra="forbid")
    suffix: str = Field(default="", pattern=r"^[a-z0-9-]{0,20}$")
    width: int = Field(ge=16, le=4096)
    height: int = Field(ge=16, le=4096)


def _placeholders(value: str, allowed: set[str]) -> None:
    unknown = set(PLACEHOLDER.findall(value)) - allowed
    if unknown:
        raise ValueError(f"unknown placeholders: {sorted(unknown)}")


class PresetDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # "svg" copies a vector version as it is; raster formats render it (FR-047).
    format: Literal["png", "webp", "jpeg", "svg"] = "webp"
    sizes: list[Size] = Field(
        default_factory=lambda: [Size(width=1024, height=1024)], min_length=1, max_length=10
    )
    naming: str = Field(default="{asset}-{view}{suffix}", min_length=1, max_length=200)
    folders: str = Field(default="", max_length=200)
    background: Literal["keep", "white"] = "keep"
    resize: Literal["contain", "cover"] = "contain"
    optimize: bool = True
    quality: int = Field(default=90, ge=50, le=100)
    metadata: Literal["none", "sidecar"] = "none"

    @field_validator("naming")
    @classmethod
    def _naming(cls, value: str) -> str:
        _placeholders(value, NAME_PLACEHOLDERS)
        literal = PLACEHOLDER.sub("", value)
        if RESERVED.search(literal) or "/" in literal:
            raise ValueError("naming must not contain path or reserved characters")
        return value

    @field_validator("folders")
    @classmethod
    def _folders(cls, value: str) -> str:
        _placeholders(value, FOLDER_PLACEHOLDERS)
        literal = PLACEHOLDER.sub("x", value)
        if RESERVED.search(literal) or value.startswith("/"):
            raise ValueError("folders must be a relative path without reserved characters")
        if any(part in ("", ".", "..") for part in literal.split("/")) and value:
            raise ValueError("folders must not contain empty, '.' or '..' parts")
        return value.strip("/")

    @model_validator(mode="after")
    def _sizes(self) -> "PresetDefinition":
        suffixes = [s.suffix for s in self.sizes]
        if len(set(suffixes)) != len(suffixes):
            raise ValueError("each size needs its own suffix")
        if len(self.sizes) > 1 and "{suffix}" not in self.naming and "{size}" not in self.naming:
            raise ValueError("with several sizes the naming needs {suffix} or {size}")
        return self


def safe(value: str) -> str:
    """A value fit for a file or folder name: letters, digits, '-' and '_' only."""
    text = unicodedata.normalize("NFKC", value).strip().lower()
    text = re.sub(r"[^\w-]+", "-", text, flags=re.UNICODE).strip("-.")
    return text[:80] or "x"


def render(pattern: str, values: dict[str, str]) -> str:
    return PLACEHOLDER.sub(lambda m: values.get(m.group(1), ""), pattern)


EXT = {"png": "png", "webp": "webp", "jpeg": "jpg", "svg": "svg"}


def file_paths(d: PresetDefinition, values: dict[str, str]) -> list[tuple[Size, str]]:
    """The relative path of each size's file, e.g. ``lower-body/squat-front-sm.webp``."""
    clean = {k: safe(v) for k, v in values.items()}
    folder = "/".join(safe(part) for part in render(d.folders, clean).split("/") if part)
    out = []
    for size in d.sizes:
        suffix = f"-{size.suffix}" if size.suffix else ""
        name = render(d.naming, clean | {"suffix": suffix, "size": f"{size.width}x{size.height}"})
        name = re.sub(r"-{2,}", "-", name).strip("-.") or "file"
        path = f"{folder}/{name}.{EXT[d.format]}" if folder else f"{name}.{EXT[d.format]}"
        out.append((size, path[:MAX_PATH]))
    return out
