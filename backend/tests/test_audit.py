"""RULE-006: audit entries are written for changes and cannot be modified."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from asset_studio.modules.audit.service import list_entries, record


def test_rule006_audit_is_append_only(db: Session) -> None:
    entry = record(db, actor="user", action="test.action", subject_type="test")
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("UPDATE audit_entry SET action = 'x' WHERE id = :id"), {"id": entry.id})
        db.flush()


def test_rule006_audit_cannot_be_deleted(db: Session) -> None:
    entry = record(db, actor="user", action="test.action", subject_type="test")
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("DELETE FROM audit_entry WHERE id = :id"), {"id": entry.id})


def test_fr115_filter_by_actor_newest_first(db: Session) -> None:
    first = record(db, actor="user", action="a.one", subject_type="test")
    record(db, actor="mcp", action="a.two", subject_type="test")
    third = record(db, actor="user", action="a.three", subject_type="test")
    entries = list_entries(db, actor="user")
    assert [e.id for e in entries[:2]] == [third.id, first.id]
