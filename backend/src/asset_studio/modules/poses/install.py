"""Install the DWPose model files (ADR-009): download or copy, then check SHA-256.

    docker compose run --rm worker python -m asset_studio.modules.poses.install
    docker compose run --rm -v <dir>:/src:ro worker
        python -m asset_studio.modules.poses.install --from /src

Files are written to ``<name>.part`` first and renamed only when the checksum matches, so a
broken download is never loaded. Existing files with the right checksum are kept. The model
catalogue with approved downloads replaces this in WP-12.
"""

import argparse
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

import httpx

from asset_studio.modules.poses.detection import models_dir
from asset_studio.modules.poses.dwpose import MODELS, sha256_of

SOURCE = "https://huggingface.co/yzd-v/DWPose/resolve/main/{name}"
SIZES_MB = {"yolox_l.onnx": 217, "dw-ll_ucoco_384.onnx": 134}


class InstallError(Exception):
    pass


def _download(url: str, target: Path, client: httpx.Client) -> None:
    with client.stream("GET", url, follow_redirects=True) as response:
        response.raise_for_status()
        with target.open("wb") as out:
            for chunk in response.iter_bytes(1024 * 1024):
                out.write(chunk)


def install(
    target_dir: Path,
    *,
    source_dir: Path | None = None,
    client: httpx.Client | None = None,
    log: Callable[[str], None] = print,
) -> list[str]:
    """Install the missing model files; return the names that were installed."""
    target_dir.mkdir(parents=True, exist_ok=True)
    own_client = client is None and source_dir is None
    http = httpx.Client(timeout=60) if own_client else client
    try:
        return _install(target_dir, source_dir, http, log)
    finally:
        if own_client and http is not None:
            http.close()


def _install(
    target_dir: Path,
    source_dir: Path | None,
    http: httpx.Client | None,
    log: Callable[[str], None],
) -> list[str]:
    installed = []
    for name, expected in MODELS.items():
        final = target_dir / name
        if final.is_file() and sha256_of(final) == expected:
            log(f"{name}: already installed")
            continue
        part = target_dir / f"{name}.part"
        try:
            if source_dir is not None:
                log(f"{name}: copying from {source_dir}")
                shutil.copyfile(source_dir / name, part)
            else:
                if http is None:  # pragma: no cover - install() always passes one
                    raise InstallError("no HTTP client")
                log(f"{name}: downloading about {SIZES_MB[name]} MB")
                _download(SOURCE.format(name=name), part, http)
            if sha256_of(part) != expected:
                raise InstallError(f"{name}: checksum mismatch, file discarded")
            part.replace(final)
        finally:
            part.unlink(missing_ok=True)
        installed.append(name)
        log(f"{name}: installed")
    return installed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install the DWPose pose detection models.")
    parser.add_argument("--from", dest="source", type=Path, help="copy from this folder")
    parser.add_argument("--to", type=Path, default=None, help="default: <data>/models/pose")
    args = parser.parse_args(argv)
    try:
        install(args.to or models_dir(), source_dir=args.source)
    except (InstallError, OSError, httpx.HTTPError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print("Pose detection is ready; the worker loads it with the next detect_pose job.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
