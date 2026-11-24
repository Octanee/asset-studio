"""Alembic environment: uses the application settings and models."""

from alembic import context
from sqlalchemy import create_engine

from asset_studio.config import get_settings
from asset_studio.db import Base
from asset_studio.models import load_all

load_all()
target_metadata = Base.metadata


def run_migrations_online() -> None:
    # A restore runs the migrations on its own connection, inside its transaction and with
    # its scratch schema first in the search path (Storage-and-Backup).
    connection = context.config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
        return
    url = context.config.attributes.get("database_url") or get_settings().database_url
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
