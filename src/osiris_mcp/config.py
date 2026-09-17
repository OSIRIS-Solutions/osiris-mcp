# SPDX-FileCopyrightText: 2026 Julia Koblitz, OSIRIS Solutions GmbH
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, HttpUrl, SecretStr, model_validator
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
    api_key_file: Path | None = None
    timeout_seconds: float = Field(default=15.0, gt=0, le=60)
    mcp_source_url: HttpUrl | None = None
    mcp_transport: Literal["stdio", "streamable-http"] = "stdio"
    mcp_host: Literal["127.0.0.1", "localhost", "0.0.0.0"] = "127.0.0.1"
    mcp_port: int = Field(default=8000, ge=1, le=65535)
    mcp_path: str = Field(default="/mcp", pattern=r"^/[A-Za-z0-9/_-]+$")

    @model_validator(mode="after")
    def load_api_key_file(self) -> "Settings":
        """Load a Docker/Kubernetes secret without exposing its content."""

        if self.api_key is not None and self.api_key_file is not None:
            raise ValueError("configure either OSIRIS_API_KEY or OSIRIS_API_KEY_FILE")
        if self.api_key_file is None:
            return self

        try:
            value = self.api_key_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ValueError("OSIRIS_API_KEY_FILE could not be read") from exc
        if not value:
            raise ValueError("OSIRIS_API_KEY_FILE must not be empty")
        self.api_key = SecretStr(value)
        return self


@lru_cache
def get_settings() -> Settings:
    """Return one immutable-by-convention settings instance per process."""

    return Settings()
