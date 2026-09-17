# SPDX-FileCopyrightText: 2026 Julia Koblitz, OSIRIS Solutions GmbH
# SPDX-License-Identifier: AGPL-3.0-or-later

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
