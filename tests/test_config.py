# SPDX-FileCopyrightText: 2026 Julia Koblitz, OSIRIS Solutions GmbH
# SPDX-License-Identifier: AGPL-3.0-or-later

from pathlib import Path

from pydantic import SecretStr, ValidationError
import pytest

from osiris_mcp.config import Settings


def test_api_key_is_masked_in_settings_output() -> None:
    settings = Settings(base_url="https://osiris.example.org", api_key="secret-value")

    assert isinstance(settings.api_key, SecretStr)
    assert "secret-value" not in repr(settings)


def test_client_id_can_be_configured_separately() -> None:
    settings = Settings(
        base_url="https://osiris.example.org",
        client_id="osc_test-client",
        api_key="secret-value",
    )

    assert settings.client_id == "osc_test-client"


def test_source_url_can_be_advertised_separately() -> None:
    settings = Settings(
        base_url="https://osiris.example.org",
        mcp_source_url="https://code.example.org/osiris-mcp",
    )

    assert str(settings.mcp_source_url) == "https://code.example.org/osiris-mcp"


def test_transport_defaults_to_stdio() -> None:
    settings = Settings(_env_file=None)

    assert settings.mcp_transport == "stdio"
    assert settings.mcp_host == "127.0.0.1"
    assert settings.mcp_port == 8000
    assert settings.mcp_path == "/mcp"


def test_api_key_can_be_loaded_from_secret_file(tmp_path: Path) -> None:
    secret_file = tmp_path / "osiris_api_key"
    secret_file.write_text("secret-from-file\n", encoding="utf-8")

    settings = Settings(api_key_file=secret_file, _env_file=None)

    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == "secret-from-file"
    assert "secret-from-file" not in repr(settings)


def test_api_key_and_secret_file_are_mutually_exclusive(tmp_path: Path) -> None:
    secret_file = tmp_path / "osiris_api_key"
    secret_file.write_text("secret-from-file", encoding="utf-8")

    with pytest.raises(ValidationError, match="configure either"):
        Settings(
            api_key="inline-secret",
            api_key_file=secret_file,
            _env_file=None,
        )


def test_inbound_api_key_mode_requires_http_and_a_strong_key() -> None:
    with pytest.raises(ValidationError, match="requires streamable-http"):
        Settings(
            mcp_auth_mode="api-key",
            mcp_api_key="x" * 32,
            _env_file=None,
        )

    with pytest.raises(ValidationError, match="at least 32 characters"):
        Settings(
            mcp_transport="streamable-http",
            mcp_auth_mode="api-key",
            mcp_api_key="too-short",
            _env_file=None,
        )


def test_oauth_mode_requires_complete_resource_server_configuration() -> None:
    with pytest.raises(ValidationError, match="OSIRIS_MCP_PUBLIC_URL"):
        Settings(
            mcp_transport="streamable-http",
            mcp_auth_mode="oauth",
            _env_file=None,
        )


def test_oauth_scopes_accept_spaces_and_commas() -> None:
    settings = Settings(
        mcp_transport="streamable-http",
        mcp_auth_mode="oauth",
        mcp_public_url="https://mcp.example.org/mcp",
        mcp_oauth_issuer_url="https://login.example.org",
        mcp_oauth_introspection_url="https://login.example.org/introspect",
        mcp_oauth_client_id="osiris-mcp",
        mcp_oauth_client_secret="secret",
        mcp_oauth_required_scopes="osiris:read, profile osiris:read",
        _env_file=None,
    )

    assert settings.mcp_oauth_required_scope_list == ["osiris:read", "profile"]
