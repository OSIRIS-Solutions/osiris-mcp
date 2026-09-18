# Releasing OSIRIS MCP

OSIRIS MCP is published to PyPI through GitHub Actions and PyPI Trusted
Publishing. No long-lived PyPI API token is stored in GitHub.

## One-time PyPI setup

While signed in to PyPI, open the account-level **Publishing** page and add a
pending GitHub publisher with these exact values:

- PyPI project name: `osiris-mcp`
- GitHub owner: `OSIRIS-Solutions`
- GitHub repository: `osiris-mcp`
- Workflow filename: `publish.yml`
- Environment name: `pypi`

The pending publisher creates the PyPI project during the first successful
release. It then becomes the project's normal trusted publisher.

## One-time GitHub setup

Create a GitHub environment named `pypi`. Requiring manual approval for this
environment is recommended so publishing always has a deliberate final gate.
No environment secret is needed.

## Release procedure

1. Update `__version__` in `src/osiris_mcp/__init__.py` using semantic
   versioning.
2. Run `uv sync --locked --dev`, `uv run pytest`, and `uv build` locally.
3. Commit the version change and merge it into `main`.
4. Create and publish a GitHub release whose tag is the package version prefixed
   with `v`, for example `v0.1.0`.
5. Approve the `pypi` environment deployment when GitHub requests it.
6. Verify the release on `https://pypi.org/project/osiris-mcp/` and test it with
   `uvx --from osiris-mcp==<version> osiris-mcp`.

The publishing workflow refuses to upload when the Git tag and package version
do not match. PyPI versions are immutable; publish a new version instead of
trying to replace an existing file.
