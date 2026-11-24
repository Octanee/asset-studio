"""Backup and restore (FR-111, FR-112, AC-009, Storage-and-Backup).

A backup is one zip (zip64) holding:

- ``db/<table>.copy``: every table in PostgreSQL's COPY text format, read in one snapshot;
- ``files/projects/...``: the library files (originals, references, processed files,
  thumbnails and previews);
- ``manifest.json``: app and schema version, each table with its columns, row count and
  SHA-256, each file with its SHA-256, and the installed models with their hashes and
  sources (never the model files, D-41).

Restore goes only into an empty data location. It checks every hash before touching
anything, loads the tables into a scratch schema migrated to the backup's schema version,
migrates that schema to the current version, and copies the rows into the live tables in
one transaction. Files are unpacked to staging first and moved into place after the
database commit. Jobs that were waiting or running when the backup was taken come back
cancelled, so nothing starts by itself after a restore (D-58).
"""

import hashlib
import json
import os
import re
import shutil
import uuid
import zipfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import Connection

from asset_studio import __version__
from asset_studio.config import get_settings
from asset_studio.errors import DomainError

FORMAT = 1
MANIFEST = "manifest.json"
# Short-lived rows that must not come back: replayed answers and worker heartbeats.
EXCLUDED_TABLES = frozenset({"idempotency_key", "worker_heartbeat", "alembic_version"})
NAME = re.compile(r"asset-studio-backup-\d{8}-\d{6}(?:-\d{1,3})?\.zip")
KEY = re.compile(r"projects/[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)*")
# Already compressed: stored as they are.
STORED = frozenset({".png", ".webp", ".jpg", ".jpeg", ".gif", ".zip", ".safetensors"})
SCRATCH = "restore_scratch"
CHUNK = 1 << 20
BACKEND_ROOT = Path(__file__).resolve().parents[4]

Progress = Callable[..., None]


def _noop(**_: Any) -> None:
    return None


def backups_dir() -> Path:
    settings = get_settings()
    return Path(settings.backups_dir or Path(settings.data_dir) / "backups")


def backup_path(name: str) -> Path:
    """The archive called ``name`` in the backup folder; names are never paths."""
    if not NAME.fullmatch(name):
        raise DomainError(422, "BACKUP_NAME_INVALID", "Not a backup name.")
    path = backups_dir() / name
    if not path.is_file():
        raise DomainError(404, "BACKUP_NOT_FOUND", f"Backup {name} not found.")
    return path


# --- database -------------------------------------------------------------------------------


def _driver(conn: Connection) -> Any:
    """The psycopg connection under SQLAlchemy, in the same transaction."""
    return conn.connection.driver_connection


def _run(conn: Connection, statement: sql.Composable) -> int:
    """Run a composed statement (identifiers quoted by psycopg); returns the row count."""
    with _driver(conn).cursor() as cur:
        cur.execute(statement)
        return int(cur.rowcount)


def _tables(conn: Connection, schema: str) -> list[str]:
    """Tables of a schema, parents before children (foreign keys)."""
    from asset_studio.db import Base
    from asset_studio.models import load_all

    load_all()
    present = set(
        conn.scalars(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = :s"),
            {"s": schema},
        )
    )
    order = [t.name for t in Base.metadata.sorted_tables]
    known = [t for t in order if t in present]
    # Tables the current code does not know yet (an older schema has none) go last.
    return [t for t in known + sorted(present - set(order)) if t not in EXCLUDED_TABLES]


def _columns(conn: Connection, schema: str, table: str) -> list[str]:
    return list(
        conn.scalars(
            text(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema = :s AND table_name = :t ORDER BY ordinal_position"
            ),
            {"s": schema, "t": table},
        )
    )


def schema_revision(conn: Connection, schema: str = "public") -> str | None:
    q = sql.SQL("SELECT version_num FROM {}.alembic_version").format(sql.Identifier(schema))
    with _driver(conn).cursor() as cur:
        cur.execute(q)
        row = cur.fetchone()
    return str(row[0]) if row else None


def _alembic() -> Config:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    return cfg


def known_revisions() -> set[str]:
    return {s.revision for s in ScriptDirectory.from_config(_alembic()).walk_revisions()}


def head_revision() -> str | None:
    return ScriptDirectory.from_config(_alembic()).get_current_head()


@contextmanager
def _search_path(conn: Connection, schema: str) -> Iterator[None]:
    before = conn.scalar(text("SELECT current_setting('search_path')"))
    conn.execute(text("SELECT set_config('search_path', :p, true)"), {"p": schema})
    try:
        yield
    finally:
        conn.execute(text("SELECT set_config('search_path', :p, true)"), {"p": before})


def _migrate(conn: Connection, schema: str, revision: str) -> None:
    """Run the migrations inside ``schema`` on this connection and transaction."""
    cfg = _alembic()
    cfg.attributes["connection"] = conn
    with _search_path(conn, schema):
        command.upgrade(cfg, revision)


# --- archive --------------------------------------------------------------------------------


@dataclass
class _Hashing:
    """Wraps a zip member being written: counts bytes and newlines, hashes."""

    out: IO[bytes]
    digest: Any = None
    size: int = 0
    lines: int = 0

    def __post_init__(self) -> None:
        self.digest = hashlib.sha256()

    def write(self, data: bytes) -> None:
        self.digest.update(data)
        self.size += len(data)
        self.lines += data.count(b"\n")
        self.out.write(data)


def _member_info(name: str, *, stored: bool) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=datetime.now(UTC).timetuple()[:6])
    info.compress_type = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
    return info


def _new_name(folder: Path, now: datetime) -> str:
    base = f"asset-studio-backup-{now:%Y%m%d-%H%M%S}"
    name, n = f"{base}.zip", 0
    while (folder / name).exists():
        n += 1
        name = f"{base}-{n}.zip"
    return name


def _models(conn: Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT id, name, kind, file_name, sha256, bytes, source_url, origin, verification"
            " FROM model WHERE status = 'installed' ORDER BY kind, id"
        )
    ).mappings()
    return [dict(r) for r in rows]


def create_backup(
    conn: Connection,
    data_root: Path,
    folder: Path,
    *,
    progress: Progress = _noop,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Write a verified backup archive into ``folder``. ``conn`` should be in one
    REPEATABLE READ transaction, so every table comes from the same moment."""
    folder.mkdir(parents=True, exist_ok=True)
    now = now or datetime.now(UTC)
    name = _new_name(folder, now)
    partial = folder / f".{name}.partial"
    keys = [
        p.relative_to(data_root).as_posix()
        for p in sorted((data_root / "projects").rglob("*"))
        if p.is_file()
    ]
    manifest: dict[str, Any] = {
        "format": FORMAT,
        "app": "asset-studio",
        "app_version": __version__,
        "schema_revision": schema_revision(conn),
        "created_at": now.isoformat(),
        "tables": [],
        "files": [],
        "models": _models(conn),
    }
    tables = _tables(conn, "public")
    try:
        with zipfile.ZipFile(partial, "w", allowZip64=True) as zf:
            for i, table in enumerate(tables):
                progress(state="database", step=i, of=len(tables))
                columns = _columns(conn, "public", table)
                member = f"db/{table}.copy"
                query = sql.SQL("COPY {} ({}) TO STDOUT").format(
                    sql.Identifier("public", table),
                    sql.SQL(", ").join(map(sql.Identifier, columns)),
                )
                with zf.open(_member_info(member, stored=False), "w", force_zip64=True) as raw:
                    out = _Hashing(raw)
                    with _driver(conn).cursor() as cur, cur.copy(query) as copy:
                        for block in copy:
                            out.write(bytes(block))
                manifest["tables"].append(
                    {
                        "name": table,
                        "columns": columns,
                        "rows": out.lines,
                        "member": member,
                        "sha256": out.digest.hexdigest(),
                        "bytes": out.size,
                    }
                )
            for i, key in enumerate(keys):
                if i % 50 == 0:
                    progress(state="files", step=i, of=len(keys))
                if not KEY.fullmatch(key) or ".." in key.split("/"):
                    continue  # not a key the app writes
                member = f"files/{key}"
                path = data_root / key
                stored = path.suffix.lower() in STORED
                big = path.stat().st_size > 2**31
                with (
                    path.open("rb") as src,
                    zf.open(_member_info(member, stored=stored), "w", force_zip64=big) as raw,
                ):
                    out = _Hashing(raw)
                    while chunk := src.read(CHUNK):
                        out.write(chunk)
                manifest["files"].append(
                    {"key": key, "sha256": out.digest.hexdigest(), "bytes": out.size}
                )
            manifest["totals"] = {
                "tables": len(manifest["tables"]),
                "rows": sum(t["rows"] for t in manifest["tables"]),
                "files": len(manifest["files"]),
                "file_bytes": sum(f["bytes"] for f in manifest["files"]),
            }
            zf.writestr(_member_info(MANIFEST, stored=False), json.dumps(manifest, indent=2))
        progress(state="verifying", step=0, of=1)
        verify_archive(partial)  # read back: what was written is what the manifest says
        os.replace(partial, folder / name)
    finally:
        partial.unlink(missing_ok=True)
    return summary(folder / name, manifest)


def summary(path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": path.name,
        "bytes": path.stat().st_size,
        "created_at": manifest.get("created_at"),
        "app_version": manifest.get("app_version"),
        "schema_revision": manifest.get("schema_revision"),
        "totals": manifest.get("totals", {}),
        "models": len(manifest.get("models", [])),
    }


def _invalid(message: str) -> DomainError:
    return DomainError(422, "BACKUP_INVALID", message)


def read_manifest(zf: zipfile.ZipFile) -> dict[str, Any]:
    try:
        manifest = json.loads(zf.read(MANIFEST))
    except (KeyError, ValueError) as exc:
        raise _invalid("The archive has no readable manifest.") from exc
    if not isinstance(manifest, dict) or manifest.get("app") != "asset-studio":
        raise _invalid("This is not an Asset Studio backup.")
    if manifest.get("format") != FORMAT:
        raise _invalid(f"Unsupported backup format {manifest.get('format')!r}.")
    for f in manifest.get("files", []):
        key = f.get("key", "")
        if not isinstance(key, str) or not KEY.fullmatch(key) or ".." in key.split("/"):
            raise _invalid(f"Unsafe file name in the manifest: {key!r}.")
    for t in manifest.get("tables", []):
        if t.get("member") != f"db/{t.get('name')}.copy":
            raise _invalid("A table entry in the manifest is malformed.")
    return manifest


def _check_member(zf: zipfile.ZipFile, member: str, sha256: str, size: int) -> None:
    digest, n = hashlib.sha256(), 0
    try:
        with zf.open(member) as src:
            while chunk := src.read(CHUNK):
                digest.update(chunk)
                n += len(chunk)
    except KeyError as exc:
        raise DomainError(422, "BACKUP_CORRUPT", f"{member} is missing.") from exc
    except (zipfile.BadZipFile, OSError) as exc:
        raise DomainError(422, "BACKUP_CORRUPT", f"{member} cannot be read.") from exc
    if digest.hexdigest() != sha256 or n != size:
        raise DomainError(422, "BACKUP_CORRUPT", f"{member} does not match its hash.")


def verify_archive(path: Path, progress: Progress = _noop) -> dict[str, Any]:
    """Every member is listed in the manifest and matches its SHA-256 (FR-112)."""
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise DomainError(422, "BACKUP_CORRUPT", "The archive cannot be opened.") from exc
    with zf:
        manifest = read_manifest(zf)
        expected = {t["member"]: t for t in manifest["tables"]}
        expected |= {f"files/{f['key']}": f for f in manifest["files"]}
        extra = set(zf.namelist()) - set(expected) - {MANIFEST}
        if extra:
            raise _invalid(f"The archive holds files the manifest does not list: {len(extra)}.")
        for i, (member, entry) in enumerate(expected.items()):
            if i % 50 == 0:
                progress(state="verifying", step=i, of=len(expected))
            _check_member(zf, member, entry["sha256"], entry["bytes"])
    return manifest


def list_backups(folder: Path | None = None) -> list[dict[str, Any]]:
    """Backups in the folder, newest first, read from their manifests (not verified)."""
    folder = folder or backups_dir()
    if not folder.is_dir():
        return []
    out = []
    for path in folder.iterdir():
        if not path.is_file() or not NAME.fullmatch(path.name):
            continue
        try:
            with zipfile.ZipFile(path) as zf:
                out.append(summary(path, read_manifest(zf)) | {"readable": True})
        except (DomainError, zipfile.BadZipFile, OSError):
            out.append({"name": path.name, "bytes": path.stat().st_size, "readable": False})
    return sorted(out, key=lambda b: b["name"], reverse=True)


# --- restore --------------------------------------------------------------------------------


def data_location_empty(conn: Connection, data_root: Path) -> bool:
    """No project in the database and no library file: a fresh install (FR-112)."""
    if conn.scalar(text("SELECT EXISTS (SELECT 1 FROM project)")):
        return False
    projects = data_root / "projects"
    return not (projects.is_dir() and any(p.is_file() for p in projects.rglob("*")))


def _require_empty(conn: Connection, data_root: Path) -> None:
    if not data_location_empty(conn, data_root):
        raise DomainError(
            409,
            "DATA_LOCATION_NOT_EMPTY",
            "Restore goes only into an empty data location: this one already has projects.",
        )


def check_restorable(conn: Connection, data_root: Path, name: str) -> Path:
    """Fast checks before queueing a restore; the job checks everything again."""
    path = backup_path(name)
    _require_empty(conn, data_root)
    return path


@dataclass
class StagedRestore:
    staging: Path
    keys: list[str]
    manifest: dict[str, Any]
    rows: dict[str, int]
    cancelled_jobs: int


def _copy_in(conn: Connection, zf: zipfile.ZipFile, entry: dict[str, Any]) -> None:
    columns = _columns(conn, SCRATCH, entry["name"])
    if not columns or not set(entry["columns"]) <= set(columns):
        raise _invalid(f"Table {entry['name']} does not fit the backup's schema version.")
    query = sql.SQL("COPY {} ({}) FROM STDIN").format(
        sql.Identifier(SCRATCH, entry["name"]),
        sql.SQL(", ").join(map(sql.Identifier, entry["columns"])),
    )
    with zf.open(entry["member"]) as src, _driver(conn).cursor() as cur, cur.copy(query) as cp:
        while chunk := src.read(CHUNK):
            cp.write(chunk)


def _load_database(
    conn: Connection, zf: zipfile.ZipFile, manifest: dict[str, Any], progress: Progress
) -> tuple[dict[str, int], int]:
    revision = manifest["schema_revision"]
    conn.execute(text(f"DROP SCHEMA IF EXISTS {SCRATCH} CASCADE"))
    conn.execute(text(f"CREATE SCHEMA {SCRATCH}"))
    progress(state="schema", step=0, of=1)
    _migrate(conn, SCRATCH, revision)
    # Rows the migrations seed (built-in poses, ...) come from the backup instead.
    for table in reversed(_tables(conn, SCRATCH)):
        _run(conn, sql.SQL("DELETE FROM {}").format(sql.Identifier(SCRATCH, table)))
    for i, entry in enumerate(manifest["tables"]):
        progress(state="database", step=i, of=len(manifest["tables"]))
        _copy_in(conn, zf, entry)
    _migrate(conn, SCRATCH, "head")  # data migrations run on the restored rows
    rows: dict[str, int] = {}
    restored = set(_tables(conn, SCRATCH))
    for table in _tables(conn, "public"):
        if table not in restored:
            continue
        cols = sql.SQL(", ").join(map(sql.Identifier, _columns(conn, "public", table)))
        insert = sql.SQL("INSERT INTO {} ({}) SELECT {} FROM {} ON CONFLICT DO NOTHING").format(
            sql.Identifier("public", table), cols, cols, sql.Identifier(SCRATCH, table)
        )
        rows[table] = _run(conn, insert)
    error = json.dumps({"code": "RESTORED", "message": "Cancelled by restoring a backup."})
    cancelled = _run(
        conn,
        sql.SQL(
            "UPDATE public.job SET state = 'cancelled', finished_at = now(), wait_reason = NULL,"
            " locked_by = NULL, locked_until = NULL, error = {}::jsonb"
            " WHERE id IN (SELECT id FROM {}) AND state IN ('queued', 'running', 'interrupted')"
        ).format(sql.Literal(error), sql.Identifier(SCRATCH, "job")),
    )
    conn.execute(text(f"DROP SCHEMA {SCRATCH} CASCADE"))
    return rows, cancelled


def restore_backup(
    conn: Connection, data_root: Path, path: Path, *, progress: Progress = _noop
) -> StagedRestore:
    """Check the archive, load the database on ``conn`` (the caller commits) and unpack
    the files to staging. Call :func:`place_files` after the commit."""
    manifest = verify_archive(path, progress)
    revision = manifest.get("schema_revision")
    if revision not in known_revisions():
        raise DomainError(
            422,
            "BACKUP_SCHEMA_UNKNOWN",
            "The backup comes from a newer version of Asset Studio. Update before restoring.",
        )
    _require_empty(conn, data_root)
    staging = data_root / "staging" / f"restore-{uuid.uuid4().hex}"
    keys = [f["key"] for f in manifest["files"]]
    try:
        with zipfile.ZipFile(path) as zf:
            for i, key in enumerate(keys):
                if i % 50 == 0:
                    progress(state="files", step=i, of=len(keys))
                target = (staging / key).resolve()
                if staging.resolve() not in target.parents:
                    raise _invalid(f"Unsafe file name: {key!r}.")
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(f"files/{key}") as src, target.open("xb") as out:
                    shutil.copyfileobj(src, out, CHUNK)
            rows, cancelled = _load_database(conn, zf, manifest, progress)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return StagedRestore(staging, keys, manifest, rows, cancelled)


def place_files(staged: StagedRestore, data_root: Path) -> int:
    """Move the unpacked files into the library (after the database commit)."""
    placed = 0
    for key in staged.keys:
        target = data_root / key
        if target.exists():
            continue  # never overwrite a library file
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staged.staging / key, target)
        placed += 1
    shutil.rmtree(staged.staging, ignore_errors=True)
    return placed


def discard(staged: StagedRestore) -> None:
    shutil.rmtree(staged.staging, ignore_errors=True)
