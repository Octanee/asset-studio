"""publishing: export presets and targets, plans, publications, current publication

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def _fk(table: str, column: str, other: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], [f"{other}.id"], name=op.f(f"fk_{table}_{column}_{other}"), ondelete="RESTRICT"
    )


def upgrade() -> None:
    for table in ("export_preset", "export_target"):
        extra = (
            [sa.Column("definition", JSONB, nullable=False)]
            if table == "export_preset"
            else [
                sa.Column("root", sa.String(length=300), nullable=False),
                sa.Column("subdir", sa.String(length=300), nullable=False),
            ]
        )
        stamps = [sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)]
        if table == "export_preset":
            stamps.append(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
        op.create_table(
            table,
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("project_id", sa.UUID(), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            *extra,
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
            *stamps,
            _fk(table, "project_id", "project"),
            sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
            sa.UniqueConstraint("project_id", "name", name=op.f(f"uq_{table}_project_id")),
        )
        op.create_index(op.f(f"ix_{table}_project_id"), table, ["project_id"], unique=False)

    op.create_table(
        "publication_plan",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("preset_id", sa.UUID(), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column("actor", sa.String(length=16), nullable=False),
        sa.Column("items", JSONB, nullable=False),
        sa.Column("skipped", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("job_id", sa.UUID(), nullable=True),
        _fk("publication_plan", "project_id", "project"),
        _fk("publication_plan", "preset_id", "export_preset"),
        _fk("publication_plan", "target_id", "export_target"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_publication_plan")),
    )
    op.create_index(
        op.f("ix_publication_plan_project_id"), "publication_plan", ["project_id"], unique=False
    )

    op.create_table(
        "publication",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("asset_version_id", sa.UUID(), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column("preset_id", sa.UUID(), nullable=False),
        sa.Column("plan_id", sa.UUID(), nullable=True),
        sa.Column("job_id", sa.UUID(), nullable=True),
        sa.Column("actor", sa.String(length=16), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        _fk("publication", "asset_version_id", "asset_version"),
        _fk("publication", "target_id", "export_target"),
        _fk("publication", "preset_id", "export_preset"),
        _fk("publication", "plan_id", "publication_plan"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_publication")),
    )
    op.create_index(
        op.f("ix_publication_asset_version_id"), "publication", ["asset_version_id"], unique=False
    )
    op.create_index(op.f("ix_publication_target_id"), "publication", ["target_id"], unique=False)

    op.create_table(
        "publication_file",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("publication_id", sa.UUID(), nullable=False),
        sa.Column("relative_path", sa.String(length=500), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("bytes", sa.BigInteger(), nullable=False),
        sa.Column("overwrote_sha256", sa.String(length=64), nullable=True),
        sa.Column("confirmed_overwrite", sa.Boolean(), nullable=False),
        _fk("publication_file", "publication_id", "publication"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_publication_file")),
    )
    op.create_index(
        op.f("ix_publication_file_publication_id"),
        "publication_file",
        ["publication_id"],
        unique=False,
    )

    op.create_table(
        "current_publication",
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column("publication_id", sa.UUID(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        _fk("current_publication", "asset_id", "asset"),
        _fk("current_publication", "target_id", "export_target"),
        _fk("current_publication", "publication_id", "publication"),
        sa.PrimaryKeyConstraint("asset_id", "target_id", name=op.f("pk_current_publication")),
    )


def downgrade() -> None:
    op.drop_table("current_publication")
    op.drop_index(op.f("ix_publication_file_publication_id"), table_name="publication_file")
    op.drop_table("publication_file")
    op.drop_index(op.f("ix_publication_target_id"), table_name="publication")
    op.drop_index(op.f("ix_publication_asset_version_id"), table_name="publication")
    op.drop_table("publication")
    op.drop_index(op.f("ix_publication_plan_project_id"), table_name="publication_plan")
    op.drop_table("publication_plan")
    for table in ("export_target", "export_preset"):
        op.drop_index(op.f(f"ix_{table}_project_id"), table_name=table)
        op.drop_table(table)
