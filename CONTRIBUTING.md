# Contributing to OSIRIS MCP

Thank you for helping improve OSIRIS MCP.

## License of contributions

OSIRIS MCP is licensed under `AGPL-3.0-or-later`. By submitting a contribution,
you agree that your contribution is made available under the same license and
that you have the right to submit it.

## Developer Certificate of Origin

Every commit in a contribution must include a `Signed-off-by` line certifying
the [Developer Certificate of Origin 1.1](https://developercertificate.org/):

```text
Signed-off-by: Your Name <your.email@example.org>
```

Git can add this line automatically when creating a commit:

```bash
git commit --signoff
```

The sign-off is a contribution certification, not a transfer of copyright.

## Source availability

If you operate a modified version over a network, ensure that `server_info`
points users to the complete Corresponding Source of the deployed version by
setting `OSIRIS_MCP_SOURCE_URL`. Keep modification notices and relevant dates as
required by the license.

## Development checks

Install the development dependencies and run the test suite before submitting a
change:

```bash
uv sync
uv run pytest
```
