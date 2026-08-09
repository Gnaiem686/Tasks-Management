FROM python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2 AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY services/devops-mcp services/devops-mcp
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install ./services/devops-mcp

FROM python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2
LABEL org.opencontainers.image.source="https://github.com/Gnaiem686/Tasks-Management" \
      org.opencontainers.image.title="workforce-devops-mcp"
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
USER 10001:10001
EXPOSE 8002
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import socket; socket.create_connection(('127.0.0.1', 8002), 2).close()"]
CMD ["python", "-m", "devops_mcp.server"]
