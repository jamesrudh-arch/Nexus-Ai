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
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1001 nexus \
    && useradd --system --uid 1001 --gid nexus --home-dir /app --shell /usr/sbin/nologin nexus

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY migrations ./migrations

# CVE-2025-47273 — setuptools before 78.1.1: `PackageIndex.download` derives a filename from an
# unquoted URL segment and joins it onto a temp directory, so a crafted URL writes anywhere the
# process can (CVSS 8.8 HIGH). The base image ships 70.3.0. Nothing here calls that API — the
# runtime installs no packages — but the code being present *is* the finding, and "unreachable in
# practice" belongs in the record rather than in the image.
#
# Removed, not upgraded. Upgrading was tried first (`pip install --upgrade "setuptools>=78.1.1"`
# against the system interpreter, before the venv was copied in) and the scan still reported
# 70.3.0, so the copy Trivy read was not the copy that command touched. Rather than keep guessing
# which interpreter owns it, both are cleared and the build then asserts the outcome: if either
# can still import setuptools, or any `setuptools*.dist-info` survives — which is what Trivy
# actually keys on, and what a plain `pip uninstall` can leave behind — this RUN fails and no
# image is produced. A fix that verifies itself beats one that is argued for, especially here,
# where no container can be started to check.
#
# Safe to remove, and checked rather than assumed: no installed distribution imports
# `pkg_resources` (grepped every `*.py` under site-packages; the only hits were setuptools
# itself and pytest, which is a dev extra and is not installed in this image), and uvloop's
# `Requires-Dist: setuptools` is gated on `extra == "dev"`.
#
# The RUN below does three things, in order: uninstall from both interpreters; delete any
# surviving `setuptools*`/`pkg_resources` directory, because pip can leave the dist-info behind
# and the dist-info is precisely what a scanner reads; then assert the result. The assertion is
# the point — `test -z` fails the build if anything matches, and the two `! python -c import`
# checks fail it if either interpreter can still load the package. No image is produced unless
# setuptools is genuinely gone from both.
RUN set -eux; \
    /usr/local/bin/python -m pip uninstall -y setuptools || true; \
    /opt/venv/bin/python -m pip uninstall -y setuptools || true; \
    find /usr/local/lib /opt/venv/lib -maxdepth 4 \
         \( -name 'setuptools*' -o -name 'pkg_resources' \) -exec rm -rf {} + || true; \
    test -z "$(find /usr/local/lib /opt/venv/lib \
               \( -name 'setuptools*' -o -name 'pkg_resources' \) -print -quit)"; \
    ! /usr/local/bin/python -c 'import setuptools'; \
    ! /opt/venv/bin/python -c 'import setuptools'

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
