FROM python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2 AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY packages/persistence packages/persistence
COPY services/notification-worker services/notification-worker
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install \
      ./packages/persistence \
      ./services/notification-worker

FROM python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2
LABEL org.opencontainers.image.source="https://github.com/Gnaiem686/Tasks-Management" \
      org.opencontainers.image.title="workforce-notification-worker"
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
USER 10001:10001
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD ["python", "-c", "import os; os.kill(1, 0)"]
CMD ["python", "-m", "notification_worker.main"]
