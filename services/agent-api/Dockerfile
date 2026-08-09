FROM python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2 AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY domain domain
COPY packages packages
COPY services/agent-api services/agent-api
COPY scripts/validation/verify_ui_assets.py scripts/validation/verify_ui_assets.py
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install \
      ./domain \
      ./packages/contracts \
      ./packages/jira-mcp-client \
      ./packages/observability \
      ./packages/persistence \
      ./services/agent-api \
    && /opt/venv/bin/python scripts/validation/verify_ui_assets.py \
      --source services/agent-api/src/agent_api/web \
      --installed /opt/venv/lib/python3.12/site-packages/agent_api/web

FROM python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2
LABEL org.opencontainers.image.source="https://github.com/Gnaiem686/Tasks-Management" \
      org.opencontainers.image.title="workforce-agent-api"
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY config config
COPY tests/fixtures/scenarios tests/fixtures/scenarios
USER 10001:10001
EXPOSE 8000
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=2)"]
CMD ["uvicorn", "agent_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
