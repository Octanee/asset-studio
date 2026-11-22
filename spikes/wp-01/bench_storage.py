"""WP-01 / R-21: file I/O speed in a container, bind mount (NTFS via WSL2) vs named volume.

Simulates the library workload: many small thumbnails, some large originals, then a full read
pass (listing + reading thumbnails, like scrolling the Asset Library).

Usage (inside a container): python bench_storage.py <dir> <label>
"""

import json
import os
import pathlib
import shutil
import sys
import time

SMALL_N, SMALL_BYTES = 2000, 40_000  # thumbnails / previews
LARGE_N, LARGE_BYTES = 20, 8_000_000  # originals (~8 MB)


def timed(fn):  # noqa: ANN001, ANN201
    t = time.perf_counter()
    fn()
    return round(time.perf_counter() - t, 3)


def main() -> None:
    root = pathlib.Path(sys.argv[1]) / "bench"
    label = sys.argv[2]
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    small, large = os.urandom(SMALL_BYTES), os.urandom(LARGE_BYTES)

    def write_small() -> None:
        for i in range(SMALL_N):
            d = root / f"a{i // 100:03d}" / f"v{i % 100:03d}"
            d.mkdir(parents=True, exist_ok=True)
            tmp = d / "thumb.tmp"
            tmp.write_bytes(small)
            tmp.replace(d / "thumb-256.webp")  # temp + rename, as in Storage-and-Backup

    def write_large() -> None:
        for i in range(LARGE_N):
            (root / f"orig-{i}.png").write_bytes(large)

    def read_small() -> None:
        n = 0
        for p in root.rglob("thumb-256.webp"):
            n += len(p.read_bytes())
        assert n == SMALL_N * SMALL_BYTES

    def read_large() -> None:
        for i in range(LARGE_N):
            (root / f"orig-{i}.png").read_bytes()

    r = {
        "label": label,
        "write_small_s": timed(write_small),
        "write_large_s": timed(write_large),
        "read_small_s": timed(read_small),
        "read_large_s": timed(read_large),
        "delete_s": timed(lambda: shutil.rmtree(root)),
    }
    r["small_files_per_s"] = round(SMALL_N / r["write_small_s"])
    r["large_write_MBps"] = round(LARGE_N * LARGE_BYTES / 1e6 / r["write_large_s"])
    print(json.dumps(r))


if __name__ == "__main__":
    main()
