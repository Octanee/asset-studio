"""Application settings, read from environment variables prefixed with ``ASSET_STUDIO_``."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ASSET_STUDIO_", env_file=".env", extra="ignore")

    # Loopback by default (NFR-005). Containers override this and publish only on 127.0.0.1.
    host: str = "127.0.0.1"
    port: int = 8400
    database_url: str = "postgresql+psycopg://asset_studio:asset_studio@127.0.0.1:5432/asset_studio"
    data_dir: str = "./data"
    log_level: str = "INFO"
    log_json: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
