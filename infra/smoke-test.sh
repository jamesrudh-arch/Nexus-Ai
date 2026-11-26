#!/bin/sh
# NEXUS bring-up smoke test — starts the stack for real and proves it serves.
#
# Why this exists: everything before Phase 4 verified that the image *builds* and that its
# entrypoint *imports*. Neither says anything about whether a process serves a request, whether the
# non-root user can write its audit database, whether the HEALTHCHECK ever answers, or whether the
# audit chain survives a restart. This is step B-1/B-2/B-3 of docs/06 §3.
#
# Usage:
#   infra/smoke-test.sh                      # from the repository root
#   SMOKE_SERVICES="core" infra/smoke-test.sh  # core alone, on a memory-constrained host
#
# It runs under a **separate compose project name** (`nexus-smoke` by default) so it cannot touch a
# real deployment's containers or volumes, and it tears down what it created. On the Oracle VM this
# is safe to run alongside a live stack; it is still a test, not a deployment.
#
# Every check runs — a failure is recorded and the script continues, because one full report is
# worth more than six CI runs that each die on the first problem. Exit status is non-zero if any
# check failed.

set -u

PROJECT="${SMOKE_PROJECT:-nexus-smoke}"
# `db` is opt-in since R-1 (D-042): core does not connect to TimescaleDB, so the smoke stack is
# nats + core. Set SMOKE_SERVICES="db nats core" to smoke the postgres profile as well.
SERVICES="${SMOKE_SERVICES:-nats core}"
REPORT="${SMOKE_REPORT:-smoke-report.txt}"
WAIT_SECONDS="${SMOKE_WAIT_SECONDS:-300}"
IMAGE="${SMOKE_IMAGE:-nexus-core:0.2.0}"
# Project-scoped, so destroying them cannot touch a real deployment's data.
DESTROY_VOLUMES="${SMOKE_DESTROY_VOLUMES:-1}"

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT" || exit 2
CHECKER="infra/smoke_check.py"

# Compose interpolates the whole file, so every `${VAR:?}` must be set even for services this run
# does not start. These are throwaway values for a test that creates no persistent state and are
# not credentials; a real deployment sets them in .env, which is never committed.
: "${POSTGRES_PASSWORD:=smoke-only-not-a-credential}"
: "${MINIO_ROOT_USER:=smoke-only}"
: "${MINIO_ROOT_PASSWORD:=smoke-only-not-a-credential}"
: "${GRAFANA_ADMIN_PASSWORD:=smoke-only-not-a-credential}"
export POSTGRES_PASSWORD MINIO_ROOT_USER MINIO_ROOT_PASSWORD GRAFANA_ADMIN_PASSWORD

FAILED=0
: > "$REPORT"

log() { printf '%s\n' "$*" | tee -a "$REPORT"; }
pass() { log "PASS $*"; }
fail() { FAILED=1; log "FAIL $*"; }

compose() { docker compose -p "$PROJECT" "$@"; }

# Run a small Python program inside core. Piped via stdin rather than passed as `-c` so the quoting
# survives three levels of shell without escapes.
in_core() { compose exec -T core python - "$@"; }

read_api() {  # read_api <path> <dotted.field>
    in_core "$1" "$2" <<'PY'
import json, sys, urllib.request
path, field = sys.argv[1], sys.argv[2]
with urllib.request.urlopen("http://127.0.0.1:8000" + path, timeout=20) as response:
    data = json.load(response)
for part in field.split("."):
    data = data[part]
print(data)
PY
}

count_rows() {  # independent of the API: read the durable table straight off the volume
    in_core <<'PY'
import sqlite3
print(sqlite3.connect("/app/data/nexus.db").execute("SELECT count(*) FROM audit_log").fetchone()[0])
PY
}

health_status() {
    id=$(compose ps -q core 2>/dev/null)
    [ -n "$id" ] && docker inspect -f '{{.State.Health.Status}}' "$id" 2>/dev/null
}

wait_for_endpoint() {
    waited=0
    while [ "$waited" -lt "$WAIT_SECONDS" ]; do
        if in_core >/dev/null 2>&1 <<'PY'
import urllib.request
urllib.request.urlopen("http://127.0.0.1:8000/healthz", timeout=5)
PY
        then
            return 0
        fi
        sleep 3
        waited=$((waited + 3))
    done
    return 1
}

dump_logs() {
    log "--- docker compose ps ---"
    compose ps 2>&1 | tee -a "$REPORT"
    log "--- last 120 lines of core's log ---"
    compose logs --tail=120 core 2>&1 | tee -a "$REPORT"
}

log "NEXUS smoke test: project=$PROJECT services='$SERVICES' image=$IMAGE"
log "host: $(uname -srm) · docker: $(docker --version 2>/dev/null | head -1 || echo 'not installed')"

# ---------------------------------------------------------------- 0. prerequisites
if [ ! -f "$CHECKER" ]; then
    fail "$CHECKER is missing — nothing can be asserted inside the container"
    exit 1
fi
if ! docker info >/dev/null 2>&1; then
    fail "the docker daemon is not reachable; this test needs a real container runtime"
    exit 1
fi

# ---------------------------------------------------------------- 1. the image exists
if docker image inspect "$IMAGE" >/dev/null 2>&1; then
    pass "image $IMAGE is present"
else
    log "image $IMAGE absent — building it"
    if compose build core >>"$REPORT" 2>&1; then
        pass "image $IMAGE built from backend/Dockerfile"
    else
        fail "the image did not build; see $REPORT"
        dump_logs
        exit 1
    fi
fi

# ---------------------------------------------------------------- 2. bring it up
log "starting: $SERVICES"
# shellcheck disable=SC2086 - SERVICES is a deliberate word list
if compose up -d --no-build --wait $SERVICES >>"$REPORT" 2>&1; then
    pass "compose brought up $SERVICES and reported them healthy"
else
    fail "compose up did not reach a healthy state within its own timeout"
    dump_logs
fi

if wait_for_endpoint; then
    pass "core answers /healthz from inside the container"
else
    fail "core never answered /healthz within ${WAIT_SECONDS}s"
    dump_logs
    log "report: $REPORT"
    exit 1
fi

# The Dockerfile's HEALTHCHECK has never been exercised by anything before this.
status=$(health_status)
if [ "$status" = "healthy" ]; then
    pass "docker reports core healthy — the image HEALTHCHECK actually answers"
else
    fail "docker reports core health as '${status:-unknown}', not 'healthy'"
fi

# ---------------------------------------------------------------- 3. posture, from inside
log "--- runtime smoke check (inside the container) ---"
if compose exec -T -e NEXUS_SMOKE_RUNTIME_CHECKS=1 core python - < "$CHECKER" 2>&1 | tee -a "$REPORT"; then
    pass "every in-container posture and runtime-image check passed"
else
    fail "the in-container smoke check reported failures (see above)"
fi

# ---------------------------------------------------------------- 4. durability
# The point of this section: defect 31 would have made the audit log ephemeral while every health
# check still reported success. Two distinct things have to survive, and they are proved separately:
#
#   a restart   — the process dies and comes back in the same container. Proves the chain resumes
#                 from the stored head instead of restarting at seq 0.
#   a recreate  — the container is destroyed and a new one is made from the image. Proves the data
#                 is actually on the `core-data` named volume and not in the container's writable
#                 layer, and that uid 1001 can still write it in a fresh container.
#
# A restart alone cannot tell those apart: the writable layer survives a restart.

M_ROWS=""; M_API=""; M_INTACT=""
measure_audit() {
    M_API=$(read_api /v1/audit/verify records 2>/dev/null || echo "ERR")
    M_ROWS=$(count_rows 2>/dev/null || echo "ERR")
    M_INTACT=$(read_api /v1/audit/verify intact 2>/dev/null || echo "ERR")
}

# assert_durability <label> <rows_before> <api_before>
assert_durability() {
    label=$1; rows_before=$2; api_before=$3
    log "after $label: records=$M_API, audit_log rows=$M_ROWS, intact=$M_INTACT"

    if [ "$M_ROWS" = "ERR" ]; then
        fail "$label: could not read the durable audit table"
    elif [ "$M_ROWS" -ge "$rows_before" ] 2>/dev/null; then
        pass "$label: the audit table survived ($rows_before -> $M_ROWS rows on the volume)"
    else
        fail "$label: the audit table lost rows ($rows_before -> $M_ROWS)"
    fi

    if [ "$M_API" = "ERR" ]; then
        fail "$label: could not read the chain through the API"
    elif [ "$M_API" -gt "$api_before" ] 2>/dev/null; then
        pass "$label: the new process resumed the stored chain and appended to it ($api_before -> $M_API)"
    else
        fail "$label: the chain did not resume from disk ($api_before -> $M_API) — the log is ephemeral"
    fi

    if [ "$M_INTACT" = "True" ]; then
        pass "$label: the hash chain still verifies across the boundary"
    else
        fail "$label: the hash chain does not verify (intact=$M_INTACT)"
    fi
}

measure_audit
rows0=$M_ROWS; api0=$M_API
log "before: /v1/audit/verify records=$api0, audit_log rows=$rows0, intact=$M_INTACT"
if [ "$rows0" = "ERR" ] || [ "$api0" = "ERR" ]; then
    fail "could not read the audit record count before the durability checks"
else
    # --- 4a. restart in place
    if compose restart core >>"$REPORT" 2>&1 && wait_for_endpoint; then
        pass "core came back after a restart"
        measure_audit
        assert_durability "a restart" "$rows0" "$api0"
        rows1=$M_ROWS; api1=$M_API
    else
        fail "core did not come back after a restart"
        dump_logs
        rows1=$rows0; api1=$api0
    fi

    # --- 4b. destroy the container, keep the volume
    if compose rm -sf core >>"$REPORT" 2>&1 \
        && compose up -d --no-build core >>"$REPORT" 2>&1 \
        && wait_for_endpoint; then
        pass "a brand new core container started from the image against the existing volume"
        measure_audit
        assert_durability "a container recreate" "$rows1" "$api1"

        # The volume inherited uid 1001 ownership from the image; prove it is still writable now,
        # in the new container, by the runtime user rather than by root.
        writable=$(in_core <<'PY' 2>/dev/null || echo "ERR"
import os, pathlib
d = pathlib.Path("/app/data")
probe = d / ".smoke-write-probe"
probe.write_text("ok")
probe.unlink()
print(f"uid={os.getuid()} writable={os.access(d, os.W_OK)}")
PY
)
        case "$writable" in
            *"uid=1001 writable=True"*) pass "the runtime user owns and can write /app/data ($writable)" ;;
            ERR) fail "could not test whether /app/data is writable by the runtime user" ;;
            *) fail "/app/data is not writable by the expected non-root user ($writable)" ;;
        esac
    else
        fail "core did not come back after a container recreate"
        dump_logs
    fi
fi

# ---------------------------------------------------------------- 5. teardown
if [ "$DESTROY_VOLUMES" = "1" ]; then
    compose down -v --remove-orphans >>"$REPORT" 2>&1 && pass "tore down project $PROJECT and its volumes"
else
    compose down --remove-orphans >>"$REPORT" 2>&1 && pass "tore down project $PROJECT (volumes kept)"
fi

log ""
if [ "$FAILED" -eq 0 ]; then
    log "SMOKE TEST PASSED — report: $REPORT"
else
    log "SMOKE TEST FAILED — report: $REPORT"
fi
exit "$FAILED"
