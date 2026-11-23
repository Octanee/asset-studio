"""processing and validation

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

# Frozen copies of the model kinds before and after this revision.
OLD_KINDS = ("checkpoint", "lora", "controlnet", "ip_adapter", "clip_vision", "vae", "pose")
NEW_KINDS = (*OLD_KINDS, "segmentation")


def _kinds(kinds: tuple[str, ...]) -> str:
    return f"kind IN ({', '.join(repr(k) for k in kinds)})"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_model_kind"), "model", type_="check")
    op.create_check_constraint(op.f("ck_model_kind"), "model", _kinds(NEW_KINDS))
    op.add_column(
        "asset_version",
        sa.Column(
            "processing",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.create_table(
        "validation_result",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("asset_version_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("rule", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('passed', 'failed', 'skipped')", name=op.f("ck_validation_result_status")
        ),
        sa.ForeignKeyConstraint(
            ["asset_version_id"],
            ["asset_version.id"],
            name=op.f("fk_validation_result_asset_version_id_asset_version"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_validation_result")),
    )
    op.create_index(
        op.f("ix_validation_result_asset_version_id"),
        "validation_result",
        ["asset_version_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_validation_result_asset_version_id"), table_name="validation_result")
    op.drop_table("validation_result")
    op.drop_column("asset_version", "processing")
    op.execute("DELETE FROM model WHERE kind = 'segmentation'")
    op.drop_constraint(op.f("ck_model_kind"), "model", type_="check")
    op.create_check_constraint(op.f("ck_model_kind"), "model", _kinds(OLD_KINDS))
