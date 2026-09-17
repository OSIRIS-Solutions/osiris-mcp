# SPDX-FileCopyrightText: 2026 Julia Koblitz, OSIRIS Solutions GmbH
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Inbound authentication for the Streamable HTTP transport."""

from __future__ import annotations

import json
import logging
import secrets
import time
from typing import Any

import httpx
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from osiris_mcp.config import Settings


logger = logging.getLogger(__name__)


def _audiences(value: object) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return {item for item in value if isinstance(item, str)}
    return set()


def _scopes(value: object) -> list[str]:
    if isinstance(value, str):
        return value.split()
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


class IntrospectionTokenVerifier(TokenVerifier):
    """Validate OAuth access tokens through an RFC 7662 endpoint."""

    def __init__(self, settings: Settings) -> None:
        assert settings.mcp_public_url is not None
        assert settings.mcp_oauth_issuer_url is not None
        assert settings.mcp_oauth_introspection_url is not None
        assert settings.mcp_oauth_client_id is not None
        assert settings.mcp_oauth_client_secret is not None

        self._resource = str(settings.mcp_public_url)
        self._issuer = str(settings.mcp_oauth_issuer_url).rstrip("/")
        self._introspection_url = str(settings.mcp_oauth_introspection_url)
        self._client_id = settings.mcp_oauth_client_id
        self._client_secret = settings.mcp_oauth_client_secret.get_secret_value()
        self._audience = settings.mcp_oauth_audience or self._resource
        self._timeout = settings.timeout_seconds

    async def verify_token(self, token: str) -> AccessToken | None:
        """Return verified caller information without logging token material."""

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    self._introspection_url,
                    data={"token": token, "token_type_hint": "access_token"},
                    auth=httpx.BasicAuth(self._client_id, self._client_secret),
                    headers={"Accept": "application/json"},
                )
        except httpx.HTTPError:
            logger.warning("OAuth token introspection request failed")
            return None

        if response.status_code != 200:
            logger.warning(
                "OAuth token introspection was rejected with status %s",
                response.status_code,
            )
            return None

        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError):
            logger.warning("OAuth token introspection returned invalid JSON")
            return None
        if not isinstance(payload, dict) or payload.get("active") is not True:
            return None

        expires_at = payload.get("exp")
        if not isinstance(expires_at, int) or expires_at <= int(time.time()):
            return None

        audiences = _audiences(payload.get("aud"))
        if self._audience not in audiences:
            logger.warning("OAuth token audience does not match OSIRIS MCP")
            return None

        issuer = payload.get("iss")
        if isinstance(issuer, str) and issuer.rstrip("/") != self._issuer:
            logger.warning("OAuth token issuer does not match configured issuer")
            return None

        client_id = payload.get("client_id")
        subject = payload.get("sub")
        principal = client_id if isinstance(client_id, str) else subject
        if not isinstance(principal, str) or not principal:
            return None

        return AccessToken(
            token=token,
            client_id=principal,
            scopes=_scopes(payload.get("scope")),
            expires_at=expires_at,
            resource=self._audience,
            subject=subject if isinstance(subject, str) else None,
            claims={"iss": issuer} if isinstance(issuer, str) else None,
        )


def oauth_server_options(settings: Settings) -> dict[str, Any]:
    """Build MCP SDK OAuth resource-server constructor options."""

    if settings.mcp_auth_mode != "oauth":
        return {}

    assert settings.mcp_public_url is not None
    assert settings.mcp_oauth_issuer_url is not None
    audience = settings.mcp_oauth_audience or str(settings.mcp_public_url)
    return {
        "token_verifier": IntrospectionTokenVerifier(settings),
        "auth": AuthSettings(
            issuer_url=AnyHttpUrl(str(settings.mcp_oauth_issuer_url)),
            resource_server_url=AnyHttpUrl(str(settings.mcp_public_url)),
            required_scopes=settings.mcp_oauth_required_scope_list,
            validate_token_resource=audience == str(settings.mcp_public_url),
        ),
    }


class ApiKeyMiddleware:
    """Protect one MCP endpoint with a pre-shared Bearer token.

    This intentionally does not publish OAuth discovery metadata. It is a small
    internal-deployment option for clients that can be configured with a fixed
    Authorization header, not an OAuth substitute for public deployments.
    """

    def __init__(self, app: ASGIApp, *, api_key: str, mcp_path: str) -> None:
        self.app = app
        self._api_key = api_key
        self._paths = {mcp_path.rstrip("/"), f"{mcp_path.rstrip('/')}/"}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") not in self._paths:
            await self.app(scope, receive, send)
            return

        authorization_headers = [
            value
            for key, value in scope.get("headers", [])
            if key.lower() == b"authorization"
        ]
        authorization = (
            authorization_headers[0].decode("latin-1", errors="ignore")
            if len(authorization_headers) == 1
            else ""
        )
        scheme, separator, supplied = authorization.partition(" ")
        valid = (
            separator == " "
            and scheme.lower() == "bearer"
            and bool(supplied)
            and secrets.compare_digest(supplied, self._api_key)
        )
        if valid:
            await self.app(scope, receive, send)
            return

        body = json.dumps(
            {
                "error": "invalid_token",
                "error_description": "Authentication required",
            }
        ).encode("utf-8")
        response_headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
            (b"cache-control", b"no-store"),
            (b"www-authenticate", b'Bearer realm="osiris-mcp"'),
        ]
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": response_headers,
            }
        )
        await send({"type": "http.response.body", "body": body})
