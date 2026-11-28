"""Runtime smoke check for a *running* NEXUS core process.

Run this against a live container, not against a test client:

    docker compose exec -T core python - < infra/smoke_check.py

It exists because everything verified before Phase 4 was verified against a build or a test
client. An image that builds and a module that imports say nothing about whether the process
serves a request, whether the non-root user can write its audit database, or whether the
posture the tests assert survives contact with a real deployment.

Two groups of checks:

* **API posture** — always run. The phase gate, live authority, alert channels and route surface
  as a *running* process reports them, plus two probes that a trading route is genuinely absent
  rather than merely undocumented.
* **Runtime image** — only when ``NEXUS_SMOKE_RUNTIME_CHECKS=1``, which the compose run sets.
  These assert properties of the image from the inside: no setuptools, no pip, a real IANA tz
  database, a non-root uid, a writable audit database. They are expected to FAIL in a development
  venv, and that is the negative control — a check that passes everywhere proves nothing.

Every check runs; nothing stops at the first failure, because a run costs minutes and one report
beats six. Exit status is non-zero if any check failed.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

BASE_URL = os.environ.get("NEXUS_SMOKE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
# The URL comes from the environment, so it is constrained rather than trusted: urllib will open
# file: and ftp: as readily as http:, and this script runs in CI where the workflow supplies it.
if not BASE_URL.startswith(("http://", "https://")):
    raise SystemExit(f"NEXUS_SMOKE_BASE_URL must be http(s); got {BASE_URL!r}")
RUNTIME_CHECKS = os.environ.get("NEXUS_SMOKE_RUNTIME_CHECKS", "") == "1"
EXPECTED_PHASE = "3-market-data"
EXPECTED_UID = 1001

# Paths that must not exist while the system cannot trade. Checked as substrings, so a route
# added later under a new prefix is still caught.
FORBIDDEN_ROUTE_WORDS = ("order", "trade", "trading", "execute", "position", "withdraw", "transfer")
# The paper trading platform (Stage 11, D-059) is the one namespace exempt from the lexical ban,
# because a simulated blotter genuinely is a list of orders — of orders that cannot be sent. Naming
# its routes /v1/paper/blotter and /v1/paper/holdings would have satisfied the substring check while
# proving nothing, so the exemption is paired with the semantic checks in
# `check_the_paper_namespace_is_inert`: those ask the running process whether it can place an order,
# and fail if it says anything other than no.
PAPER_NAMESPACE = "/v1/paper"
# The only mutations this build is allowed to expose: the emergency halt and its release, plus
# starting, stopping and resetting the simulation. None of the three can transmit anything.
ALLOWED_POST_PATHS = {
    "/v1/halt",
    "/v1/halt/release",
    f"{PAPER_NAMESPACE}/start",
    f"{PAPER_NAMESPACE}/stop",
    f"{PAPER_NAMESPACE}/reset",
}

_results: list[tuple[bool, str, str]] = []


def record(passed: bool, name: str, detail: str = "") -> None:
    _results.append((passed, name, detail))
    print(f"{'PASS' if passed else 'FAIL'} {name}" + (f": {detail}" if detail and not passed else ""))


def check(name: str, condition: bool, detail: str = "") -> bool:
    record(bool(condition), name, detail)
    return bool(condition)


def get(path: str) -> tuple[int, Any]:
    """Return (status, body). Body is parsed JSON when possible, else the raw text."""
    request = urllib.request.Request(f"{BASE_URL}{path}", method="GET")  # noqa: S310 - http(s) enforced
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - http(s) enforced
            raw = response.read().decode("utf-8", "replace")
            status = response.status
    except urllib.error.HTTPError as exc:  # a 4xx/5xx is a result, not an exception
        raw = exc.read().decode("utf-8", "replace")
        status = exc.code
    except OSError as exc:
        # Nothing listening, DNS failure, connection reset. A crash here would be the least
        # useful possible report: the whole point is to say "the process is not serving".
        return 0, f"unreachable: {type(exc).__name__}: {exc}"
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, raw


def probe(path: str, method: str = "GET") -> int:
    """Status code for a request that should not succeed. Any 2xx is a failure."""
    request = urllib.request.Request(f"{BASE_URL}{path}", method=method)  # noqa: S310 - http(s) enforced
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - http(s) enforced
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except OSError as exc:
        record(False, f"probe {path}", f"could not reach the endpoint at all: {exc}")
        return -1


# --------------------------------------------------------------------- API posture


def check_api() -> None:
    status, body = get("/healthz")
    if not check("healthz responds 200", status == 200, f"got {status}: {str(body)[:160]}"):
        return  # nothing else can be trusted if the process is not serving
    if isinstance(body, dict):
        check("healthz reports ok", body.get("status") == "ok", str(body)[:160])
        check(
            "healthz reports the expected phase",
            body.get("phase") == EXPECTED_PHASE,
            f"got {body.get('phase')!r}, expected {EXPECTED_PHASE!r}",
        )

    status, body = get("/readyz")
    check("readyz responds 200", status == 200, f"got {status}: {str(body)[:200]}")
    if isinstance(body, dict):
        check(
            "readyz reports ready — the audit store is writable by this user",
            body.get("ready") is True,
            f"problems={body.get('problems')}",
        )
        check("readyz reports no problems", body.get("problems") == [], str(body.get("problems")))

    status, body = get("/v1/status")
    if not check("status responds 200", status == 200, f"got {status}"):
        return
    if not isinstance(body, dict):
        record(False, "status body is an object", str(body)[:160])
        return

    gate = body.get("phase_gate") or {}
    for key in ("live_trading", "venue_adapters", "real_money_orders_possible", "order_capability"):
        check(f"phase_gate.{key} is false", gate.get(key) is False, f"got {gate.get(key)!r}")

    authority = body.get("live_authority") or {}
    check("live_authority.granted is false", authority.get("granted") is False, str(authority)[:200])
    check(
        "live_authority.status is DENIED",
        authority.get("status") == "DENIED",
        str(authority.get("status")),
    )
    check(
        "live_authority names its blocking reasons",
        bool(authority.get("blocking_reasons")),
        "a DENIED authority with no reasons cannot be diagnosed",
    )

    check(
        "no venue trading adapters exist",
        body.get("venue_adapters") == [],
        str(body.get("venue_adapters")),
    )

    sources = body.get("market_data_sources") or {}
    check(
        "market_data_sources.authenticated is false",
        sources.get("authenticated") is False,
        str(sources)[:160],
    )
    check("market_data_sources.read_only is true", sources.get("read_only") is True, str(sources)[:160])
    check(
        "market_data_sources.order_capable is false",
        sources.get("order_capable") is False,
        str(sources)[:160],
    )
    check("market_data_sources.cost_usd is 0", sources.get("cost_usd") == 0, str(sources.get("cost_usd")))
    check(
        "market data sources are the free public feeds (D-019/D-026)",
        bool(sources.get("sources")),
        "no sources enabled",
    )

    alerts = body.get("alert_channels") or {}
    check("SMS stays blocked (D-020)", alerts.get("sms") is False, str(alerts.get("sms")))
    check("WhatsApp stays blocked (D-020)", alerts.get("whatsapp") is False, str(alerts.get("whatsapp")))

    check("risk limits are still labelled provisional (O-002)", body.get("risk_limits_provisional") is True)
    check("the zero-cost constraint is stated", "D-019" in str(body.get("cost_constraint", "")))

    status, spec = get("/openapi.json")
    if check("openapi is served", status == 200 and isinstance(spec, dict), f"got {status}"):
        paths = spec.get("paths") or {}
        check("openapi declares routes", bool(paths), "no paths at all — the check went vacuous")
        forbidden = sorted(
            p
            for p in paths
            if not p.startswith(PAPER_NAMESPACE)
            and any(word in p.lower() for word in FORBIDDEN_ROUTE_WORDS)
        )
        check("no route can place, amend or cancel an order", not forbidden, f"found {forbidden}")
        posts = sorted(p for p, ops in paths.items() if isinstance(ops, dict) and "post" in ops)
        unexpected = sorted(set(posts) - ALLOWED_POST_PATHS)
        # The name is derived from the allow-list rather than written out, because a report line
        # that names two paths while five are permitted is a false statement about the system, and
        # it would keep passing while saying it. This report is published as a CI annotation and
        # read by a person deciding whether the build can trade; it has to be true when it is green.
        check(
            "the only mutations are the allowed POST paths: "
            + ", ".join(sorted(ALLOWED_POST_PATHS)),
            not unexpected,
            f"unexpected POST routes: {unexpected}",
        )

    check_the_paper_namespace_is_inert()


def check_the_paper_namespace_is_inert() -> None:
    """Ask the running process whether the paper platform can trade, and believe only "no".

    The lexical route ban above cannot tell a simulated blotter from a real one, and the exemption
    for ``/v1/paper`` would be a hole in the gate on its own. So the exemption is earned here, by
    questioning the process that is actually serving: its own description of its capability, and the
    labelling on every body it returns. A build that could send an order would have to lie in three
    separate responses to pass, and the phase-gate checks above would have to lie with it.
    """
    status, body = get(f"{PAPER_NAMESPACE}")
    if status == 404:
        # The platform can be switched off entirely (NEXUS_PAPER_ENABLED=false), in which case the
        # routes are still served and say so; a genuine 404 means a build without Stage 11 at all,
        # and there is nothing here to check.
        record(True, "paper namespace absent — nothing to check", "")
        return
    if not check("the paper namespace describes itself", status == 200, f"got {status}"):
        return
    if not isinstance(body, dict):
        check("the paper namespace describes itself", False, f"body was {type(body).__name__}")
        return
    check("paper says it cannot place live orders", body.get("can_place_live_orders") is False, str(body.get("can_place_live_orders")))
    check("paper says it is simulated", body.get("simulated") is True, str(body.get("simulated")))
    check("paper says it is not a venue adapter", body.get("is_venue_adapter") is False, str(body.get("is_venue_adapter")))
    check("paper holds no venue adapter", body.get("adapter_count") == 0, str(body.get("adapter_count")))
    check("paper needs no network access", body.get("network_access") is False, str(body.get("network_access")))
    check("paper needs no credential", body.get("credentials_required") is False, str(body.get("credentials_required")))
    engine = body.get("engine")
    check(
        "the paper engine reports PAPER as its environment",
        isinstance(engine, dict) and engine.get("environment") == "PAPER",
        str(engine.get("environment") if isinstance(engine, dict) else engine),
    )

    for path in ("account", "orders", "fills", "positions", "analysis"):
        status, payload = get(f"{PAPER_NAMESPACE}/{path}")
        labelled = (
            status == 200
            and isinstance(payload, dict)
            and payload.get("simulated") is True
            and payload.get("environment") == "PAPER"
        )
        check(
            f"every /v1/paper/{path} body is labelled simulated",
            labelled,
            f"status {status}, simulated={payload.get('simulated') if isinstance(payload, dict) else None}",
        )

    status, payload = get("/v1/status")
    if status == 200 and isinstance(payload, dict):
        paper = payload.get("paper")
        check(
            "status publishes paper beside live_authority, and they disagree in the right way",
            isinstance(paper, dict)
            and paper.get("can_place_live_orders") is False
            and isinstance(payload.get("live_authority"), dict)
            and payload["live_authority"].get("status") == "DENIED",
            f"paper={paper}",
        )


    # Two live probes. A route can be missing from openapi.json and still be served, so the
    # absence is tested by asking for it, not only by reading the spec.
    check(
        "an unknown instrument is refused with 404",
        probe("/v1/instruments/INS-DOES-NOT-EXIST/session") == 404,
        "a running process answered something other than 404",
    )
    # GET on the collection is a legitimate read — it serves the master. The write is what must
    # be refused, so it is a POST that has to come back 405.
    check(
        "the instrument master is readable",
        probe("/v1/instruments") == 200,
        "GET on the collection should serve the master",
    )
    check(
        "the instrument master cannot be written to",
        probe("/v1/instruments", "POST") == 405,
        "a POST was not refused with 405 — the master is writable from a running process",
    )

    status, body = get("/v1/audit/verify")
    if check("audit verify responds 200", status == 200, f"got {status}") and isinstance(body, dict):
        check("the audit hash chain is intact", body.get("intact") is True, str(body.get("breaks"))[:200])
        check(
            "the audit log has records — readiness wrote one",
            int(body.get("records") or 0) >= 1,
            f"records={body.get('records')}",
        )


# --------------------------------------------------------------------- runtime image


def check_runtime_image() -> None:
    """Properties of the image, asserted from inside a running container."""
    for module in ("setuptools", "pip"):
        try:
            __import__(module)
            record(False, f"{module} is absent from the runtime image", f"{module} imported successfully")
        except ImportError:
            record(True, f"{module} is absent from the runtime image")

    try:
        from zoneinfo import ZoneInfo

        zone = ZoneInfo("America/New_York")
        record(True, "the IANA tz database is installed", str(zone))
    except Exception as exc:  # noqa: BLE001 - any failure here means the entrypoint would die
        record(False, "the IANA tz database is installed", f"{type(exc).__name__}: {exc}")

    uid = os.getuid() if hasattr(os, "getuid") else -1
    check("the process is not root", uid != 0, f"uid={uid}")
    check(f"the process runs as the nexus user (uid {EXPECTED_UID})", uid == EXPECTED_UID, f"uid={uid}")

    data_dir = Path(os.environ.get("NEXUS_DATA_DIR", "/app/data"))
    check("the data directory exists", data_dir.is_dir(), str(data_dir))
    check("the data directory is writable by this user", os.access(data_dir, os.W_OK), str(data_dir))
    databases = sorted(data_dir.glob("*.db"))
    check("the audit database was created", bool(databases), f"nothing matching *.db in {data_dir}")
    for path in databases:
        check(f"{path.name} is writable", os.access(path, os.W_OK), str(path))

    # The Dockerfile asserts this at build time; asserting it again at runtime catches a volume
    # mount or a later layer reintroducing what the build removed.
    declared = []
    for root in ("/usr/local/lib", "/opt/venv/lib"):
        base = Path(root)
        if not base.is_dir():
            continue
        for manifest in list(base.rglob("*.cdx.json")) + list(base.rglob("*.spdx.json")):
            try:
                if "setuptools" in manifest.read_text(errors="ignore"):
                    declared.append(str(manifest))
            except OSError:
                continue
    check("no manifest in the image declares setuptools", not declared, str(declared[:3]))


def main() -> int:
    print(f"NEXUS runtime smoke check against {BASE_URL}")
    print(f"runtime image checks: {'ON' if RUNTIME_CHECKS else 'off'}")
    check_api()
    if RUNTIME_CHECKS:
        check_runtime_image()
    failed = [name for passed, name, _ in _results if not passed]
    print(f"\n{len(_results) - len(failed)}/{len(_results)} checks passed")
    if failed:
        print("FAILED CHECKS:")
        for passed, name, detail in _results:
            if not passed:
                print(f"  - {name}" + (f" ({detail})" if detail else ""))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
