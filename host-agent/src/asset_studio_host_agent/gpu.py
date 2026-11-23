"""GPU information from ``nvidia-smi`` (FR-043)."""

import shutil
import subprocess
from collections.abc import Callable
from typing import Any

FIELDS = ("name", "memory.total", "memory.used", "utilization.gpu", "driver_version")


def parse(output: str) -> list[dict[str, Any]]:
    gpus = []
    for line in output.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != len(FIELDS):
            continue
        name, total, used, util, driver = parts
        gpus.append(
            {
                "name": name,
                "memory_total_mb": _int(total),
                "memory_used_mb": _int(used),
                "utilization_percent": _int(util),
                "driver": driver,
            }
        )
    return gpus


def _int(value: str) -> int | None:
    try:
        return int(float(value))
    except ValueError:
        return None  # "[N/A]" on some drivers


def probe(
    run: Callable[..., Any] = subprocess.run,
    which: Callable[[str], str | None] = shutil.which,
) -> dict[str, Any]:
    exe = which("nvidia-smi")
    if exe is None:
        return {"available": False, "reason": "NVIDIA_SMI_NOT_FOUND", "gpus": []}
    try:
        result = run(
            [exe, f"--query-gpu={','.join(FIELDS)}", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "reason": "NVIDIA_SMI_FAILED", "gpus": []}
    if result.returncode != 0:
        return {"available": False, "reason": "NVIDIA_SMI_FAILED", "gpus": []}
    gpus = parse(result.stdout)
    return {"available": bool(gpus), "reason": None if gpus else "NO_GPU", "gpus": gpus}
