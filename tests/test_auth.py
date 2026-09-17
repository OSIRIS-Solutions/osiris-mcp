# SPDX-FileCopyrightText: 2026 Julia Koblitz, OSIRIS Solutions GmbH
# SPDX-License-Identifier: AGPL-3.0-or-later

import time
from typing import Any

import httpx
from mcp.server import MCPServer
import pytest

from osiris_mcp.auth import (
    ApiKeyMiddleware,
    IntrospectionTokenVerifier,
    oauth_server_options,
)
from osiris_mcp.config import Settings


def oauth_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "mcp_transport": "streamable-http",
        "mcp_auth_mode": "oauth",
        "mcp_public_url": "https://mcp.example.org/mcp",
        "mcp_oauth_issuer_url": "https://login.example.org",
        "mcp_oauth_introspection_url": "https://login.example.org/introspect",
        "mcp_oauth_client_id": "osiris-mcp",
        "mcp_oauth_client_secret": "introspection-secret",
        "mcp_oauth_required_scopes": "osiris:read",
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


async def ok_app(scope: Any, receive: Any, send: Any) -> None:
    del scope, receive
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": b'{"ok":true}'})


async def test_api_key_middleware_protects_only_mcp_path() -> None:
    app = ApiKeyMiddleware(ok_app, api_key="s" * 32, mcp_path="/mcp")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://localhost",
    ) as client:
        missing = await client.post("/mcp")
        wrong = await client.post(
            "/mcp", headers={"Authorization": "Bearer wrong"}
        )
        valid = await client.post(
            "/mcp", headers={"Authorization": f"Bearer {'s' * 32}"}
        )
        health = await client.get("/health")

    assert missing.status_code == 401
    assert missing.headers["WWW-Authenticate"] == 'Bearer realm="osiris-mcp"'
    assert missing.headers["Cache-Control"] == "no-store"
    assert wrong.status_code == 401
    assert valid.status_code == 200
    assert health.status_code == 200


async def test_oauth_mode_publishes_metadata_and_challenges_clients() -> None:
    settings = oauth_settings()
    server = MCPServer("test", **oauth_server_options(settings))
    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        host="mcp.example.org",
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://mcp.example.org",
    ) as client:
        protected = await client.post("/mcp")
        metadata = await client.get("/.well-known/oauth-protected-resource/mcp")

    assert protected.status_code == 401
    assert "resource_metadata=" in protected.headers["WWW-Authenticate"]
    assert metadata.status_code == 200
    document = metadata.json()
    assert document["resource"] == "https://mcp.example.org/mcp"
    assert document["authorization_servers"] == ["https://login.example.org/"]
    assert document["scopes_supported"] == ["osiris:read"]


async def test_introspection_verifier_checks_audience_and_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "active": True,
        "aud": ["https://mcp.example.org/mcp"],
        "iss": "https://login.example.org/",
        "client_id": "claude-client",
        "sub": "julia",
        "scope": "osiris:read profile",
        "exp": int(time.time()) + 300,
    }
    seen: dict[str, Any] = {}

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            seen["timeout"] = kwargs["timeout"]

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, **kwargs: Any) -> httpx.Response:
            seen["url"] = url
            seen["data"] = kwargs["data"]
            request = httpx.Request("POST", url)
            return httpx.Response(200, json=payload, request=request)

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    verifier = IntrospectionTokenVerifier(oauth_settings())

    token = await verifier.verify_token("opaque-access-token")

    assert token is not None
    assert token.client_id == "claude-client"
    assert token.subject == "julia"
    assert token.scopes == ["osiris:read", "profile"]
    assert seen["data"]["token"] == "opaque-access-token"

    payload["aud"] = ["https://another-service.example.org"]
    assert await verifier.verify_token("wrong-audience") is None
