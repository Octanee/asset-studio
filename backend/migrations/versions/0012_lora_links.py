"""LoRAs linked to styles and characters (WP-13 part 2)

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lora_link",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("model_id", sa.String(length=120), nullable=False),
        sa.Column("target_type", sa.String(length=16), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column("strength", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "target_type IN ('style', 'character')", name=op.f("ck_lora_link_target_type")
        ),
        sa.CheckConstraint("strength >= 0 AND strength <= 2", name=op.f("ck_lora_link_strength")),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["model.id"],
            name=op.f("fk_lora_link_model_id_model"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lora_link")),
        sa.UniqueConstraint("model_id", "target_type", "target_id", name=op.f("uq_lora_link_link")),
    )
    op.create_index(op.f("ix_lora_link_target_id"), "lora_link", ["target_id"])


def downgrade() -> None:
    op.drop_table("lora_link")
