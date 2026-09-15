# OSIRIS MCP

OSIRIS MCP is a read-only Model Context Protocol server for controlled access to
research information stored in OSIRIS.

The project is intentionally split into two layers:

1. OSIRIS remains responsible for data access and authorization.
2. This MCP server exposes a small allowlist of typed, auditable tools.

The current implementation is an initial development scaffold. Before exposing
it publicly, review the deployment end to end, including TLS, network access,
logging, rate limits, and the scopes granted to its dedicated API client.

## Development setup

```bash
uv sync
uv run pytest
```

Start the local stdio server:

```bash
uv run osiris-mcp
```

Open it in the MCP Inspector:

```bash
uv run mcp dev src/osiris_mcp/server.py:mcp
```

## Configuration

Copy `.env.example` to `.env` and adjust it for a development OSIRIS instance.
Never commit `.env` or real API keys.

For a dedicated MCP client, configure both `OSIRIS_CLIENT_ID` and
`OSIRIS_API_KEY`. In OSIRIS, allow the client to use the MCP API area and grant
only the read permissions required by the enabled tools. The legacy global API
key remains supported without a client ID, but is unrestricted and should be
avoided for new installations.

The available read-only tools are:

- `server_info`: shows non-sensitive server and connection information.
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

Project searches can be narrowed by a free-text query, an `active_on` date in
`YYYY-MM-DD` format, exact status, topic, organizational unit, and result limit.
Topic and unit filters always require exact instance-specific IDs. Clients
should obtain them with `list_topics` and `list_units` rather than guessing.

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

## Compact activity representation

Activity documents can contain extensive editing history, metrics, external
metadata, and HTML renderings. The MCP API does not expose those raw fields.
Search and detail results share one small contract containing only:

- ID, exact type and subtype, and title
- start and end date
- linked OSIRIS persons and organizational units
- the plain-text `citation` rendered by OSIRIS
- stable identifiers such as DOI or PubMed ID, when present
- a source URL added by the MCP adapter

Free-text search may inspect the title, abstract, and rendered citation on the
OSIRIS side, but the verbose source fields are not returned to the model.

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
