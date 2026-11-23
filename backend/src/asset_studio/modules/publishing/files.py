"""Writing into export targets (ADR-013, Security-Architecture).

Targets live under configured export roots. Every path is resolved and checked to stay inside
its root, so neither a target's folder nor a preset's pattern can write anywhere else. Files
are written to a temporary name and renamed into place, so a reader never sees half a file.
"""

import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from asset_studio.config import get_settings
from asset_studio.errors import DomainError


@dataclass(frozen=True)
class Root:
    id: str
    name: str
    path: Path


def roots() -> list[Root]:
    out = []
    for i, raw in enumerate(get_settings().export_roots):
        path = Path(raw).resolve()
        out.append(Root(id=str(i), name=path.name or str(path), path=path))
    return out


def root_by_path(raw: str) -> Root:
    for r in roots():
        if str(r.path) == raw:
            return r
    raise DomainError(
        409,
        "EXPORT_ROOT_UNAVAILABLE",
        "The target's export root is not configured any more.",
        {"root": raw},
    )


def clean_subdir(subdir: str) -> str:
    parts = [p for p in subdir.replace("\\", "/").split("/") if p not in ("", ".")]
    if any(p == ".." or ":" in p for p in parts):
        raise DomainError(422, "TARGET_PATH_INVALID", "The folder must stay inside the root.")
    return "/".join(parts)


def inside(base: Path, relative: str) -> Path:
    """``base/relative`` resolved, refusing anything that leaves ``base`` (symlinks too)."""
    path = (base / relative).resolve()
    if path != base and base not in path.parents:
        raise DomainError(422, "TARGET_PATH_INVALID", "The path leaves the export root.")
    return path


def target_dir(root_path: str, subdir: str) -> Path:
    root = root_by_path(root_path)
    return inside(root.path, clean_subdir(subdir))


def sha256_of(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write(base: Path, relative: str, data: bytes) -> Path:
    path = inside(base, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{uuid.uuid4().hex[:8]}.part"
    try:
        with tmp.open("wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path
