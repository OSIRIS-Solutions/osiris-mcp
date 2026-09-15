from mcp import Client

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


async def test_server_info_reports_configuration_without_exposing_secrets() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool("server_info", {})

    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content["name"] == "OSIRIS MCP"
    assert result.structured_content["version"] == "0.1.0"
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
