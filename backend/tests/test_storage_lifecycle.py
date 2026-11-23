"""Storage safety and the lifecycle table, without a database."""

import io
from pathlib import Path

import pytest

from asset_studio.modules.assets.lifecycle import STATES, TRANSITIONS, Policy, actor_allowed
from asset_studio.modules.storage.local import (
    FileTooLargeError,
    KeyExistsError,
    LocalStorage,
    StorageError,
)


def test_put_is_atomic_hashed_and_never_overwrites(tmp_path: Path) -> None:
    s = LocalStorage(tmp_path)
    stored = s.put("projects/p/assets/a/v1/original.png", io.BytesIO(b"abc"))
    assert stored.bytes == 3
    assert stored.sha256 == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    with pytest.raises(KeyExistsError):
        s.put("projects/p/assets/a/v1/original.png", io.BytesIO(b"other"))
    assert s.path("projects/p/assets/a/v1/original.png").read_bytes() == b"abc"
    assert not list((tmp_path / "staging").iterdir())


@pytest.mark.parametrize(
    "key",
    ["../x", "projects/../../etc", "/abs", "C:/win", "staging/x", "Projects/Up", "a//b", ""],
)
def test_keys_cannot_escape_or_target_staging(tmp_path: Path, key: str) -> None:
    with pytest.raises(StorageError):
        LocalStorage(tmp_path).put(key, io.BytesIO(b"x"))


def test_size_limit_leaves_nothing_behind(tmp_path: Path) -> None:
    s = LocalStorage(tmp_path)
    with pytest.raises(FileTooLargeError):
        s.put("projects/p/big.png", io.BytesIO(b"x" * 10), max_bytes=5)
    assert not s.exists("projects/p/big.png")
    assert not list((tmp_path / "staging").iterdir())


def test_clean_staging_removes_partial_files(tmp_path: Path) -> None:
    (tmp_path / "staging").mkdir()
    (tmp_path / "staging" / "x.part").write_bytes(b"partial")
    LocalStorage(tmp_path).clean_staging()
    assert not (tmp_path / "staging").exists()


def test_every_transition_uses_known_states() -> None:
    for t in TRANSITIONS.values():
        assert t.sources <= set(STATES)
        assert t.target is None or t.target in STATES


def test_deleted_is_terminal_and_published_cannot_be_deleted_directly() -> None:
    assert not any("deleted" in t.sources for t in TRANSITIONS.values())
    assert "published" not in TRANSITIONS["delete"].sources


@pytest.mark.parametrize(
    ("policy", "actor", "mcp_can_decide", "allowed"),
    [
        ("decider", "user", False, True),
        ("decider", "mcp", False, False),
        ("decider", "mcp", True, True),
        ("decider", "system", True, False),
        ("user", "mcp", True, False),
        ("system", "user", False, False),
        ("user_or_system", "mcp", True, False),
    ],
)
def test_actor_policies(policy: Policy, actor: str, mcp_can_decide: bool, allowed: bool) -> None:
    assert actor_allowed(policy, actor, mcp_can_decide=mcp_can_decide) is allowed
