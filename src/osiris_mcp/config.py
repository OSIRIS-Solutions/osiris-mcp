# SPDX-FileCopyrightText: 2026 Julia Koblitz, OSIRIS Solutions GmbH
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings.

    Secrets are represented as ``SecretStr`` so accidental string conversion does
    not disclose them in logs or debugging output.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="OSIRIS_",
        extra="ignore",
    )

    base_url: HttpUrl | None = None
    client_id: str | None = None
    api_key: SecretStr | None = None
    timeout_seconds: float = Field(default=15.0, gt=0, le=60)
    mcp_source_url: HttpUrl | None = None


@lru_cache
def get_settings() -> Settings:
    """Return one immutable-by-convention settings instance per process."""

    return Settings()
