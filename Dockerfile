# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:0.12.1 AS uv

FROM python:3.12-slim-bookworm AS builder

COPY --from=uv /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock README.md CONTRIBUTING.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev --no-editable


FROM python:3.12-slim-bookworm AS runtime

ARG SOURCE_URL=""

LABEL org.opencontainers.image.title="OSIRIS MCP" \
      org.opencontainers.image.description="Secure read-only MCP access to OSIRIS" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later" \
      org.opencontainers.image.source="${SOURCE_URL}"

RUN groupadd --system --gid 10001 osiris \
    && useradd --system --uid 10001 --gid osiris \
        --home-dir /nonexistent --shell /usr/sbin/nologin osiris

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
RUN mkdir -p /usr/src/osiris-mcp
COPY --chown=10001:10001 \
    pyproject.toml uv.lock README.md CONTRIBUTING.md LICENSE \
    Dockerfile compose.yaml .env.example \
    /usr/src/osiris-mcp/
COPY --chown=10001:10001 src /usr/src/osiris-mcp/src
COPY --chown=10001:10001 tests /usr/src/osiris-mcp/tests

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OSIRIS_MCP_TRANSPORT=streamable-http \
    OSIRIS_MCP_HOST=0.0.0.0 \
    OSIRIS_MCP_PORT=8000 \
    OSIRIS_MCP_PATH=/mcp

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).read()"]

ENTRYPOINT ["osiris-mcp"]
