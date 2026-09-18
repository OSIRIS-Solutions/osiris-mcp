# OSIRIS MCP

OSIRIS MCP is a read-only Model Context Protocol server for controlled access to
research information stored in OSIRIS.

The project is intentionally split into two layers:

1. OSIRIS remains responsible for data access and authorization.
2. This MCP server exposes a small allowlist of typed, auditable tools.

The current implementation is an initial development scaffold. Before exposing
it publicly, review the deployment end to end, including TLS, network access,
logging, rate limits, and the scopes granted to its dedicated API client.

## Installation

Python 3.12 is required. Run the published package without installing it
globally:

```bash
uvx --from osiris-mcp osiris-mcp
```

Alternatively, install the command into an isolated environment:

```bash
pipx install osiris-mcp
osiris-mcp
```

The server uses the stdio transport by default and reads its configuration from
environment variables or a `.env` file in the current directory. At minimum,
set `OSIRIS_BASE_URL` and `OSIRIS_API_KEY`; dedicated OSIRIS API clients should
also set `OSIRIS_CLIENT_ID`. See [Configuration](#configuration) for the full
setup and the distinction between downstream OSIRIS credentials and inbound MCP
authentication.

## Development setup

```bash
uv sync
uv run pytest
```

Start the local stdio server:

```bash
uv run osiris-mcp
```

## Local Docker container

The included Compose configuration runs OSIRIS MCP as a persistent local
Streamable HTTP service. It requires Docker but no local Python installation.

```bash
cp .env.example .env
# Configure the OSIRIS URL, client ID, API key, and source URL in .env.
docker compose up --build -d
```

The MCP endpoint is then available at `http://127.0.0.1:8765/mcp` and the
minimal process health check at `http://127.0.0.1:8765/health`. Stop it with:

```bash
docker compose down
```

The published port is deliberately bound to `127.0.0.1`. The default
`OSIRIS_MCP_AUTH_MODE=none` is suitable only for this loopback setup and must
never be exposed on a LAN, through a reverse proxy, or on the public internet.
DNS-rebinding protection additionally permits only local Host and Origin values,
but it is not a substitute for authentication or the loopback binding.

The image runs as an unprivileged user with a read-only filesystem, all Linux
capabilities removed, and `no-new-privileges` enabled. Its health response does
not test OSIRIS or reveal configuration. The build also places the Corresponding
Source in `/usr/src/osiris-mcp` inside the image.

On Docker Desktop, services running directly on the host are reachable from the
container as `host.docker.internal`. The included local OAuth overlay also maps
the `osiris.test` virtual host to the Docker host.

For the local Keycloak setup described below, keep its public issuer at
`http://127.0.0.1:8080/realms/osiris` so browser discovery remains stable, and
start OSIRIS MCP with:

```bash
docker compose -f compose.yaml -f compose.local-oauth.yaml up --build -d
```

The overlay changes the container's back-channel introspection URL to
`host.docker.internal`, while retaining `127.0.0.1:8080` as its HTTP `Host`
header. This is necessary because local Keycloak tokens use the public issuer
hostname and Keycloak otherwise treats them as inactive during introspection.
The overlay also sets the public MCP URL to the published port `8765` and
explicitly permits unencrypted introspection on this trusted local Docker
bridge. It must not be used for a production deployment. Stop this stack with:

```bash
docker compose -f compose.yaml -f compose.local-oauth.yaml down
```

The command-line entry point supports these transport settings:

- `OSIRIS_MCP_TRANSPORT`: `stdio` (default) or `streamable-http`
- `OSIRIS_MCP_HOST`: `127.0.0.1`, `localhost`, or `0.0.0.0`
- `OSIRIS_MCP_PORT`: internal HTTP port, default `8000`
- `OSIRIS_MCP_PATH`: MCP path, default `/mcp`
- `OSIRIS_MCP_PUBLISHED_PORT`: host port used by Compose, default `8765`
- `OSIRIS_MCP_AUTH_MODE`: `none`, `api-key`, or `oauth`

For orchestrator-managed secrets, omit `OSIRIS_API_KEY` and set
`OSIRIS_API_KEY_FILE` to a mounted secret file instead. Configuring both is
rejected to avoid ambiguous secret precedence.

## Inbound MCP authentication

Authentication protects access from an MCP client to this server. It is
separate from `OSIRIS_API_KEY`, which the server uses for its downstream calls
to OSIRIS. Authentication applies only to Streamable HTTP; stdio relies on the
security boundary of the process that launches it.

### OAuth/OIDC resource-server mode

`oauth` is the production mode for remotely reachable installations. OSIRIS MCP
does not implement login, consent, or token issuance. An external authorization
server such as Keycloak or another institutional provider with an RFC 7662
introspection endpoint does that. OSIRIS MCP validates every access token
through that endpoint and verifies activity, expiry, issuer, audience, and the
required scopes.

```dotenv
OSIRIS_MCP_TRANSPORT=streamable-http
OSIRIS_MCP_AUTH_MODE=oauth
OSIRIS_MCP_PUBLIC_URL=https://mcp.example.org/mcp
OSIRIS_MCP_OAUTH_ISSUER_URL=https://login.example.org/realms/osiris
OSIRIS_MCP_OAUTH_INTROSPECTION_URL=https://login.example.org/realms/osiris/protocol/openid-connect/token/introspect
OSIRIS_MCP_OAUTH_CLIENT_ID=osiris-mcp
OSIRIS_MCP_OAUTH_CLIENT_SECRET_FILE=/run/secrets/oauth_client_secret
OSIRIS_MCP_OAUTH_REQUIRED_SCOPES=osiris:read
```

The public URL must identify the exact MCP endpoint, including its path. HTTPS
is mandatory outside localhost. By default the token audience must equal this
URL; set `OSIRIS_MCP_OAUTH_AUDIENCE` only when the identity provider uses a
different API audience identifier. The MCP SDK publishes RFC 9728 Protected
Resource Metadata and returns standards-compliant `401` and `403` challenges,
allowing capable clients to discover the authorization server automatically.

The introspection client secret is an identity-provider credential and should
be mounted as a secret file. It is never forwarded to OSIRIS. The access token
received from the MCP client is likewise never passed to OSIRIS; downstream
requests always use the dedicated `OSIRIS_API_KEY`.

HTTP introspection on a non-loopback hostname is rejected by default. The
`OSIRIS_MCP_OAUTH_ALLOW_INSECURE_INTROSPECTION` escape hatch exists only for the
local Docker bridge overlay. Production introspection must use HTTPS.
When a private back-channel URL reaches the same authorization server through a
different hostname, `OSIRIS_MCP_OAUTH_INTROSPECTION_HOST_HEADER` can explicitly
preserve the public issuer's HTTP host. Leave it unset unless the authorization
server or reverse proxy requires this routing behavior.

### Static API-key mode

`api-key` is a simpler option for a controlled internal network or a single
trusted client that supports fixed HTTP headers. Generate a random secret of at
least 32 characters and configure the client to send it on every MCP request:

```dotenv
OSIRIS_MCP_TRANSPORT=streamable-http
OSIRIS_MCP_AUTH_MODE=api-key
OSIRIS_MCP_API_KEY_FILE=/run/secrets/osiris_mcp_api_key
```

```http
Authorization: Bearer <OSIRIS_MCP_API_KEY>
```

For local Compose, place the key in the ignored `secrets/` directory and add
the mount to `compose.override.yaml`:

```yaml
services:
  osiris-mcp:
    volumes:
      - ./secrets/osiris_mcp_api_key:/run/secrets/osiris_mcp_api_key:ro
```

This mode uses constant-time secret comparison, rejects missing or malformed
credentials with `401`, and leaves `/health` public. It intentionally publishes
no OAuth discovery metadata and therefore does not provide interactive login,
individual user identities, scopes, or automatic token rotation. Use it behind
TLS and network restrictions; prefer OAuth for multi-user or public deployments.

`none` remains available for stdio and loopback-only development. The server
rejects `api-key` or `oauth` configuration with stdio so operators cannot assume
that a pipe is protected by HTTP authentication.

Open it in the MCP Inspector:

```bash
uv run mcp dev src/osiris_mcp/server.py:mcp
```

## Configuration

Copy `.env.example` to `.env` and adjust it for a development OSIRIS instance.
Never commit `.env` or real API keys.

Set `OSIRIS_MCP_SOURCE_URL` to the public repository containing the exact source
code of the deployed version. This value is exposed by `server_info`. Operators
who make a modified version available over a network must point it to the
Corresponding Source of that modified version as required by AGPL section 13.

For a dedicated MCP client, configure both `OSIRIS_CLIENT_ID` and
`OSIRIS_API_KEY`. In OSIRIS, allow the client to use the MCP API area and grant
only the read permissions required by the enabled tools. The legacy global API
key remains supported without a client ID, but is unrestricted and should be
avoided for new installations.

The available read-only tools are:

- `server_info`: shows non-sensitive server, connection, license, and source-code
  information.
- `get_instance_info`: describes the connected OSIRIS installation, enabled
  features, catalog sizes, and supported project filters.
- `list_units`: resolves human-readable organizational unit names to the exact
  IDs used by this OSIRIS installation.
- `list_topics`: resolves research topic names to exact IDs and explicitly
  reports when the installation has no topic catalog.
- `list_activity_types`: lists the exact activity category and subtype IDs used
  by the installation.
- `search_activities`: searches activities while returning only a compact
  citation-centered evidence bundle.
- `get_activity`: retrieves the same compact representation for one activity.
- `search_people`: resolves names, usernames, aliases, and ORCIDs to exact
  OSIRIS person IDs without exposing contact or account metadata.
- `get_person`: retrieves a compact research profile for one exact username.
- `search_experts`: searches curated expertise and research fields and returns
  explicit evidence for every match. When enabled, OpenAlex publication topics
  are included as lower-priority evidence.
- `search_projects`: searches projects through the dedicated
  `/api/mcp/projects` OSIRIS endpoint using fixed filters and a fixed field
  allowlist.
- `get_project`: retrieves the allowlisted details of one project by ID.

Activity date filters use `date_field=start` by default; for example,
`from_date=2026-09-01` and `to_date=2026-09-30` select activities starting in
September 2026. Set `date_field=end` to select activities completed in that
period, such as completed theses. Activity searches include only affiliated
records and exclude Online-ahead-of-print records by default. Exceptional
searches can opt in with `include_unaffiliated=true` or
`include_online_ahead_of_print=true`. Project searches can be narrowed by a
free-text query, an `active_on` date in `YYYY-MM-DD` format, exact status, topic,
organizational unit, and result limit.
Topic and unit filters always require exact instance-specific IDs. Clients
should obtain them with `list_topics` and `list_units` rather than guessing.

## Complete result lists

List and search tools return bounded pages so a large OSIRIS installation cannot
overflow a single MCP response. Every page contains `count`, `total`, `offset`,
`limit`, `has_more`, and `next_offset`. To obtain a complete result list, keep
the original filters unchanged and pass the returned `next_offset` into the next
call until `has_more` is `false`. Organizational-unit and topic resources follow
the same pagination internally and therefore return their complete catalogs.

The same discovery information is available as MCP resources for clients that
use resource discovery:

- `osiris://instance`
- `osiris://units`
- `osiris://topics`
- `osiris://activity-types`

The recommended client flow is to read `get_instance_info` first, resolve any
topic or unit mentioned by a user through the corresponding catalog tool, and
only then pass the returned ID to `search_projects`. Tools mirror the resources
because some MCP hosts do not automatically load resources into the model's
context.

OSIRIS provides these dedicated endpoints to the MCP adapter:

- `GET /api/mcp/instance`
- `GET /api/mcp/units`
- `GET /api/mcp/topics`
- `GET /api/mcp/activity-types`
- `GET /api/mcp/activities`
- `GET /api/mcp/activities/{id}`
- `GET /api/mcp/persons`
- `GET /api/mcp/persons/{username}`
- `GET /api/mcp/experts`
- `GET /api/mcp/projects`
- `GET /api/mcp/projects/{id}`

OSIRIS authenticates this adapter as a dedicated API client. Client secrets are
stored as hashes, can be rotated or disabled independently, and are restricted
to the MCP API area and explicitly granted read permissions.

## Safe errors and request IDs

Every OSIRIS MCP API request receives a server-generated identifier in the form
`req_<32 hexadecimal characters>`. It is returned in the `X-Request-ID` header
for successful and unsuccessful responses. Error responses also contain the
same value as `request_id` in their JSON body.

Expected validation and not-found responses remain machine-readable.
Unexpected PHP errors are logged inside OSIRIS with their request ID and MCP
endpoint, while the caller receives only a generic HTTP 500 response—never a
stack trace, source path, database error, or raw exception message. Buffered
warnings and stray output are discarded before the JSON response is sent.

The Python adapter does not forward OSIRIS error messages or rejected response
values to the MCP client. It emits a stable description and the validated
request ID, when one was received. This gives administrators a useful support
reference without exposing server details to the language model. Transport
failures are reported generically because no server-side request ID exists.
Expected errors are explicitly marked as safe MCP tool errors so the model can
read this description. Unexpected exceptions remain masked by the MCP runtime.
If local input validation fails before an HTTP request is made, the error states
that OSIRIS was not called and therefore no request ID exists. HTTPX request
logging is restricted to warnings and errors because complete request URLs can
contain names, search terms, or other sensitive query parameters.

## Compact activity representation

Activity documents can contain extensive editing history, metrics, external
metadata, and HTML renderings. The MCP API does not expose those raw fields.
Search and detail results share one small contract containing only:

- ID, exact type and subtype, and title
- start and end date
- linked OSIRIS persons and organizational units
- the plain-text `citation` rendered by OSIRIS
- stable identifiers such as DOI or PubMed ID, when present
- affiliation and Online-ahead-of-print status
- optional bibliometric values, including their available reference or
  retrieval dates
- a source URL added by the MCP adapter

Free-text search may inspect the title, abstract, and rendered citation on the
OSIRIS side, but the verbose source fields are not returned to the model.
Bibliometric values are contextual evidence and must not be treated as a
standalone measure of the quality of a publication or researcher.

## Person and expertise search

Identity resolution and expertise discovery are separate operations.
`search_people` uses the OSIRIS person search field and returns only name,
position, current units, active status, and profile URL. `get_person` adds ORCID,
expertise, research interests, OSIRIS topics, and the sanitized research profile.
When a unit filter is supplied, only assignments active on the current date are
matched. A missing or null start date has no lower bound; a missing or null end
date has no upper bound.

`search_experts` searches only curated expertise, research interests, research
profiles, and OSIRIS research topics. It deliberately does not search general
biographies. If the Research Spectrum feature is enabled, matching OpenAlex
topics from affiliated publications are added as clearly identified evidence
with a lower relevance weight than curated profile data.

Email addresses, phone numbers, gender, login history, account roles, internal
IDs, biographies, social profiles, and user-interface settings are never part of
these MCP responses.

## License

OSIRIS MCP is free software licensed under the GNU Affero General Public License,
version 3 or any later version (`AGPL-3.0-or-later`). You may use, modify,
distribute, and commercially operate the software under the conditions of that
license. In particular, operators of a modified version that users interact with
remotely over a network must offer those users access to the Corresponding Source
of the deployed version.

Copyright © 2026 Julia Koblitz, OSIRIS Solutions GmbH.

See [LICENSE](LICENSE) for the complete license text and
[CONTRIBUTING.md](CONTRIBUTING.md) for contribution requirements. This license
applies to the standalone Python connector in this repository; it does not by
itself change the license of the separate OSIRIS Core repository.
