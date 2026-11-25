# NEXUS core — Phase 3 (core foundation + market data / instrument master)
# Multi-stage, non-root, no paid base image. python:3.12-slim is multi-arch, so this
# builds natively on the Oracle Always Free Ampere A1 (ARM64) host and on x86 dev machines.
#
# Extras installed: `archive` (pyarrow + duckdb — the first-party Parquet tick/bar store)
# and `streams` (websockets — real-time public venue feeds). Both are free/OSS (D-019).
# `postgres` and `nats` are installed for the compose stack. Still no venue trading
# dependency and no credential of any kind is baked into the image.

# ---------------------------------------------------------------- build stage
FROM python:3.12-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

# Build deps for wheels that need compiling on ARM64.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip wheel \
    && /opt/venv/bin/pip install ".[archive,streams,postgres,nats]"

# ---------------------------------------------------------------- runtime stage
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    # Fail closed: no implicit network egress to paid services, no telemetry.
    NEXUS_LIVE_TRADING_ENABLED=false \
    NEXUS_MODEL_ALLOW_PAID_APIS=false \
    DO_NOT_TRACK=1

# curl for the healthcheck only; no shell-based tooling beyond it.
#
# setuptools is upgraded because the base image ships 70.3.0, which carries CVE-2025-47273:
# `PackageIndex.download` derives a filename from an unquoted URL segment and joins it onto a
# temp directory, so a crafted URL yields an arbitrary file write with the process's
# permissions (fixed in 78.1.1, CVSS 8.8 HIGH). Nothing in this image ever calls that API — the
# runtime installs no packages — but the code is present, so Trivy reports it, and "unreachable
# in practice" is an argument to make in the record rather than a reason to ship it.
#
# Upgraded rather than removed: removal would be the smaller surface, but no container is ever
# started in this sandbox, so a dependency that imports `pkg_resources` would break only in
# production. Revisit on the first real `docker compose up` (docs/05 §5). The Trivy scan blocks
# on HIGH again, so dropping this line fails CI.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && /usr/local/bin/python -m pip install --no-cache-dir --upgrade "setuptools>=78.1.1" \
    && groupadd --system --gid 1001 nexus \
    && useradd --system --uid 1001 --gid nexus --home-dir /app --shell /usr/sbin/nologin nexus

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY migrations ./migrations

# Data directory for the SQLite audit store on single-host deployments. Owned by nexus,
# never world-writable.
RUN mkdir -p /app/data && chown -R nexus:nexus /app

USER nexus

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

# Bound to 0.0.0.0 inside the container network only; Caddy is the public entry point and
# the compose file does not publish this port to the host.
CMD ["uvicorn", "nexus.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
