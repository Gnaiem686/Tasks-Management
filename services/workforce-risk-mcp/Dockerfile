FROM python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2 AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY domain domain
COPY packages packages
COPY services/workforce-risk-mcp services/workforce-risk-mcp
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install \
      ./domain \
      ./packages/contracts \
      ./packages/jira-mcp-client \
      ./packages/persistence \
      ./services/workforce-risk-mcp

FROM python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2
LABEL org.opencontainers.image.source="https://github.com/Gnaiem686/Tasks-Management" \
      org.opencontainers.image.title="workforce-risk-mcp"
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY config config
COPY packages/persistence/alembic.ini /app/alembic.ini
COPY packages/persistence/migrations /app/migrations
USER 10001:10001
EXPOSE 8001
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import socket; socket.create_connection(('127.0.0.1', 8001), 2).close()"]
CMD ["python", "-m", "workforce_risk_mcp.server"]
