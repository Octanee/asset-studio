"""training datasets, items and runs (WP-13)

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "training_dataset",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("trigger_word", sa.String(length=40), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
            name=op.f("fk_training_dataset_project_id_project"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_training_dataset")),
    )
    op.create_index(op.f("ix_training_dataset_project_id"), "training_dataset", ["project_id"])
    op.create_table(
        "training_item",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("dataset_id", sa.UUID(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("asset_version_id", sa.UUID(), nullable=True),
        sa.Column("storage_key", sa.String(length=300), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source IN ('asset_version', 'upload')", name=op.f("ck_training_item_source")
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["training_dataset.id"],
            name=op.f("fk_training_item_dataset_id_training_dataset"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["asset_version_id"],
            ["asset_version.id"],
            name=op.f("fk_training_item_asset_version_id_asset_version"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_training_item")),
        sa.UniqueConstraint("dataset_id", "sha256", name=op.f("uq_training_item_image")),
    )
    op.create_index(op.f("ix_training_item_dataset_id"), "training_item", ["dataset_id"])
    op.create_table(
        "training_run",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("dataset_id", sa.UUID(), nullable=False),
        sa.Column("family_id", sa.String(length=16), nullable=False),
        sa.Column("base_model_id", sa.String(length=120), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("images", sa.Integer(), nullable=False),
        sa.Column("estimate", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("acknowledged_estimate", sa.Boolean(), nullable=False),
        sa.Column("output_name", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=True),
        sa.Column("output_model_id", sa.String(length=120), nullable=True),
        sa.Column("created_by_actor", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("family_id IN ('sd15', 'sdxl')", name=op.f("ck_training_run_family")),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
            name=op.f("fk_training_run_project_id_project"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["training_dataset.id"],
            name=op.f("fk_training_run_dataset_id_training_dataset"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_training_run")),
    )
    op.create_index(op.f("ix_training_run_project_id"), "training_run", ["project_id"])
    op.create_index(op.f("ix_training_run_dataset_id"), "training_run", ["dataset_id"])


def downgrade() -> None:
    op.drop_table("training_run")
    op.drop_table("training_item")
    op.drop_table("training_dataset")
