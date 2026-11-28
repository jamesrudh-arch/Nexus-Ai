# NEXUS — Phase 4: Venue Certification (demo/paper only)

**Status:** PRE-FLIGHT. No venue has been contacted, no account connected, no credential requested.
**Date:** 2026-11-25 · **Branch:** `arena/06913352-nexus-ai` · **Cost:** $0 (D-019)

Phase 3 was accepted on 2026-11-25 (D-027). Phase 4 is authorized **VM-first** (D-028): before any
venue is certified, the stack must be brought up for real, because nothing in Phase 2 or Phase 3
ever started a container. This document records that work. The accepted Phase 3 record
(`docs/05-phase3-market-data.md`) is frozen and is not amended here.

---

## 1. Authority and scope

| Ref | Decision | Date |
|-----|----------|------|
| **D-027** | **Phase 3 ACCEPTED.** Market data + instrument master; exit gate PASSED for offline-verifiable scope. O-009 (live endpoints) and O-010 (Dukascopy layout) remain **open** and tracked, both requiring network egress this sandbox does not have | 2026-11-25 |
| **D-028** | **Phase 4 authorized, VM-first.** The first task is a real `docker compose up` on the Oracle Always Free VM approved in D-021, closing the "no container has ever started" limitation and testing the runtime image's assumptions for real. Venue certification follows. **Demo/paper accounts only** — no live trading, no real-money keys, no withdrawal-enabled credential | 2026-11-25 |
| **D-029** | **First venues: Bybit and OKX, certified in parallel**, matching the Phase 3 build order (D-026). Each is certified independently (D-007); neither inherits the other's status. Both are ADOPT for Nigeria per `docs/02` §3 (OKX removed from the restricted list 8 Jul 2026; Bybit partial) | 2026-11-25 |

Unchanged and still binding: D-004 (autonomy requires a separate live-authority approval),
D-013 (legal review before live), D-019 (zero cost), D-021 (the VM must be re-approved before any
live phase).

**Out of scope for Phase 4:** live trading, real-money orders, withdrawal permissions, any paid
service, any venue not named in D-007, and any change to a model or strategy without owner
approval (D-012).

---

## 2. Pre-flight defects — found before any venue work began

Found while preparing the bring-up — 31 to 35 by reading what the deployment actually configures
against what the code actually honours, 36 and 37 by *starting the stack for the first time*, and 38
and 39 by *contacting the venues for the first time*. None of 31 to 37 is a venue defect; all would
have been discovered during the bring-up at the worst possible moment, one would have destroyed
evidence, and one made the deployment unstartable.

38 to 40 are a different kind: they are defects in **our** reading of a venue's published contract,
and they are the reason §4 item 6 existed. None could be found offline — 39 for a structural reason
recorded against it, and 40 only because a real file finally arrived to be parsed.

| # | Defect | Impact if unfixed | Fix |
|---|--------|-------------------|-----|
| 31 | **`_default_store` silently substituted an in-memory audit store** for any `NEXUS_DATABASE_URL` that was not `sqlite:///` — and `.env.example` advertised `postgresql+psycopg://...` as the compose variant, with a TimescaleDB service shipped to serve it | **The audit trail — the system's evidence record — would have been discarded on every restart**, while `/healthz` and `/readyz` both reported success. Reachable purely by following the documentation. For a system whose decisions must be auditable after the fact, this is the worst failure mode available: not a crash, but plausible-looking compliance with nothing behind it | Refuse startup with `CONFIG_INVALID`, naming the scheme that works and the explicit way to choose memory (`NEXUS_AUDIT_BACKEND=memory`). This is the codebase's own rule — `NatsEventBus` documents "events are never silently discarded"; the audit store is now held to it. The refusal carries only the URL *scheme* in its context, because it is persisted and surfaced in the UI and a database URL can contain a password |
| 32 | **The test suite wrote a real audit database into `backend/data/`** | `Settings.database_url` is relative, so every test that built the app with defaults appended to one shared SQLite file — shared between tests *and* between runs, and invisible to git because the path is ignored. An append-only hash-chained log shared across runs is not isolation: a verification that passes on a dirty tree can fail on a clean one | An autouse fixture runs each test in its own directory. Guarded by executing a real pytest subprocess from the repository cwd and asserting no `backend/data` appears — not by checking the fixture exists, because a fixture can exist and not be autouse, and only the second case protects anything |
| 33 | **`.env.example` never documented `NEXUS_SECRET_OWNER_TOTP_SECRET`** | The step-up factor for `POST /v1/halt/release`. An operator following the documentation would bring up a system whose emergency halt could be **engaged but never released**, and nothing would explain why until the first incident needed it | Documented, with what it gates. Guarded in *both* directions by a new test class: every variable the deployment sets or the docs recommend must be read by something (a `Settings` field, an `os.environ` read, a Caddyfile/compose template, or the secrets naming convention), and every `SecretRef` the code declares must appear in `.env.example` |
| 34 | **`core` waits for `db` to be healthy but never connects to it** | TimescaleDB costs ~1.5 GB of the 12 GB Always Free budget and adds startup latency for a database nothing reads, on the most memory-constrained host in the plan | Recorded as a KNOWN GAP in the compose header rather than papered over. Wiring `core` to Postgres is Phase 4 work; until then a memory-constrained host should bring up `core` alone. `backend/migrations/0001_core.sql` is complete Postgres DDL, including append-only triggers, and is what that wiring will apply |
| 35 | **A negative-control loop silently failed to restore the files it mutated** | Six deliberate mutations — including re-introducing defect 31 — were left in the working tree, and the next commit would have shipped every one of them. Two causes: the loop backed up each file *after* mutating it, and `git -C <repo> checkout -- <path>` was given paths relative to a different cwd, so git errored and the fallback restored the mutated copy | Repaired by hand and verified line by line. The lesson is recorded rather than the history rewritten: a control whose restoration is not verified is worse than no control, because it leaves the tree in a state that looks intentional. Restore by absolute path, and diff against HEAD before committing |
| 36 | **The compose stack was unstartable: the `nats` healthcheck probed a port the service never opened.** `nats:2-alpine` ships `CMD nats-server --config /etc/nats/nats-server.conf`, and that config file is what sets `monitor_port: 8222`. compose overrode `command:` with `--jetstream --store_dir /data`, discarding the `--config` flag, so nothing listened on 8222 | The healthcheck could only ever get a connection refused, so the container was **permanently unhealthy**, and `core` — which waits on `nats: condition: service_healthy` — never started. `docker compose up` of this stack has never worked, in any environment, and nothing in the repository could say so: the config parses, the image builds, and both of those were all CI had ever checked | `command: ["--jetstream", "--store_dir", "/data", "-m", "8222"]`, with the reasoning in a comment. Restoring `--config` instead would be worse: that upstream file also opens cluster route port 6222 with a hardcoded credential (`ruser`/`T0pS3cr3t`), so enabling only the monitoring port is the tighter fix. Now guarded by a generalised test — any service that overrides `command:` and has an HTTP healthcheck must re-declare every port that healthcheck probes |
| 37 | **`NatsEventBus` called `nats.connect()` synchronously, but it is a coroutine function.** Measured, not inferred: `asyncio.iscoroutinefunction(nats.connect)` is `True`, and calling it returns a `coroutine` object with no `jetstream` attribute | Every first publish raised `EventPublishError`, so **no event could ever have reached NATS**. The class documented itself as fail-closed and was in fact fail-always. It survived because nothing publishes in Phase 3 and both lines carried `# pragma: no cover`, so no test ever executed them — the pragma hid the defect from the only thing that could have found it | The bus now owns a dedicated event loop on a daemon thread and drives `connect`, `publish` and `close` through `run_coroutine_threadsafe`, with a bound on each so a stalled socket produces a refusal rather than a hung audit path. Tested against an injected fake async client, which covers the part that was wrong without needing a NATS server; the coroutine-function assumption itself is pinned against the real library, which is why `nats-py` joined the dev extra. **Reaching a real server is still unverified** — that is B-5 |
| 38 | **The Binance Vision dump URLs omitted the daily-or-monthly frequency path segment.** `kline_url` built `data/{market}/klines/{symbol}/{interval}/{name}.zip`; the published layout is `data/{market}/{frequency}/{data_type}/{symbol}/{interval}/{name}.zip`. `agg_trades_url` had the same omission | Every bulk download 404s. Confirmed live: `data/spot/klines/BTCUSDT/1m/BTCUSDT-1m-2026-11-18.zip` returned 404 from a CI runner, while the same host answered normally for the corrected path | Both builders now include the segment, and `periodicity` is validated in `agg_trades_url` rather than defaulted — it selects a path segment as well as a filename stamp, so an unrecognised value would have silently requested a daily file under a monthly name. Found by live verification, not by reading |
| 39 | **The Dukascopy bi5 URL contained an invented `BID`/`ASK` path segment.** `hour_url` built `{PAIR}/{YYYY}/{MM-1}/{DD}/{SIDE}/{HH}h_ticks.bi5`. The feed serves **one file per instrument-hour holding both sides** — every 20-byte record already carries ask points, bid points and a volume for each — so the path is `{PAIR}/{YYYY}/{MM-1}/{DD}/{HH}h_ticks.bi5` and nothing else. Confirmed live: `EURUSD/2026-10-19/BID/12h_ticks.bi5` returned 404 | Every Dukascopy hour 404s, so **no FX tick could ever have been downloaded** and `LAYOUT_VERIFIED` could never have become True. It survived 151 passing adapter tests for a structural reason worth stating plainly: those tests registered their expected responses in the recording transport under the key `hour_url(...)`, the very function under test. Code and expectation came from one source, so they always agreed, and no number of such tests could detect a wrong URL | The side segment is gone from `hour_url`, which no longer takes `side` at all; `side` is a parse-time choice and `parse_bi5` now refuses an unknown one instead of letting the two-way branch default it to ASK. The fixtures were rewritten to key off an independently transcribed `expected_bi5_url` / `expected_kline_url`, and a new `TestUrlShapesMatchThePublishedContract` pins each builder's entire output against a literal from the venue's documentation. Verified by control: reintroducing the segment now fails **five** tests including four that were previously blind to it |
| 40 | **Binance Vision publishes microsecond timestamps for spot dumps from 2025-01-01, and the parser assumed milliseconds.** `parse_kline_csv` passed `assume_ms=True`, so every value was divided by 1000 regardless of magnitude | The first real dump this repository ever downloaded — a genuine 71,720-byte ZIP, proof the defect-38 URL fix worked — failed to parse with `ValueError: year 58852 is out of range`. The dangerous alternative was not the exception: had the value landed inside `datetime`'s range it would have produced a bar dated tens of thousands of years out, entered the archive silently, and poisoned every aggregate, rollup and retention calculation built on it | `to_utc` now scales a numeric epoch by the unit its **magnitude** implies, via a new `epoch_unit`. This is a measurement rather than a preference because the four windows are *disjoint* across 2010–2100 — seconds, milliseconds, microseconds and nanoseconds are three orders of magnitude apart, so there is never a tie to break, and a test asserts the disjointness rather than trusting it. A value that fits no window is refused as `CONFIG_INVALID` instead of becoming a date. The `assume_ms` parameter was **removed** rather than left inert: a flag that no longer governs is worse than no flag, because a caller passing it believes it has an effect. `DumpParseResult` now reports `timestamp_units`, so a dump that mixes units across the 2025-01-01 boundary is visible instead of absorbed. All four units verified to denote the same instant |

Defect 31 is the significant one. It is the same shape as the CI-era defects in `docs/05` §4 — a
configuration key or code path that is silently inert while looking correct — but the payload is
worse: those lost a scan result or a build diagnosis, and this one loses the evidence trail that
every other guarantee depends on. It was found by asking a question nobody had asked: *which of the
variables this deployment sets does the code actually read?*

Defect 36 is the one that justifies the whole exercise. It was not subtle, it was not in an obscure
corner, and it was not findable by any check the repository had: `docker compose config` parses the
file happily, the image builds, the tests pass, and 884 green tests said nothing about it. One
`docker compose up` found it in about four minutes. That is the concrete cost of limitation 1 below,
and it is why the smoke test now runs on every push rather than being a script somebody remembers to
run before a release.

Defect 37 is the same shape one level down, and it is worth naming the mechanism: `# pragma: no
cover` on the two lines that talked to the network meant the only code path that could have revealed
the transport was broken was excluded from measurement. A pragma that suppresses coverage does not
make code correct; here it made a broken transport look deliberately untested rather than untested
by accident.

---

## 3. Bring-up plan

Sequenced so that each step produces evidence the next one depends on. Nothing here contacts a
venue.

| Step | What is verified | Where | Evidence produced |
|------|------------------|-------|-------------------|
| **B-1** | The stack starts and serves. `core` builds, starts, answers `/healthz` and `/readyz`, and reports the phase gate honestly from a *running* process | GitHub Actions (x86-64), then the Oracle VM (ARM64) | Container logs, endpoint responses, `docker compose ps` health states |
| **B-2** | The runtime image's assumptions hold under execution: the pip removal did not break a runtime import, `tzdata` is present, the non-root user can write its audit database, the healthcheck actually answers | same | The same assertions the Dockerfile makes at build time, re-checked in a running container |
| **B-3** | SQLite audit store durability across a restart **and across a container recreate**: records survive, the hash chain resumes from the stored head and still verifies | GitHub Actions, then the Oracle VM | `/v1/audit/verify` plus a direct row count from the volume, before and after each |
| **B-4** | ARM64-native execution (not QEMU-emulated), and the memory budget on 2 OCPU / 12 GB | Oracle VM only — CI cannot do this | `docker stats` under load, `uname -m` from inside the container |
| **B-5** | Postgres/TimescaleDB actually used by `core`, closing defect 34 and Phase 3 limitation 5 | Oracle VM | Migration applied, records written to and read from Postgres, `db` no longer idle |
| **B-6** | Only then: Bybit and OKX **demo/paper** connectivity, per D-029 | Oracle VM (has egress) | Per-venue certification records |

B-1 and B-2 can run in CI, on GitHub-hosted runners, for $0 — which is worth doing before the VM,
because a failure found there costs minutes and a failure found on the VM costs a rebuild. B-4 and
B-5 cannot be done anywhere but the VM. B-3 turned out to belong in the first group as well: a
`docker compose rm -sf core` followed by `up -d core` destroys the container and keeps the
`core-data` named volume, which is available on a hosted runner and is a *stronger* test than the
restart alone.

### 3.1 How B-1/B-2/B-3 are wired

Three pieces, all offline-verifiable except the container run itself.

**`infra/smoke_check.py`** — 34 assertions, standard library only, because it has to run inside the
runtime image where the only guaranteed interpreter is the application's own. It is piped in with
`docker compose exec -T core python - < infra/smoke_check.py` rather than copied, so it cannot be
stale relative to the checkout. It reads the API from inside the container (`/healthz`, `/readyz`,
`/v1/status`, `/openapi.json`, `/v1/instruments`, `/v1/audit/verify`) and asserts the *posture*: the
phase gate is closed, live authority is `DENIED` with reasons, `venue_adapters` is empty, the market
data sources are unauthenticated and read-only at zero cost, SMS and WhatsApp stay blocked (D-020),
no route can place or cancel an order, the only mutations are halt and halt/release, and the
instrument master refuses a POST with 405.

The route assertions read `/openapi.json` rather than the router object, so they describe what a
client can actually reach. Forbidden routes are matched as substrings — `order`, `trade`, `execute`,
`position`, `withdraw`, `transfer` — so a capability added later under a new prefix is still caught.

Image-only properties (pip and setuptools absent, the IANA tz database installed, uid 1001, `/app/data`
writable, no SBOM in the image declaring setuptools) run only when `NEXUS_SMOKE_RUNTIME_CHECKS=1`.
That gate exists so the checks have a **negative control**: in a development virtualenv they must
fail, because pip and setuptools are both present there. A check that passes in every environment
is not checking anything.

**`infra/smoke-test.sh`** — the orchestration. It brings up `db nats core` under a *separate compose
project name* (`nexus-smoke`) so it cannot touch a real deployment's containers or volumes, which
matters on the VM where a live stack may already be running; tears down what it created; and runs
every check rather than stopping at the first failure, because one complete report is worth more
than six CI runs that each die on the first problem. Exit status is non-zero if any check failed.

It asserts the image's own `HEALTHCHECK` answers (docker reports `core` healthy — nothing had ever
exercised that), runs the checker inside the container with the runtime checks on, then proves
durability twice over: a restart, and a container recreate against the surviving volume. It also
confirms the runtime user — not root — can write `/app/data` in the *new* container, which is where
a volume that inherited the wrong ownership would show up.

No step whose exit status matters is piped. `cmd | tail -5; echo "exit=$?"` reports `tail`'s status,
not `cmd`'s, and that silently turned a crash into a green result while this was being written.

**The `smoke` CI job** — builds the amd64 image with `load: true` under the exact tag
`docker-compose.yml` names, runs the script, and republishes `smoke-report.txt` as **one** check
annotation. The annotation is not a convenience: this environment cannot read job logs, because
GitHub serves them from a host outside the egress allowlist, so without it a failure here is a red
X with no content. One annotation rather than one per failure, because Actions caps annotations at
10 per level per step and a long report would silently lose everything past the tenth.

The job deliberately has no `needs:`. Lint and runtime are independent signals about different
things, and chaining them means the runtime verdict arrives only on pushes that are already
lint-clean.

**11 new tests in `test_repo_hygiene.py`** hold all of the above in place, including running the
checker against the real application served by uvicorn on an ephemeral port. That last one is the
important part: it executes the checker end to end, over a real socket, with no docker involved, so
a bug in the *checker* is caught offline instead of surfacing as a confusing red container job. Two
such bugs were found while writing it and are now regression-tested — it crashed with an unhandled
`URLError` traceback when nothing was listening (the least useful possible output from a bring-up
check, since "the process is not there" is the one thing the operator already suspects), and one
route probe used GET where it meant POST, so it failed against a correct application. All six
negative controls over these tests fired, and each mutated file was verified restored individually
rather than inferred from the controls passing.

### 3.2 Result — B-1, B-2 and B-3 are closed on x86-64

Two CI runs, and the first one failed in the most useful way available.

**Run 1 — `2ca6ca5`, push run `45716117878`, job `139562484012`: FAILED.** The image built and
loaded, compose pulled TimescaleDB and NATS, and `db` reached healthy. Then:
`dependency failed to start: container nexus-smoke-nats-1 is unhealthy`. That is defect 36, and it
is the first time this project has ever observed a container start. The failure was diagnosed
entirely from the republished annotation, without log access.

**Run 2 — `91393af`, push run `45718271682` and pull_request run `45718281143`: PASSED, 59 checks,
all five jobs green on both events.** What is now measured from inside a running container rather
than inferred from a build:

- `compose up` brings up `db`, `nats` and `core` and all three report healthy — **the stack starts**;
- `docker` itself reports `core` healthy, so **the image's own `HEALTHCHECK` answers** (curl reaches
  `/healthz` on 127.0.0.1:8000 from inside);
- all 34 posture checks pass against a real process: phase gate closed, live authority `DENIED` with
  seven blocking reasons, no venue adapters, unauthenticated read-only market data at zero cost, SMS
  and WhatsApp blocked, no order/trade/execute/position/withdraw/transfer route, halt and
  halt/release as the only mutations, instrument master refusing POST with 405;
- **`setuptools` and `pip` are both absent from the runtime image**, and no manifest in the image
  declares setuptools. This closes limitation 2: the pip removal is now *observed in the image*, not
  reasoned from a dev venv whose package set differs (the reasoning error behind `docs/05` defects
  25 and 30);
- the IANA tz database is installed, so the import-time `ZoneInfo("America/New_York")` that defect 26
  flagged is satisfied in the image and not merely in the base;
- the process is not root and runs as `nexus`, uid 1001; `/app/data` exists, is writable by that
  user, and holds a writable `nexus.db` on the named volume;
- **durability, twice**: across a restart (2 → 3 rows) and across a container recreate against the
  surviving volume (3 → 4 rows). In both cases the new process read the stored chain head and
  appended to it rather than restarting at seq 0, and `/v1/audit/verify` still reports the chain
  intact. A recreate is what separates "on the volume" from "in the writable layer"; a restart alone
  cannot tell those apart, so both were run.

B-4 (ARM64-native execution and the memory budget) is unaffected by this and remains VM-only: CI
builds arm64 under QEMU and the smoke job runs amd64. Everything above is x86-64 evidence.

**O-009 and O-010 can be closed from CI, not from this sandbox.** GitHub-hosted runners have
internet egress, which the sandbox does not: a scheduled or on-demand workflow can contact the
public Bybit and OKX endpoints and fetch a real Dukascopy bi5 file, then compare both against the
synthetic fixtures the adapters were written from. That is the plan for closing the two outstanding
Phase 3 exit-gate items without waiting for the VM, and it needs no API key (D-026: public
endpoints only).

---

## 4. Limitations — what is NOT verified

Per Appendix C. Items 1 and 2 were closed by the first container run (§3.2) and are kept here,
marked, so the cross-references elsewhere in this document stay valid. Items 3 to 7 are open.

1. **CLOSED for x86-64 — `core` now runs in a container and serves.** The numbering is kept so the
   cross-references above stay valid. As of `91393af` (runs `45718271682` / `45718281143`) the stack
   comes up, the image's own `HEALTHCHECK` answers, and 59 checks pass against a real process — see
   §3.2. What remains open is narrower and lives in item 4: all of this is amd64 evidence, and the
   deployment host (D-021) is ARM64, where the image has only ever been cross-compiled under QEMU.
2. **CLOSED — the pip removal is now observed in the image, not reasoned about.** The reasoning that
   closed O-011 came from grepping the **dev venv**, whose package set differs from the image's: the
   same mistake as `docs/05` defect 30, which cost a red build. B-2 removed the inference. From
   inside the running container, both interpreters fail to import `pip` and `setuptools`, no
   manifest in the image declares setuptools, the application serves every route, and the audit
   store writes. Nothing that was installed imports pip at runtime, which was the open question.
3. **PostgreSQL/TimescaleDB is still untested at runtime**, and is now known to be *unused* by
   `core` (defect 34). Only SQLite has ever been exercised.
4. **The ARM64 build is QEMU-emulated in CI.** It proves cross-compilation, not native execution or
   performance. B-4 is the first ARM64-native evidence, and D-021's host is ARM64.
5. **The Caddyfile remains completely unexercised.** It has never been parsed by Caddy, in CI or
   anywhere else.
6. **PARTIALLY CLOSED — one venue has been contacted and answered; two were wrong and are fixed but
   not yet re-verified; one cannot be verified from a hosted runner at all.** The first live run
   (`45724918466`, 2026-11-25) contacted all four sources for real and returned 5 passed / 10
   failed:
   * **OKX — verified live, 5 of 5.** Instrument info, quotes, trades, candles and order book all
     normalised from real responses: `BTC-USDT-SWAP` contract size 0.01, tick size 0.1; bid
     60505.6 / ask 60505.7, spread 0.017 bps, uncrossed; 50 trades, which in that run happened to
     include both a `BUY` and a `SELL`, with prices inside the quoted band; 100 one-minute candles spanning 1.65 h, contiguous, each with
     `low <= open,close <= high`; a 40-level book, ordered and uncrossed, entitlement `LIVE`. Raw
     responses were captured. This is the first time any venue's real data has passed through this
     code.
   * **Binance Vision — URL verified live, then defect 40 found in parsing, fixed.** The second run
     (`45726585354`) downloaded a genuine **71,720-byte ZIP** from the corrected path, which proves
     defect 38 fixed. Parsing it then failed with `year 58852 is out of range`: spot dumps use
     **microsecond** timestamps from 2025-01-01 and the parser assumed milliseconds (defect 40). This
     is the single clearest justification for the whole exercise — the URL could only be proven by
     downloading, and the timestamp unit could only be proven by parsing what came back.
   * **Dukascopy — URL corrected, layout still unverified.** The second run reached the corrected
     path (no side segment), and got **HTTP 503 on all four
     attempts**, so `verify_layout` had still never run against a real file and `LAYOUT_VERIFIED`
     stayed False. **SUPERSEDED 2026-11-26 (Stage 7.2, lever L-A):** `verify_layout` has since passed
     against a real hour in **twelve** consecutive CI runs and the flag is now `True`, with records
     tagged `DUKASCOPY_BI5` — `docs/14` §1.4 F-1 and §2.1. EURUSD only: 12 of the 13 point divisors
     have still never met a real file. Dukascopy's datafeed is documented as aggressively rate-limited, using 503 as well
     as 429 as its throttle response, and some hosts of this kind also reject a non-browser
     `User-Agent`; this transport sends `NEXUS/0.1 (personal research; free public data)`. **Which of
     those it is has not been determined**, because determining it needs a host with egress and the
     ability to vary one thing at a time. It is recorded as an open question rather than guessed at.
     503 is classified `unavailable`, so the three checks skip rather than fail — correct, since
     nothing about our code is implicated yet.

     > **Correction, 2026-11-26 (`docs/14` §2.4).** Every bi5 path written in this document is
     > hyphenated — `EURUSD/2026-10-19/BID/12h_ticks.bi5`, and three others. The feed's real path is
     > **slash-separated with a 0-indexed month**, so those strings address nothing and a request
     > built from one 404s: hour `2026-10-19T12:00Z` is served at `EURUSD/2026/09/19/12h_ticks.bi5`, and the hour the
     > layout was verified against, `2026-11-24T12:00Z`, at `EURUSD/2026/10/24/12h_ticks.bi5`. Both strings here were
     > generated by `hour_url()` rather than retyped. The historical rows are left as written because
     > they record what was requested at the time; this note is what keeps a reader from copying
     > them. The code was never affected — `hour_url()` has always emitted the slash form, and the
     > live run evidence quotes it correctly.
   * **Bybit — not verifiable from a GitHub-hosted runner.** All five endpoints returned HTTP 403 at
     the edge. Bybit geo-blocks the jurisdictions hosted runners sit in and answers 403 from
     CloudFront on **public, unauthenticated** endpoints, so this is a property of where the check
     runs, not of the adapter. It is now classified `GEO-BLOCKED` rather than lumped in with
     timeouts, and reported separately so it stays visible; the workflow accepts a self-hosted runner
     label on dispatch. **Bybit therefore remains unverified**, and per D-007 venues are certified
     independently, so OKX's result says nothing about it. Note the tension worth recording: Bybit
     was chosen for Nigeria (D-024), where it is not geo-blocked, but CI runs in the US, where it
     is — so Bybit's verification has to happen on the deployment host (D-021), not in CI.
   * What the adapter tests still cannot do is detect a wrong URL on their own, for the structural
     reason in defect 39. That is now closed for Binance Vision and Dukascopy by independently
     transcribed fixture keys; Bybit and OKX fixtures already keyed off literals, which is why
     neither of them was the one that broke.
7. **No credential of any kind exists yet**, and none is requested by anything built so far. Phase
   4 will need demo/paper credentials, which go to the secrets provider and never into chat, the
   repository, the image, or the audit log.

---

## 5. Evidence

| Check | Result | Date | Environment |
|-------|--------|------|-------------|
| Full suite | **902 tests, 0 failures, 0 errors, 1 skipped** (71 hygiene, 66 API, 88 core guarantees) | 2026-11-25 | sandbox, local venv, Python 3.11 |
| Lint / format | `ruff check` clean, `ruff format --check` clean (69 files) | 2026-11-25 | same |
| Types | `mypy` strict — no issues in 49 source files | 2026-11-25 | same |
| Negative controls | **6 of 6 fired**: re-advertising the Postgres URL, un-documenting the TOTP secret, adding a variable nothing reads, changing the compose default to a refused scheme, reverting the refusal to a silent in-memory fallback, and making the cwd fixture non-autouse | 2026-11-25 | same |
| Control restoration | Failed silently on the first attempt (defect 35); repaired and verified line by line against HEAD before committing | 2026-11-25 | same |
| Repository state | No `backend/data`, no artifact, no credential-shaped file, no scan-suppression file | 2026-11-25 | same |
| CI on GitHub | **Green on both events** at `9522856`: `push` run `45709533997`, `pull_request` run `45709545037` — Backend ✓ · Compose ✓ · Secret scanning ✓ · Container image ✓ | 2026-11-25 | GitHub-hosted `ubuntu-latest`, x86-64 |
| First container start | **`docker compose up` ran for the first time** and found defect 36: TimescaleDB reached healthy, NATS never did (`dependency failed to start: container nexus-smoke-nats-1 is unhealthy`), `core` never started | 2026-11-25 | CI run `45716117878`, job `139562484012`, x86-64 |
| Failure was readable without log access | The smoke job republished its report as a check annotation, and the diagnosis above came entirely from that annotation — job logs remain unreachable from this environment, which is the O-011 constraint | 2026-11-25 | same |
| Checker against a real process | **34/34 checks passed** against the application served by uvicorn on a real socket (posture, phase gate, DENIED authority with reasons, no order route, halt-only mutations, master refuses POST with 405, hash chain intact) | 2026-11-25 | sandbox, no docker |
| Negative controls | **10 of 10 fired**: 6 over the smoke wiring (image not loaded, job gated behind lint, annotation step disabled, wrong expected phase, checker path renamed, unreachable-process handler removed), 1 reverting the NATS port fix, 3 over the async bridge (synchronous connect, no loop cleanup on failed connect, no loop cleanup on close) | 2026-11-25 | same |
| Control restoration | Every mutated file verified restored individually against its pre-mutation content, and `git diff --numstat` reviewed before committing — the defect 35 discipline, applied rather than merely recorded | 2026-11-25 | same |
| CI green after the fixes | **All five jobs green on both events** at `91393af`: `push` run `45718271682`, `pull_request` run `45718281143` — Backend ✓ · Compose ✓ · Secret scanning ✓ · Container image (amd64 + arm64) ✓ · **Runtime smoke test ✓** | 2026-11-25 | GitHub-hosted `ubuntu-latest`, x86-64 |
| B-1/B-2/B-3 closed | **59 checks passed** from inside a running container: the stack comes up healthy, the image `HEALTHCHECK` answers, all 34 posture checks hold against a real process, `pip` and `setuptools` are absent from the image, tzdata installed, uid 1001, `/app/data` writable with `nexus.db` on the volume, and the audit chain survives both a restart (2→3 rows) and a container recreate (3→4 rows) still verifying intact | 2026-11-25 | same, job `45718271682` |
| Defect 37 measurement | `asyncio.iscoroutinefunction(nats.connect)` → `True`; calling it synchronously returns a `coroutine` with no `jetstream` attribute. Measured against the installed library, not inferred from documentation | 2026-11-25 | sandbox, nats-py installed |
| Second live run — URL fixes confirmed | **6 passed / 1 failed / 5 geo-blocked / 3 skipped of 15** (run `45726585354`). Binance Vision downloaded a genuine **71,720-byte ZIP** from the corrected path (`data/spot/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2026-11-18.zip`), confirming defect 38 fixed. OKX again 5 of 5 with fresh data (bid 60482.6 / ask 60482.7, 100 candles to 2026-11-26T00:09Z). Bybit again 403 on all five, now correctly labelled `GEO-BLOCKED` | 2026-11-26 | GitHub-hosted runner |
| Defect 40, found by parsing the real file | The dump that defect 38's fix made downloadable then failed to parse: `ValueError: year 58852 is out of range`. Binance Vision spot dumps use **microsecond** timestamps from 2025-01-01 and `parse_kline_csv` passed `assume_ms=True`. Reproduced offline: `1764072000000000 / 1000` as seconds is year 57871 | 2026-11-26 | sandbox, by direct invocation |
| Disjointness of the epoch unit windows | Measured, because the whole fix rests on it: across 2010-01-01..2100-01-01 the windows are `s [1.262e9, 4.102e9]`, `ms [1.262e12, 4.102e12]`, `us [1.262e15, 4.102e15]`, `ns [1.262e18, 4.102e18]` — three orders of magnitude apart, no overlap. Each of the four magnitudes for one instant resolves to exactly **one** plausible unit, and all four convert to the same instant. A test asserts the disjointness so the property cannot rot silently | 2026-11-26 | sandbox |
| Defect 40 controls | **5 of 5 fired** with every mutated file verified restored: reverting to blanket division by 1000 (7 tests fail), emitting an implausible epoch instead of refusing it (1), widening the window so ms and s overlap (2 — caught by the disjointness test), dropping `timestamp_units` from both parsers (4), and reinstating `assume_ms` as a governing parameter (1) | 2026-11-26 | sandbox, local venv |
| Dukascopy still unverified — 503 *(**superseded 2026-11-26**: `verify_layout` has now passed against a real hour six times and `LAYOUT_VERIFIED = True` — `docs/14` §1.4 F-1 and §2.1)* | All four attempts at the corrected bi5 URL returned **HTTP 503**, so `verify_layout` had still never run against a real file. Dukascopy's datafeed is documented as aggressively rate-limited and uses 503 as well as 429 as its throttle response; some such hosts also reject a non-browser `User-Agent`, and this transport sends a descriptive one. **Which cause it is has not been determined** and is not guessed at here. 503 is classified `unavailable`, so the checks skip rather than fail | 2026-11-26 | GitHub-hosted runner |
| Suite after the defect-40 fix | **928 tests, 0 failures, 0 errors, 2 skipped**; `ruff check` and `ruff format --check` clean; `mypy` strict clean (49 files). The detection change altered no existing behaviour — all 918 prior tests still pass, because detection agrees with the old heuristic for every in-window seconds/milliseconds value | 2026-11-26 | sandbox, local venv |
| Live endpoint verification | **First contact with real venues** (run `45724918466`, 2026-11-25): 5 passed / 10 failed of 15 checks. OKX answered on all five endpoints with real data; Bybit answered 403 at the edge on all five; Binance Vision and Dukascopy answered 404 because our URLs were wrong (defects 38 and 39) | 2026-11-25 | GitHub-hosted runner, `ubuntu-latest` |
| OKX verified against live data | `BTC-USDT-SWAP`: contract size 0.01, tick size 0.1, status `live`; bid 60505.6 / ask 60505.7, spread 0.017 bps, uncrossed, entitlement `LIVE`; 50 trades, prices inside the quoted band — that run contained both sides, but `_assert_ticks` accepts `BUY`, `SELL` or an absent side, so a one-sided list passes and is not a failure (corrected 2026-11-26; `docs/14` F-9: run `45759709313` returned 50 buys and passed, correctly); 100 one-minute candles spanning 1.65 h, contiguous, each with `low <= open,close <= high`; 40-level book ordered and uncrossed. Raw responses captured to an artifact | 2026-11-25 | same |
| Bybit geo-block, measured not assumed | All five public unauthenticated endpoints returned HTTP 403 from a hosted runner. Bybit restricts certain jurisdictions at the CloudFront edge, so this is where the check runs and not what it checks. Classified `GEO-BLOCKED` and reported separately; **Bybit remains unverified** and needs the deployment host (D-021), which is in a region Bybit does not restrict | 2026-11-25 | same |
| Defect 38/39 confirmed by response, not by inference | `data/spot/klines/BTCUSDT/1m/BTCUSDT-1m-2026-11-18.zip` → 404; `EURUSD/2026-10-19/BID/12h_ticks.bi5` → 404. Both hosts answered, so neither was a network problem; a 404 means the request addressed nothing | 2026-11-25 | same |
| Corrected URL shapes | `data/spot/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2026-11-18.zip`, `data/spot/monthly/klines/...`, `data/spot/daily/aggTrades/...`, `datafeed/EURUSD/2026-10-19/12h_ticks.bi5`, `datafeed/EURUSD/2026-00-15/14h_ticks.bi5` — each transcribed from the venue's published layout and pinned by test | 2026-11-25 | sandbox, by direct invocation |
| The blind-fixture hole is closed | Control: reintroducing the `BID` segment into `hour_url` now fails **5** tests, of which **4 are fetch tests that were previously blind to it** because they keyed their recording transport by `hour_url` itself. Baseline passes, mutated fails, restore verified byte-for-byte | 2026-11-25 | sandbox, local venv |
| Full suite after the fixes | **918 tests, 0 failures, 0 errors, 2 skipped**; `ruff check` and `ruff format --check` clean (70 files); `mypy` strict clean (49 files) | 2026-11-25 | sandbox, local venv, Python 3.11 |
| Live module behaviour with no egress | All 15 checks skip and none fail — the classifier validated against genuine network failures. With the flag unset the module collects nothing at all, so the ordinary suite never touches the network (both directions executed by a hygiene test, using `--collect-only` so it cannot make requests) | 2026-11-25 | sandbox, no egress |

The skips are a pre-existing `pytest.skip` for an interval outside the modelled set plus the live
verification module's own gate; neither is a disabled test. The count rises 868 → 884 → 902 → 918 as
defects 31–33, the smoke wiring, defects 36–37, and the live verification work each
added tests.

The failed smoke run above is recorded as evidence rather than hidden: it is the first time this
project has observed a container start, and what it observed was that the stack could not. The
fixes are in; whether they are sufficient is the next CI run's answer, and B-1 stays open until a
run reports `core` healthy and serving.
