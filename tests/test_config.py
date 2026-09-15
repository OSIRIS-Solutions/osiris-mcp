from pydantic import SecretStr

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
