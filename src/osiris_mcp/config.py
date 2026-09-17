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
    mcp_auth_mode: Literal["none", "api-key", "oauth"] = "none"
    mcp_api_key: SecretStr | None = None
    mcp_api_key_file: Path | None = None
    mcp_public_url: HttpUrl | None = None
    mcp_oauth_issuer_url: HttpUrl | None = None
    mcp_oauth_introspection_url: HttpUrl | None = None
    mcp_oauth_introspection_host_header: str | None = Field(
        default=None,
        pattern=(
            r"^(?:[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?"
            r"|\[[0-9A-Fa-f:.]+\])(?::[1-9][0-9]{0,4})?$"
        ),
    )
    mcp_oauth_client_id: str | None = None
    mcp_oauth_client_secret: SecretStr | None = None
    mcp_oauth_client_secret_file: Path | None = None
    mcp_oauth_required_scopes: str = "osiris:read"
    mcp_oauth_audience: str | None = None
    mcp_oauth_allow_insecure_introspection: bool = False
    mcp_allowed_hosts: str | None = None
    mcp_allowed_origins: str | None = None

    @model_validator(mode="after")
    def load_api_key_file(self) -> "Settings":
        """Load secret files and reject unsafe or incomplete auth settings."""

        self.api_key = self._load_secret(
            self.api_key,
            self.api_key_file,
            "OSIRIS_API_KEY",
        )
        self.mcp_api_key = self._load_secret(
            self.mcp_api_key,
            self.mcp_api_key_file,
            "OSIRIS_MCP_API_KEY",
        )
        self.mcp_oauth_client_secret = self._load_secret(
            self.mcp_oauth_client_secret,
            self.mcp_oauth_client_secret_file,
            "OSIRIS_MCP_OAUTH_CLIENT_SECRET",
        )

        if self.mcp_auth_mode != "none" and self.mcp_transport != "streamable-http":
            raise ValueError("MCP authentication requires streamable-http transport")

        if self.mcp_auth_mode == "api-key":
            if self.mcp_api_key is None:
                raise ValueError("api-key mode requires OSIRIS_MCP_API_KEY")
            if len(self.mcp_api_key.get_secret_value()) < 32:
                raise ValueError("OSIRIS_MCP_API_KEY must contain at least 32 characters")

        if self.mcp_auth_mode == "oauth":
            required = {
                "OSIRIS_MCP_PUBLIC_URL": self.mcp_public_url,
                "OSIRIS_MCP_OAUTH_ISSUER_URL": self.mcp_oauth_issuer_url,
                "OSIRIS_MCP_OAUTH_INTROSPECTION_URL": (
                    self.mcp_oauth_introspection_url
                ),
                "OSIRIS_MCP_OAUTH_CLIENT_ID": self.mcp_oauth_client_id,
                "OSIRIS_MCP_OAUTH_CLIENT_SECRET": self.mcp_oauth_client_secret,
            }
            missing = [name for name, value in required.items() if value is None]
            if missing:
                raise ValueError(f"oauth mode requires {', '.join(missing)}")
            if not self.mcp_oauth_required_scope_list:
                raise ValueError("OSIRIS_MCP_OAUTH_REQUIRED_SCOPES must not be empty")
            assert self.mcp_public_url is not None
            public_path = self.mcp_public_url.path.rstrip("/") or "/"
            configured_path = self.mcp_path.rstrip("/") or "/"
            if public_path != configured_path:
                raise ValueError("OSIRIS_MCP_PUBLIC_URL path must match OSIRIS_MCP_PATH")
            for name, url in (
                ("OSIRIS_MCP_PUBLIC_URL", self.mcp_public_url),
                ("OSIRIS_MCP_OAUTH_ISSUER_URL", self.mcp_oauth_issuer_url),
            ):
                assert url is not None
                if url.scheme != "https" and url.host not in {"127.0.0.1", "localhost"}:
                    raise ValueError(f"{name} must use HTTPS outside localhost")
            assert self.mcp_oauth_introspection_url is not None
            introspection = self.mcp_oauth_introspection_url
            if (
                introspection.scheme != "https"
                and introspection.host not in {"127.0.0.1", "localhost"}
                and not self.mcp_oauth_allow_insecure_introspection
            ):
                raise ValueError(
                    "OSIRIS_MCP_OAUTH_INTROSPECTION_URL must use HTTPS outside "
                    "localhost; explicitly enable "
                    "OSIRIS_MCP_OAUTH_ALLOW_INSECURE_INTROSPECTION only for a "
                    "trusted development network"
                )

        return self

    @staticmethod
    def _load_secret(
        direct: SecretStr | None,
        file_path: Path | None,
        setting_name: str,
    ) -> SecretStr | None:
        if direct is not None and file_path is not None:
            raise ValueError(f"configure either {setting_name} or {setting_name}_FILE")
        if file_path is None:
            return direct
        try:
            value = file_path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ValueError(f"{setting_name}_FILE could not be read") from exc
        if not value:
            raise ValueError(f"{setting_name}_FILE must not be empty")
        return SecretStr(value)

    @property
    def mcp_oauth_required_scope_list(self) -> list[str]:
        """Return the configured OAuth scopes in stable, deduplicated order."""

        scopes = self.mcp_oauth_required_scopes.replace(",", " ").split()
        return list(dict.fromkeys(scopes))

    @property
    def mcp_allowed_host_list(self) -> list[str]:
        """Return explicit Host allow-list entries."""

        if not self.mcp_allowed_hosts:
            return []
        return [value.strip() for value in self.mcp_allowed_hosts.split(",") if value.strip()]

    @property
    def mcp_allowed_origin_list(self) -> list[str]:
        """Return explicit Origin allow-list entries."""

        if not self.mcp_allowed_origins:
            return []
        return [value.strip() for value in self.mcp_allowed_origins.split(",") if value.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return one immutable-by-convention settings instance per process."""

    return Settings()
