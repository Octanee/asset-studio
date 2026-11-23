"""library and review: tags, favourites, collections, review comments

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "asset",
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.String(length=40)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )
    op.add_column("asset", sa.Column("favorite_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_asset_tags", "asset", ["tags"], unique=False, postgresql_using="gin")

    op.create_table(
        "collection",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
            name=op.f("fk_collection_project_id_project"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collection")),
        sa.UniqueConstraint("project_id", "name", name=op.f("uq_collection_project_id")),
    )
    op.create_index(op.f("ix_collection_project_id"), "collection", ["project_id"], unique=False)
    op.create_table(
        "collection_item",
        sa.Column("collection_id", sa.UUID(), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["asset.id"],
            name=op.f("fk_collection_item_asset_id_asset"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["collection.id"],
            name=op.f("fk_collection_item_collection_id_collection"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("collection_id", "asset_id", name=op.f("pk_collection_item")),
    )
    op.create_index(
        op.f("ix_collection_item_asset_id"), "collection_item", ["asset_id"], unique=False
    )

    op.create_table(
        "review_comment",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("asset_version_id", sa.UUID(), nullable=False),
        sa.Column("actor", sa.String(length=16), nullable=False),
        sa.Column("body", sa.String(length=4000), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("actor IN ('user', 'mcp')", name=op.f("ck_review_comment_actor")),
        sa.ForeignKeyConstraint(
            ["asset_version_id"],
            ["asset_version.id"],
            name=op.f("fk_review_comment_asset_version_id_asset_version"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_comment")),
    )
    op.create_index(
        op.f("ix_review_comment_asset_version_id"),
        "review_comment",
        ["asset_version_id"],
        unique=False,
    )
    # Comments are kept like the audit trail: no updates, no deletes.
    op.execute(
        """
        CREATE FUNCTION review_comment_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'review_comment is append-only';
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER review_comment_append_only
            BEFORE UPDATE OR DELETE ON review_comment
            FOR EACH ROW EXECUTE FUNCTION review_comment_append_only();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER review_comment_append_only ON review_comment")
    op.execute("DROP FUNCTION review_comment_append_only()")
    op.drop_index(op.f("ix_review_comment_asset_version_id"), table_name="review_comment")
    op.drop_table("review_comment")
    op.drop_index(op.f("ix_collection_item_asset_id"), table_name="collection_item")
    op.drop_table("collection_item")
    op.drop_index(op.f("ix_collection_project_id"), table_name="collection")
    op.drop_table("collection")
    op.drop_index("ix_asset_tags", table_name="asset")
    op.drop_column("asset", "favorite_at")
    op.drop_column("asset", "tags")
