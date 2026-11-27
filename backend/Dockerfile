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
# tzdata is not optional. `nexus.instruments.sessions` builds `ZoneInfo("America/New_York")` at
# *import* time, and `nexus.api.app` — the module the CMD below executes — imports it. Without the
# IANA database that import raises ZoneInfoNotFoundError and the container dies before it binds a
# port. Installing it explicitly rather than relying on whatever the base image happens to ship:
# `slim` variants have dropped it before, and correctness must not depend on an incidental package.
#
# `apt-get dist-upgrade` is here because the base image carries Debian's own packages and they go stale
# between rebuilds. On 2026-11-26 the scan blocked the build on CVE-2025-6020, reported against four
# PAM packages at `1.5.2-6+deb12u2` with the fix at `1.5.2-6+deb12u3`: libpam0g, libpam-runtime,
# libpam-modules and libpam-modules-bin, all of them shipped by `python:3.12-slim-bookworm` and none
# of them installed by anything in this file. Nothing in this commit changed the image, so the finding
# is upstream drift — exactly what the nightly schedule in `ci.yml` exists to catch, and what a
# documents-only push surfaced anyway.
#
# The fix is to upgrade, not to justify. The scanner's own annotation says a fixed version exists, and
# `ignore-unfixed: true` means every finding it reports is one that upgrading can clear; suppressing a
# fixable HIGH would be the one move this file's history argues against (see the setuptools finding
# below, which was proven a false positive by measurement rather than ignored).
#
# Reachability is NOT claimed here, because it was never established. What this file guarantees is a
# non-root user (uid 1001) with a nologin shell, and nothing in this repository installs a login path, an
# sshd or a sudo; whether the base image nevertheless carries `su` or another PAM consumer was never
# checked, because no Docker daemon exists here to check it with. So the honest claim is "probably
# unreachable, unverified" — and a one-step upgrade beats an unverified judgement about an image this
# file does not control.
# Only this stage upgrades: the builder stage's packages never reach the image, so upgrading them
# would cost build time and change nothing the scanner reads.
#
# `dist-upgrade` rather than `upgrade` because `upgrade` silently skips a package whose fix needs a new
# dependency, and a skipped security fix is precisely the failure being prevented here.
#
# The assertion is targeted at the finding rather than generic, and that division of labour is deliberate:
# Trivy is already the generic gate — it fails this build if any HIGH with an available fix survives, for
# any package, forever, so nothing here needs to restate it. What a scanner cannot say is whether the
# upgrade that was supposed to clear a *named* finding actually ran, and a `dist-upgrade` that silently
# did nothing would leave the build green today and red tomorrow for a reason nobody could see. So this
# checks the four packages CVE-2025-6020 was reported against and no others: it passes on any later point
# release (`deb12u3`, `u4`, …), it cannot fail on an unrelated hold, and if it does fail the message names
# the package. Exit code 27 is named in the legend line below and continues the numbering the
# pip-removal block uses (21–26); it is deliberately not folded into that block, which appears later in
# this file, because a test pins 21–26 there as a property and renumbering six working codes to make room
# for one new one would break a check that has already caught a real defect. No Docker daemon exists in
# the environment this file is written in, so the CI build is the only place this assertion can run
# against a real dpkg-query — the same reason that block asserts its outcome instead of trusting it. Its
# shell semantics are nevertheless measured rather than argued for:
# tests/test_repo_hygiene.py::test_the_runtime_stage_upgrades_and_proves_the_named_finding_is_gone
# extracts the assertion below and executes it against a model of dpkg-query over eight fixtures.
#   27 a libpam package is still at the version CVE-2025-6020 was reported against
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends curl tzdata; \
    apt-get dist-upgrade -y; \
    ! dpkg-query -W -f='${Package} ${Version}\n' 'libpam*' | grep -q 'deb12u2$' || exit 27; \
    rm -rf /var/lib/apt/lists/*; \
    groupadd --system --gid 1001 nexus; \
    useradd --system --uid 1001 --gid nexus --home-dir /app --shell /usr/sbin/nologin nexus

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY migrations ./migrations

# CVE-2025-47273 (setuptools < 78.1.1; path traversal in `PackageIndex._download_url`, CVSS 8.8
# HIGH) is reported against this image, and it is a false positive — proven by measurement in CI,
# not argued.
#
# setuptools is not installed anywhere in this image. A probe run on the base image and on the
# builder stage (the two images this one is assembled from) reports `ModuleNotFoundError: No module
# named 'setuptools'` from both interpreters, and a whole-filesystem search finds no setuptools
# package and no setuptools distribution metadata. What the scanner actually reads is
# `pip/_vendor/bom.cdx.json`: pip ships a CycloneDX SBOM listing its own vendored dependencies,
# and that manifest declares `pkg:pypi/setuptools@70.3.0`. It is a version string inside a text
# file, not an installation, and nothing imports it.
#
# That is why the two fixes tried before this one could not have worked:
#   - upgrading setuptools touched a package that was not installed, and no pip command can rewrite
#     a version baked into pip's own vendored SBOM;
#   - removing setuptools removed nothing, and the assertion that followed then failed the build on
#     pip's vendored `pkg_resources` directory — a real, necessary part of pip that has nothing to
#     do with the finding.
#
# The check below is deliberately narrower than "no SBOM survives". Asserting that was tried, and
# the build failed on `psycopg_binary-3.3.9.dist-info/sboms/auditwheel.cdx.json` — a second SBOM
# carrier that says nothing about setuptools. That conclusion had been drawn from a local venv,
# which does not install the `postgres` extra; the builder stage does, and so does the image. What
# matters is not the presence of manifests but whether any of them declares the package.
#
# So pip itself goes, from both interpreters. This is not suppression: there is no ignore file, no
# manifest deleted to hide a finding, and the scan stays fully blocking on HIGH and CRITICAL. The
# runtime installs no packages — nothing under src/nexus shells out to pip — so a package installer
# in the image is attack surface with no benefit: a compromised process could otherwise fetch and
# install anything it liked. pip is also the only carrier of an SBOM here (verified by searching
# every `*.cdx.json` in the tree), so removing it removes the declaration at its source and leaves
# the scanner nothing to misread.
#
# The build then asserts the outcome instead of trusting the uninstall, because no container can be
# started in CI to check by hand. The last assertion is the one that makes removing pip safe to do
# blind: the entrypoint module the CMD runs must still import from the venv, which also proves
# tzdata is really present. If any of these fail, no image is produced.
#
# Each check exits with its own code, because CI publishes the failing command line but not the
# build log: a single RUN with six assertions can only say "one of these failed".
#   21 pip or setuptools distribution metadata survived the removal
#   22 an SBOM in the image still declares setuptools — the artifact the scanner reads
#   23 the system interpreter can still import setuptools
#   24 the venv interpreter can still import setuptools
#   25 the venv can still import pip
#   26 the module the CMD runs cannot be imported from the venv
RUN set -eux; \
    /usr/local/bin/python -m pip uninstall -y pip setuptools || true; \
    /opt/venv/bin/python -m pip uninstall -y pip setuptools || true; \
    rm -f /usr/local/bin/pip* /opt/venv/bin/pip*; \
    find /usr/local/lib /opt/venv/lib -maxdepth 3 \
         \( -name 'pip' -o -name 'pip-*.dist-info' -o -name 'setuptools*' \) \
         -exec rm -rf {} + || true; \
    test -z "$(find /usr/local/lib /opt/venv/lib -maxdepth 3 \
               \( -name 'pip' -o -name 'pip-*.dist-info' -o -name 'setuptools*' \) \
               -print -quit)" || exit 21; \
    test -z "$(grep -rl setuptools --include='*.cdx.json' --include='*.spdx.json' \
               /usr/local/lib /opt/venv/lib 2>/dev/null)" || exit 22; \
    ! /usr/local/bin/python -c 'import setuptools' || exit 23; \
    ! /opt/venv/bin/python -c 'import setuptools' || exit 24; \
    ! /opt/venv/bin/python -c 'import pip' || exit 25; \
    /opt/venv/bin/python -c 'import nexus.api.app as m; assert callable(m.create_app)' || exit 26

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
