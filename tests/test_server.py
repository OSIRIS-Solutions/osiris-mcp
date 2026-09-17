# SPDX-FileCopyrightText: 2026 Julia Koblitz, OSIRIS Solutions GmbH
# SPDX-License-Identifier: AGPL-3.0-or-later

import httpx
from mcp import Client
import pytest

from osiris_mcp import server as server_module
from osiris_mcp.client import OsirisApiError
from osiris_mcp.config import Settings
from osiris_mcp.server import mcp


async def test_server_exposes_initial_read_only_tools() -> None:
    async with Client(mcp) as client:
        result = await client.list_tools()

    assert {tool.name for tool in result.tools} == {
        "server_info",
        "get_instance_info",
        "list_units",
        "list_topics",
        "list_activity_types",
        "search_activities",
        "get_activity",
        "search_people",
        "get_person",
        "search_experts",
        "search_projects",
        "get_project",
    }
    assert all(tool.annotations.read_only_hint for tool in result.tools)
    assert all(not tool.annotations.destructive_hint for tool in result.tools)
    paginated = {
        "list_units",
        "list_topics",
        "search_activities",
        "search_people",
        "search_experts",
        "search_projects",
    }
    for tool in result.tools:
        if tool.name in paginated:
            assert "offset" in tool.input_schema["properties"]

    activity_tool = next(tool for tool in result.tools if tool.name == "search_activities")
    properties = activity_tool.input_schema["properties"]
    assert properties["date_field"]["default"] == "start"
    assert properties["date_field"]["enum"] == ["start", "end"]
    assert properties["include_unaffiliated"]["default"] is False
    assert properties["include_online_ahead_of_print"]["default"] is False


async def test_server_info_reports_configuration_without_exposing_secrets() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool("server_info", {})

    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content["name"] == "OSIRIS MCP"
    assert result.structured_content["version"] == "0.1.0"
    assert result.structured_content["license"] == "AGPL-3.0-or-later"
    assert "source_code" in result.structured_content
    assert result.structured_content["mode"] == "read-only development"
    assert result.structured_content["transport"] in {"stdio", "streamable-http"}
    assert result.structured_content["authentication"] in {"none", "api-key", "oauth"}
    assert isinstance(result.structured_content["osiris_configured"], bool)
    assert "api_key" not in result.structured_content


async def test_server_exposes_instance_catalog_resources() -> None:
    async with Client(mcp) as client:
        result = await client.list_resources()

    assert {str(resource.uri) for resource in result.resources} == {
        "osiris://instance",
        "osiris://units",
        "osiris://topics",
        "osiris://activity-types",
    }
    assert all(resource.mime_type == "application/json" for resource in result.resources)


async def test_expected_api_error_reaches_model_with_request_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_id = "req_22222222222222222222222222222222"

    async def fail_get_person(*_: object, **__: object) -> None:
        raise OsirisApiError(
            f"OSIRIS person was not found (request ID: {request_id})"
        )

    monkeypatch.setattr(
        server_module,
        "get_settings",
        lambda: Settings(base_url="https://osiris.example.org"),
    )
    monkeypatch.setattr(server_module.OsirisClient, "get_person", fail_get_person)

    async with Client(mcp) as client:
        result = await client.call_tool("get_person", {"person_id": "unknown"})

    message = " ".join(
        block.text for block in result.content if getattr(block, "type", None) == "text"
    )
    assert result.is_error is True
    assert request_id in message
    assert "OSIRIS person was not found" in message


async def test_local_validation_error_explains_absent_request_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        server_module,
        "get_settings",
        lambda: Settings(base_url="https://osiris.example.org"),
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_activity",
            {"activity_id": "invalid/id"},
        )

    message = " ".join(
        block.text for block in result.content if getattr(block, "type", None) == "text"
    )
    assert result.is_error is True
    assert "activity_id must be a 24-character hexadecimal ID" in message
    assert "OSIRIS was not called; no request ID is available" in message


async def test_health_check_discloses_no_configuration() -> None:
    app = mcp.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        transport_security=server_module._local_transport_security(),
        host="0.0.0.0",
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://localhost",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["Cache-Control"] == "no-store"


def test_run_uses_stdio_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_run(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))

    monkeypatch.setattr(server_module.mcp, "run", fake_run)

    server_module.run(Settings(_env_file=None))

    assert calls == [((), {})]


def test_run_uses_hardened_local_http_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_run(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))

    monkeypatch.setattr(server_module.mcp, "run", fake_run)
    settings = Settings(
        mcp_transport="streamable-http",
        mcp_host="0.0.0.0",
        mcp_port=8765,
        mcp_path="/custom-mcp",
        _env_file=None,
    )

    server_module.run(settings)

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == ()
    assert kwargs["transport"] == "streamable-http"
    assert kwargs["host"] == "0.0.0.0"
    assert kwargs["port"] == 8765
    assert kwargs["streamable_http_path"] == "/custom-mcp"
    assert kwargs["stateless_http"] is True
    assert kwargs["json_response"] is True
    assert kwargs["max_request_body_size"] == 1024 * 1024
    security = kwargs["transport_security"]
    assert isinstance(security, server_module.TransportSecuritySettings)
    assert "localhost:*" in security.allowed_hosts


def test_run_wraps_http_app_in_api_key_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel_app = object()
    app_calls: list[dict[str, object]] = []
    uvicorn_calls: list[tuple[object, dict[str, object]]] = []

    def fake_app(**kwargs: object) -> object:
        app_calls.append(kwargs)
        return sentinel_app

    def fake_uvicorn_run(app: object, **kwargs: object) -> None:
        uvicorn_calls.append((app, kwargs))

    monkeypatch.setattr(server_module.mcp, "streamable_http_app", fake_app)
    monkeypatch.setattr(server_module.uvicorn, "run", fake_uvicorn_run)
    settings = Settings(
        mcp_transport="streamable-http",
        mcp_auth_mode="api-key",
        mcp_api_key="s" * 32,
        _env_file=None,
    )

    server_module.run(settings)

    assert len(app_calls) == 1
    assert len(uvicorn_calls) == 1
    protected_app, uvicorn_options = uvicorn_calls[0]
    assert isinstance(protected_app, server_module.ApiKeyMiddleware)
    assert uvicorn_options == {"host": "127.0.0.1", "port": 8000}


def test_transport_security_includes_public_oauth_host() -> None:
    settings = Settings(
        mcp_transport="streamable-http",
        mcp_auth_mode="oauth",
        mcp_public_url="https://mcp.example.org/mcp",
        mcp_oauth_issuer_url="https://login.example.org",
        mcp_oauth_introspection_url="https://login.example.org/introspect",
        mcp_oauth_client_id="osiris-mcp",
        mcp_oauth_client_secret="secret",
        _env_file=None,
    )

    security = server_module._transport_security(settings)

    assert "mcp.example.org:*" in security.allowed_hosts
    assert "https://mcp.example.org:*" in security.allowed_origins
